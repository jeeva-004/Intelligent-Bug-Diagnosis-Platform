"""Retrieval test using known duplicates.

Apache issues linked as "X duplicates Y" give pairs where the right answer is known.
For each duplicate X we search with its text and check whether the original Y is returned.

    python -m app.kb.evaluate --pairs 200
"""
import argparse
import random

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from .. import config
from ..database import SessionLocal
from ..models import HistoricalDefect
from .embedder import get_embedder
from .retrieval import search_similar
from .vector_store import VectorStore

TOP_K = 10


def duplicate_pairs(session: Session):
    dup, orig = aliased(HistoricalDefect), aliased(HistoricalDefect)
    stmt = (
        select(dup, orig)
        .join(orig, (orig.source == dup.source) & (orig.source_bug_id == dup.duplicate_of))
        .where(dup.duplicate_of.is_not(None))
    )
    return session.execute(stmt).all()


def evaluate(session: Session, store: VectorStore, embedder, max_pairs: int = 200, seed: int = 42) -> dict:
    pairs = duplicate_pairs(session)
    random.Random(seed).shuffle(pairs)
    pairs = pairs[:max_pairs]
    ranks = []
    for dup, orig in pairs:
        query = "\n".join(p for p in (dup.title, dup.description) if p)
        results = search_similar(query, session, store, embedder, top_k=TOP_K, exclude_defect_id=dup.id)
        ids = [r.defect_id for r in results]
        ranks.append(ids.index(orig.id) + 1 if orig.id in ids else None)
    n = len(ranks)
    report = {"pairs": n}
    for k in (1, 5, 10):
        report[f"recall@{k}"] = (sum(1 for r in ranks if r is not None and r <= k) / n) if n else None
    report["mrr"] = (sum(1 / r for r in ranks if r) / n) if n else None
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate retrieval on known duplicate pairs.")
    parser.add_argument("--pairs", type=int, default=200)
    args = parser.parse_args()
    store = VectorStore(config.CHROMA_DIR, config.CHROMA_COLLECTION, config.EMBEDDING_MODEL)
    with SessionLocal() as session:
        report = evaluate(session, store, get_embedder(config.EMBEDDING_MODEL), args.pairs)
    if not report["pairs"]:
        print("No duplicate pairs found in the knowledge base (needs Apache data with duplicate links).")
        return
    print(f"Duplicate pairs tested: {report['pairs']}")
    for k in (1, 5, 10):
        print(f"  recall@{k:<2}: {report[f'recall@{k}']:.2%}")
    print(f"  MRR      : {report['mrr']:.3f}")


if __name__ == "__main__":
    main()
