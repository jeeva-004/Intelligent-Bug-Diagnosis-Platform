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


# ---- Historical defect knowledge base (M1.4, see M1.2 schema section 7.2) ----
from sqlalchemy import UniqueConstraint  # noqa: E402


class HistoricalDefect(Base):
    __tablename__ = "historical_defects"
    __table_args__ = (UniqueConstraint("source", "source_bug_id", name="uq_defect_source_bug"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(Enum("mozilla", "apache", "eclipse", name="defect_source"), nullable=False)
    source_bug_id: Mapped[str] = mapped_column(String(50), nullable=False)
    project: Mapped[str | None] = mapped_column(String(100), nullable=True)
    component: Mapped[str | None] = mapped_column(String(100), nullable=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(BigText, nullable=True)
    stack_trace: Mapped[str | None] = mapped_column(BigText, nullable=True)
    resolution_text: Mapped[str | None] = mapped_column(BigText, nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resolution: Mapped[str | None] = mapped_column(String(50), nullable=True)
    severity: Mapped[str | None] = mapped_column(String(50), nullable=True)
    priority: Mapped[str | None] = mapped_column(String(50), nullable=True)
    duplicate_of: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    comments: Mapped[list["DefectComment"]] = relationship(
        back_populates="defect", cascade="all, delete-orphan"
    )


class DefectComment(Base):
    __tablename__ = "defect_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    defect_id: Mapped[int] = mapped_column(ForeignKey("historical_defects.id", ondelete="CASCADE"), nullable=False)
    comment_no: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(BigText, nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    defect: Mapped[HistoricalDefect] = relationship(back_populates="comments")
