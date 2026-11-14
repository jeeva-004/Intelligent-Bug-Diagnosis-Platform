"""Chunking strategy (see docs/M1.4-knowledge-base.md).

One defect becomes several chunks, one kind of content per chunk, so a search hit tells you
*what* matched (the description, the stack trace, a comment or the resolution):

  description : title + description text, split into windows (max 4)
  stack_trace : extracted stack traces, split into windows (max 2)
  comment     : up to 5 longer comments, first window of each
  resolution  : resolution label + closing note (Apache only), first window
"""
from dataclasses import dataclass

from .records import DefectRecord

MAX_DESCRIPTION_CHUNKS = 4
MAX_TRACE_CHUNKS = 2
MAX_COMMENT_CHUNKS = 5
MIN_COMMENT_CHARS = 40


@dataclass
class Chunk:
    id: str
    text: str
    metadata: dict


def split_text(text: str, size: int, overlap: int) -> list[str]:
    """Split into windows of about `size` characters, preferring paragraph/line/sentence breaks."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            floor = start + int(size * 0.6)
            for sep in ("\n\n", "\n", ". ", " "):
                cut = text.rfind(sep, floor, end)
                if cut != -1:
                    end = cut + len(sep)
                    break
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def _metadata(defect_id: int, rec: DefectRecord, chunk_type: str, chunk_no: int) -> dict:
    # ChromaDB metadata values must be str/int/float/bool, so missing values become "".
    return {
        "defect_id": defect_id,
        "source": rec.source,
        "project": rec.project or "",
        "component": rec.component or "",
        "chunk_type": chunk_type,
        "chunk_no": chunk_no,
        "status": rec.status or "",
        "resolution": rec.resolution or "",
        "severity": rec.severity or "",
        "priority": rec.priority or "",
        "duplicate_of": rec.duplicate_of or "",
        "created_at": rec.created_at.isoformat() if rec.created_at else "",
    }


def build_chunks(defect_id: int, rec: DefectRecord, size: int, overlap: int) -> list[Chunk]:
    chunks: list[Chunk] = []

    def add(chunk_type: str, texts: list[str]) -> None:
        for n, text in enumerate(texts):
            chunks.append(
                Chunk(
                    id=f"{defect_id}:{chunk_type}:{n}",
                    text=text,
                    metadata=_metadata(defect_id, rec, chunk_type, n),
                )
            )

    body = "\n\n".join(p for p in (rec.title, rec.description) if p)
    if len(body) >= 10:
        add("description", split_text(body, size, overlap)[:MAX_DESCRIPTION_CHUNKS])

    if rec.stack_trace:
        add("stack_trace", split_text(rec.stack_trace, size, 0)[:MAX_TRACE_CHUNKS])

    if rec.resolution_text:
        label = f"Resolution: {rec.resolution}\n" if rec.resolution else ""
        add("resolution", split_text(label + rec.resolution_text, size, overlap)[:1])

    comment_texts: list[str] = []
    for c in rec.comments:
        if rec.resolution_text and c.text == rec.resolution_text:
            continue  # already indexed as the resolution chunk
        if len(c.text) >= MIN_COMMENT_CHARS:
            comment_texts.append(split_text(c.text, size, overlap)[0])
        if len(comment_texts) >= MAX_COMMENT_CHUNKS:
            break
    add("comment", comment_texts)
    return chunks
