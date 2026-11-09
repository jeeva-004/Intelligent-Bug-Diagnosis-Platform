from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import BugReport, BugReportFile
from ..schemas import BugReportOut, BugReportSummary
from ..services import storage, validation

router = APIRouter(prefix="/api/bug-reports", tags=["bug reports"])


@router.post("", response_model=BugReportOut, status_code=201)
async def submit_bug_report(
    title: str | None = Form(None),
    description: str | None = Form(None),
    stack_trace: str | None = Form(None),
    error_log: str | None = Form(None),
    environment: str | None = Form(None),
    description_file: UploadFile | None = File(None),
    stack_trace_file: UploadFile | None = File(None),
    error_log_file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    """Accept a bug report as pasted text, uploaded files, or a mix of both.

    For each of description, stack trace and error log, either the pasted text
    or an uploaded file may be supplied. A file takes the place of pasted text
    for that field. The description is required.
    """
    title = validation.clean_text(title)
    environment = validation.clean_text(environment)
    if title and len(title) > 255:
        raise HTTPException(422, "Title must be 255 characters or fewer.")
    if environment and len(environment) > 255:
        raise HTTPException(422, "Environment must be 255 characters or fewer.")

    texts = {
        "description": validation.validate_pasted_text("description", description),
        "stack_trace": validation.validate_pasted_text("stack_trace", stack_trace),
        "error_log": validation.validate_pasted_text("error_log", error_log),
    }
    uploads = {
        "description": description_file,
        "stack_trace": stack_trace_file,
        "error_log": error_log_file,
    }

    read_files: dict[str, validation.ReadFile] = {}
    for field, upload in uploads.items():
        if upload is not None and upload.filename:
            read_files[field] = await validation.read_and_validate_upload(field, upload)
            texts[field] = read_files[field].text

    if not texts["description"]:
        raise HTTPException(422, "A bug description is required. Paste it or upload a file.")

    stored_paths: list[str] = []
    try:
        report = BugReport(
            title=title,
            description=texts["description"],
            stack_trace=texts["stack_trace"],
            error_log=texts["error_log"],
            environment=environment,
            input_method="upload" if read_files else "paste",
            status="submitted",
        )
        for field, f in read_files.items():
            path = storage.save_upload(f.raw, f.extension)
            stored_paths.append(path)
            report.files.append(
                BugReportFile(
                    field=field,
                    original_filename=f.original_filename,
                    stored_path=path,
                    file_type=f.extension.lstrip("."),
                    size_bytes=len(f.raw),
                )
            )
        db.add(report)
        db.commit()
        db.refresh(report)
    except Exception:
        db.rollback()
        storage.delete_files(stored_paths)
        raise HTTPException(500, "The bug report could not be saved. Please try again.")
    return report


@router.get("", response_model=list[BugReportSummary])
def list_bug_reports(limit: int = 50, db: Session = Depends(get_db)):
    limit = max(1, min(limit, 200))
    stmt = select(BugReport).order_by(BugReport.id.desc()).limit(limit)
    return db.scalars(stmt).all()


@router.get("/{report_id}", response_model=BugReportOut)
def get_bug_report(report_id: int, db: Session = Depends(get_db)):
    report = db.get(BugReport, report_id)
    if report is None:
        raise HTTPException(404, "Bug report not found.")
    return report
