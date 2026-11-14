"""Application settings, read from environment variables (or a .env file)."""
import os
from pathlib import Path


def _load_dotenv() -> None:
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://root:password@localhost:3306/bug_diagnosis",
)
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "uploads"))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))  # 5 MB
ALLOWED_EXTENSIONS = {".txt", ".log", ".json"}
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:4200").split(",")]

# ---- M1.4 Historical Defect Knowledge Base ----
DATA_DIR = Path(os.getenv("DATA_DIR", "data"))  # folder holding the unzipped Kaggle datasets
CHROMA_DIR = Path(os.getenv("CHROMA_DIR", "chroma_db"))
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "historical_defects")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
APACHE_SAMPLE_SIZE = int(os.getenv("APACHE_SAMPLE_SIZE", "10000"))  # 0 = all eligible Apache bugs
APACHE_DUPLICATE_PAIRS = int(os.getenv("APACHE_DUPLICATE_PAIRS", "300"))
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))  # characters
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "150"))  # characters
MIN_DESCRIPTION_CHARS = int(os.getenv("MIN_DESCRIPTION_CHARS", "20"))
