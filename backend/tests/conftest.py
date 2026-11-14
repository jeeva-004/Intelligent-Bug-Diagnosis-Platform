"""Test environment: a throwaway SQLite database and folders. Set before the app is imported."""
import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["UPLOAD_DIR"] = f"{_tmp}/uploads"
os.environ["MAX_UPLOAD_BYTES"] = "1024"
os.environ["EMBEDDING_MODEL"] = "hash"  # no model download in tests
os.environ["CHROMA_DIR"] = f"{_tmp}/chroma"
