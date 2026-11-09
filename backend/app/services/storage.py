"""Saves uploaded files to disk under a generated name."""
import uuid
from pathlib import Path

from ..config import UPLOAD_DIR


def save_upload(raw: bytes, extension: str) -> str:
    """Write the file to the upload directory and return its stored path."""
    Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    stored = Path(UPLOAD_DIR) / f"{uuid.uuid4().hex}{extension}"
    stored.write_bytes(raw)
    return str(stored)


def delete_files(paths: list[str]) -> None:
    for p in paths:
        try:
            Path(p).unlink(missing_ok=True)
        except OSError:
            pass
