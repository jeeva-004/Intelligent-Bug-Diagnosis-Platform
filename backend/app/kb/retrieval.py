"""Semantic retrieval of similar historical defects.

1. Embed the query text.
2. Search ChromaDB for the nearest chunks (optionally filtered by metadata).
3. Group chunks by defect, keeping the best score per defect.
4. Load the full defect records from MySQL.
"""
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import HistoricalDefect
from .vector_store import VectorStore

MAX_QUERY_CHARS = 4000


@dataclass
class MatchedChunk:
    chunk_type: str
    similarity: float
    text: str


@dataclass
class SimilarDefect:
    defect_id: int
    source: str
    source_bug_id: str
    title: str | None
    project: str | None
    component: str | None
    status: str | None
    resolution: str | None
    duplicate_of: str | None
    resolution_text: str | None
    score: float  # best chunk similarity (cosine, 0 to 1)
    matches: list[MatchedChunk] = field(default_factory=list)


def search_similar(
    query: str,
    session: Session,
    store: VectorStore,
    embedder,
    top_k: int = 5,
    source: str | None = None,
    exclude_defect_id: int | None = None,
) -> list[SimilarDefect]:
    query = (query or "").strip()[:MAX_QUERY_CHARS]
    if not query:
        return []
    embedding = embedder.embed([query])[0]
    where = {"source": source} if source else None
    # Several chunks of one defect can match, so fetch more chunks than defects.
    hits = store.query(embedding, n_results=max(top_k * 6, 30), where=where)

    grouped: dict[int, list[dict]] = {}
    for hit in hits:
        defect_id = int(hit["metadata"]["defect_id"])
        if defect_id == exclude_defect_id:
            continue
        grouped.setdefault(defect_id, []).append(hit)
    if not grouped:
        return []

    rows = session.scalars(select(HistoricalDefect).where(HistoricalDefect.id.in_(list(grouped)))).all()
    by_id = {r.id: r for r in rows}

    results: list[SimilarDefect] = []
    for defect_id, defect_hits in grouped.items():
        row = by_id.get(defect_id)
        if row is None:
            continue  # index and MySQL out of sync for this defect
        defect_hits.sort(key=lambda h: -h["similarity"])
        results.append(
            SimilarDefect(
                defect_id=row.id,
                source=row.source,
                source_bug_id=row.source_bug_id,
                title=row.title,
                project=row.project,
                component=row.component,
                status=row.status,
                resolution=row.resolution,
                duplicate_of=row.duplicate_of,
                resolution_text=row.resolution_text,
                score=defect_hits[0]["similarity"],
                matches=[
                    MatchedChunk(h["metadata"]["chunk_type"], h["similarity"], h["text"])
                    for h in defect_hits[:3]
                ],
            )
        )
    results.sort(key=lambda r: -r.score)
    return results[:top_k]
