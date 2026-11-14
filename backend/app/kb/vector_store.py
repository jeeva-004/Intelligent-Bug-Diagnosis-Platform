"""ChromaDB wrapper: stores chunk embeddings with defect metadata (cosine similarity)."""
from pathlib import Path

import chromadb


class VectorStore:
    def __init__(self, path: Path, collection: str, embedding_model: str):
        self.client = chromadb.PersistentClient(path=str(path))
        self.name = collection
        self.embedding_model = embedding_model
        self.collection = self._open()

    def _open(self):
        return self.client.get_or_create_collection(
            self.name,
            metadata={"hnsw:space": "cosine", "embedding_model": self.embedding_model},
        )

    def reset(self) -> None:
        try:
            self.client.delete_collection(self.name)
        except Exception:
            pass
        self.collection = self._open()

    def indexed_model(self) -> str | None:
        return (self.collection.metadata or {}).get("embedding_model")

    def count(self) -> int:
        return self.collection.count()

    def add(self, ids: list[str], texts: list[str], embeddings: list[list[float]], metadatas: list[dict]) -> None:
        self.collection.upsert(ids=ids, documents=texts, embeddings=embeddings, metadatas=metadatas)

    def query(self, embedding: list[float], n_results: int, where: dict | None = None) -> list[dict]:
        n_results = max(1, min(n_results, max(self.count(), 1)))
        res = self.collection.query(
            query_embeddings=[embedding], n_results=n_results, where=where or None
        )
        hits = []
        for i, chunk_id in enumerate(res["ids"][0]):
            hits.append(
                {
                    "id": chunk_id,
                    "text": res["documents"][0][i],
                    "metadata": res["metadatas"][0][i],
                    "similarity": 1.0 - res["distances"][0][i],
                }
            )
        return hits
