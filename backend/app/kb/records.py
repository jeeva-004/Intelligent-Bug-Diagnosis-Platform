"""Standardised in-memory form of a historical defect (matches the historical_defects schema)."""
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class CommentRecord:
    text: str
    created_at: datetime | None = None


@dataclass
class DefectRecord:
    source: str  # mozilla | apache | eclipse
    source_bug_id: str
    project: str | None = None
    component: str | None = None
    title: str | None = None
    description: str | None = None
    stack_trace: str | None = None
    resolution_text: str | None = None
    status: str | None = None
    resolution: str | None = None
    severity: str | None = None
    priority: str | None = None
    duplicate_of: str | None = None
    created_at: datetime | None = None
    resolved_at: datetime | None = None
    comments: list[CommentRecord] = field(default_factory=list)
