# Intelligent Bug Diagnosis Platform with Fix Recommendation Assistance

Infosys Springboard Virtual Internship project.

## Milestone 1 status

| Part | Status |
|---|---|
| M1.1 Research and technical understanding | Done (document) |
| M1.2 System architecture | Done (document) |
| M1.3 Bug Submission Module | Done (this repository) |
| M1.4 Historical Defect Knowledge Base | Not started |

## Tech stack (confirmed)

Angular (frontend), Python with FastAPI (backend), MySQL (bug records and defect metadata),
ChromaDB (vector store), sentence-transformers (embeddings), Ollama (local LLM runtime),
pandas (data cleaning). Only the parts needed for M1.3 are implemented so far.

## Repository layout

```
backend/    FastAPI app (API, validation, MySQL storage) and tests
frontend/   Angular app (bug submission page)
```

## M1.3 Bug Submission Module

- Paste a bug description, stack trace and error log, or upload a file for any of the three.
- Allowed upload types: `.txt`, `.log`, `.json` (max 5 MB each). `.json` files must be valid JSON.
- An uploaded file replaces the pasted text for that field. The bug description is required.
- Reports are saved in MySQL (`bug_reports`, `bug_report_files`); files are saved in `backend/uploads/`.

### API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/bug-reports` | Submit a report (multipart form) |
| GET | `/api/bug-reports` | List recent reports |
| GET | `/api/bug-reports/{id}` | Get one report |
| GET | `/api/health` | Health check |

Form fields for POST: `title`, `description`, `stack_trace`, `error_log`, `environment`,
`description_file`, `stack_trace_file`, `error_log_file`.

## Setup

### 1. MySQL

```sql
CREATE DATABASE bug_diagnosis CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 2. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows   (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env          # Linux/macOS: cp .env.example .env  -> then edit DATABASE_URL
uvicorn app.main:app --reload --port 8000
```

Tables are created automatically on startup. API docs: http://localhost:8000/docs

Run tests (they use a temporary SQLite database, so MySQL is not needed):

```bash
python -m pytest
```

### 3. Frontend

```bash
cd frontend
npm install
npm start
```

Open http://localhost:4200. The backend address is set in `frontend/src/app/config.ts`.
