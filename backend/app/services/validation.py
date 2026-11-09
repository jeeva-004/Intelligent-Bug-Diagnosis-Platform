"""Validation and file reading for bug submissions."""
import json
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, UploadFile

from ..config import ALLOWED_EXTENSIONS, MAX_UPLOAD_BYTES

FIELD_LABELS = {
    "description": "Bug description",
    "stack_trace": "Stack trace",
    "error_log": "Error log",
}


@dataclass
class ReadFile:
    text: str
    raw: bytes
    original_filename: str
    extension: str


def _fail(message: str, status: int = 422) -> None:
    raise HTTPException(status_code=status, detail=message)


def clean_text(value: str | None) -> str | None:
    """Strip surrounding whitespace; empty input becomes None."""
    if value is None:
        return None
    value = value.strip()
    return value or None


def validate_pasted_text(field: str, value: str | None) -> str | None:
    value = clean_text(value)
    if value is None:
        return None
    if "\x00" in value:
        _fail(f"{FIELD_LABELS[field]} contains invalid characters.")
    if len(value.encode("utf-8")) > MAX_UPLOAD_BYTES:
        _fail(f"{FIELD_LABELS[field]} is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.", 413)
    return value


async def read_and_validate_upload(field: str, upload: UploadFile) -> ReadFile:
    label = FIELD_LABELS[field]
    filename = Path(upload.filename or "").name
    extension = Path(filename).suffix.lower()

    if not filename:
        _fail(f"{label}: the uploaded file has no name.")
    if extension not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        _fail(f"{label}: '{filename}' is not supported. Allowed file types: {allowed}.", 415)

    # Read one byte past the limit so oversized files are detected without loading them fully.
    raw = await upload.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        _fail(f"{label}: '{filename}' is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.", 413)
    if not raw.strip():
        _fail(f"{label}: '{filename}' is empty.")
    if b"\x00" in raw:
        _fail(f"{label}: '{filename}' is not a text file.")

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        _fail(f"{label}: '{filename}' is not valid UTF-8 text.")

    if extension == ".json":
        try:
            json.loads(text)
        except json.JSONDecodeError as exc:
            _fail(f"{label}: '{filename}' is not valid JSON ({exc.msg} at line {exc.lineno}).")

    return ReadFile(text=text.strip(), raw=raw, original_filename=filename, extension=extension)
