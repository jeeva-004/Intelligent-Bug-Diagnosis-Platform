from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BugReportFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    field: str
    original_filename: str
    file_type: str
    size_bytes: int


class BugReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str | None
    description: str
    stack_trace: str | None
    error_log: str | None
    environment: str | None
    input_method: str
    status: str
    created_at: datetime
    files: list[BugReportFileOut] = []


class BugReportSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str | None
    input_method: str
    status: str
    created_at: datetime
