"""Command-line semantic search over the knowledge base.

    python -m app.kb.search "NullPointerException when saving file"
    python -m app.kb.search --bug-id 3          # use a submitted bug report (M1.3) as the query
"""
import argparse
import sys

from .. import config
from ..database import SessionLocal
from ..models import BugReport
from .embedder import get_embedder
from .retrieval import search_similar
from .vector_store import VectorStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Find similar historical defects.")
    parser.add_argument("query", nargs="?", help="bug text to search for")
    parser.add_argument("--bug-id", type=int, help="use a submitted bug report as the query")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--source", choices=["apache", "mozilla", "eclipse"])
    args = parser.parse_args()

    with SessionLocal() as session:
        query = args.query
        if args.bug_id:
            report = session.get(BugReport, args.bug_id)
            if report is None:
                sys.exit(f"Bug report {args.bug_id} not found.")
            query = "\n".join(p for p in (report.title, report.description, report.stack_trace) if p)
        if not query:
            sys.exit("Give a query text or --bug-id.")

        store = VectorStore(config.CHROMA_DIR, config.CHROMA_COLLECTION, config.EMBEDDING_MODEL)
        if store.count() == 0:
            sys.exit("The knowledge base is empty. Run: python -m app.kb.build --data-dir data --reset")
        embedder = get_embedder(config.EMBEDDING_MODEL)
        results = search_similar(query, session, store, embedder, top_k=args.top_k, source=args.source)

    if not results:
        print("No similar defects found.")
    for rank, r in enumerate(results, start=1):
        print(f"\n{rank}. [{r.source}] {r.source_bug_id}  similarity {r.score:.3f}")
        print(f"   {r.title}")
        print(f"   project: {r.project or '-'} | component: {r.component or '-'} | "
              f"status: {r.status or '-'} | resolution: {r.resolution or '-'}"
              + (f" | duplicate of {r.duplicate_of}" if r.duplicate_of else ""))
        for m in r.matches[:1]:
            snippet = " ".join(m.text.split())[:160]
            print(f"   matched {m.chunk_type}: {snippet}")


if __name__ == "__main__":
    main()
