"""MySQL tables for submitted bug reports (see M1.2 schema, section 7.1)."""
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

# LONGTEXT on MySQL (uploads can be up to 5 MB); plain TEXT elsewhere (tests).
def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


BigText = Text().with_variant(LONGTEXT(), "mysql")


class BugReport(Base):
    __tablename__ = "bug_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str] = mapped_column(BigText, nullable=False)
    stack_trace: Mapped[str | None] = mapped_column(BigText, nullable=True)
    error_log: Mapped[str | None] = mapped_column(BigText, nullable=True)
    environment: Mapped[str | None] = mapped_column(String(255), nullable=True)
    input_method: Mapped[str] = mapped_column(Enum("paste", "upload", name="input_method"), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("submitted", "processing", "completed", "failed", name="bug_status"),
        nullable=False,
        default="submitted",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    files: Mapped[list["BugReportFile"]] = relationship(
        back_populates="bug_report", cascade="all, delete-orphan"
    )


class BugReportFile(Base):
    __tablename__ = "bug_report_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bug_report_id: Mapped[int] = mapped_column(ForeignKey("bug_reports.id", ondelete="CASCADE"), nullable=False)
    field: Mapped[str] = mapped_column(
        Enum("description", "stack_trace", "error_log", name="file_field"), nullable=False
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    bug_report: Mapped[BugReport] = relationship(back_populates="files")
