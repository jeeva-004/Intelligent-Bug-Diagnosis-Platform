"""Build the historical defect knowledge base.

    python -m app.kb.build --data-dir data --reset

Steps: load CSVs -> clean -> save to MySQL -> chunk -> embed -> index in ChromaDB.
"""
import argparse
import sys
import time
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .. import config
from ..database import Base, SessionLocal, engine
from ..models import DefectComment, HistoricalDefect
from .chunking import build_chunks
from .cleaning import clean_record
from .embedder import get_embedder
from .loaders import load_apache, load_bugzilla_csv
from .records import DefectRecord
from .vector_store import VectorStore

BATCH_DEFECTS = 500


def _trunc(value: str | None, n: int) -> str | None:
    return value[:n] if value else value


def _to_row(rec: DefectRecord) -> HistoricalDefect:
    row = HistoricalDefect(
        source=rec.source,
        source_bug_id=_trunc(rec.source_bug_id, 50),
        project=_trunc(rec.project, 100),
        component=_trunc(rec.component, 100),
        title=_trunc(rec.title, 500),
        description=rec.description,
        stack_trace=rec.stack_trace,
        resolution_text=rec.resolution_text,
        status=_trunc(rec.status, 50),
        resolution=_trunc(rec.resolution, 50),
        severity=_trunc(rec.severity, 50),
        priority=_trunc(rec.priority, 50),
        duplicate_of=_trunc(rec.duplicate_of, 50),
        created_at=rec.created_at,
        resolved_at=rec.resolved_at,
    )
    for n, c in enumerate(rec.comments, start=1):
        row.comments.append(DefectComment(comment_no=n, text=c.text, created_at=c.created_at))
    return row


def clean_all(raw: list[DefectRecord], min_chars: int, log=print) -> list[DefectRecord]:
    cleaned, seen = [], set()
    dropped_short = dropped_dupe = 0
    for rec in raw:
        out = clean_record(rec, min_chars)
        if out is None:
            dropped_short += 1
            continue
        key = (out.source, out.source_bug_id)
        if key in seen:
            dropped_dupe += 1
            continue
        seen.add(key)
        cleaned.append(out)
    log(f"Cleaning: {len(raw):,} read, {len(cleaned):,} kept, "
        f"{dropped_short:,} dropped (description too short), {dropped_dupe:,} dropped (repeated id).")
    return cleaned


def index_records(
    records: list[DefectRecord],
    session: Session,
    store: VectorStore,
    embedder,
    chunk_size: int,
    chunk_overlap: int,
    log=print,
) -> int:
    total_chunks = 0
    started = time.time()
    for start in range(0, len(records), BATCH_DEFECTS):
        batch = records[start : start + BATCH_DEFECTS]
        rows = [_to_row(r) for r in batch]
        session.add_all(rows)
        session.flush()  # assigns database ids
        chunks = []
        for row, rec in zip(rows, batch):
            chunks.extend(build_chunks(row.id, rec, chunk_size, chunk_overlap))
        if chunks:
            vectors = embedder.embed([c.text for c in chunks])
            store.add([c.id for c in chunks], [c.text for c in chunks], vectors, [c.metadata for c in chunks])
        session.commit()
        total_chunks += len(chunks)
        done = min(start + BATCH_DEFECTS, len(records))
        log(f"  indexed {done:,}/{len(records):,} defects ({total_chunks:,} chunks, {time.time() - started:.0f}s)")
    return total_chunks


def build_knowledge_base(
    data_dir: Path,
    reset: bool = False,
    apache_sample: int | None = None,
    duplicate_pairs: int | None = None,
    bugzilla_sample: int = 0,
    sources: tuple[str, ...] = ("apache", "mozilla", "eclipse"),
    store: VectorStore | None = None,
    embedder=None,
    log=print,
) -> dict:
    Base.metadata.create_all(bind=engine)
    store = store or VectorStore(config.CHROMA_DIR, config.CHROMA_COLLECTION, config.EMBEDDING_MODEL)
    embedder = embedder or get_embedder(config.EMBEDDING_MODEL)

    raw: list[DefectRecord] = []
    if "apache" in sources:
        raw += load_apache(
            data_dir,
            config.APACHE_SAMPLE_SIZE if apache_sample is None else apache_sample,
            config.APACHE_DUPLICATE_PAIRS if duplicate_pairs is None else duplicate_pairs,
            log=log,
        )
    if "mozilla" in sources:
        raw += load_bugzilla_csv(data_dir, "mozilla_bug_report_data.csv", "mozilla", bugzilla_sample, log=log)
    if "eclipse" in sources:
        raw += load_bugzilla_csv(data_dir, "eclipse_bug_report_data.csv", "eclipse", bugzilla_sample, log=log)
    if not raw:
        raise SystemExit(f"No dataset files found under '{data_dir}'. Unzip the Kaggle datasets there.")

    records = clean_all(raw, config.MIN_DESCRIPTION_CHARS, log)

    with SessionLocal() as session:
        existing = session.scalar(select(func.count()).select_from(HistoricalDefect)) or 0
        if existing and not reset:
            raise SystemExit(
                f"The knowledge base already holds {existing:,} defects. Run again with --reset to rebuild it."
            )
        if reset:
            session.execute(delete(DefectComment))
            session.execute(delete(HistoricalDefect))
            session.commit()
            store.reset()
        elif store.indexed_model() not in (None, config.EMBEDDING_MODEL):
            raise SystemExit("The index was built with a different embedding model. Use --reset.")

        log(f"Indexing with embedding model '{config.EMBEDDING_MODEL}' ...")
        chunks = index_records(records, session, store, embedder, config.CHUNK_SIZE, config.CHUNK_OVERLAP, log)

        by_source = dict(
            session.execute(select(HistoricalDefect.source, func.count()).group_by(HistoricalDefect.source)).all()
        )
    summary = {"defects": len(records), "chunks": chunks, "by_source": by_source, "index_count": store.count()}
    log(f"Done: {summary}")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the historical defect knowledge base.")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR, help="folder with the unzipped datasets")
    parser.add_argument("--reset", action="store_true", help="delete and rebuild the existing knowledge base")
    parser.add_argument("--apache-sample", type=int, default=None, help="Apache bugs to load (0 = all)")
    parser.add_argument("--bugzilla-sample", type=int, default=0,
                        help="Mozilla/Eclipse bugs to load from each file (0 = all)")
    parser.add_argument("--sources", nargs="+", default=["apache", "mozilla", "eclipse"],
                        choices=["apache", "mozilla", "eclipse"])
    args = parser.parse_args()
    try:
        build_knowledge_base(
            args.data_dir, args.reset, args.apache_sample,
            bugzilla_sample=args.bugzilla_sample, sources=tuple(args.sources),
        )
    except ValueError as exc:
        sys.exit(f"Error: {exc}")


if __name__ == "__main__":
    main()
