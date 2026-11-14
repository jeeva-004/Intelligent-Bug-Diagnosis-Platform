"""Embedding generation.

Default: a sentence-transformers model running locally (free, CPU is enough).
The special model name "hash" is a tiny word-hashing embedder with no download. It exists for
automated tests only and is NOT suitable for real semantic search.
"""
import hashlib
import math
import re
from functools import lru_cache

HASH_MODEL = "hash"
_TOKEN = re.compile(r"\w+")


class HashEmbedder:
    dimension = 384

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            vec = [0.0] * self.dimension
            for token in _TOKEN.findall(text.lower()):
                h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
                vec[h % self.dimension] += 1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            vectors.append([v / norm for v in vec])
        return vectors


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer  # imported here: it is slow to load

        self.model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self.model.encode(
            texts, batch_size=64, normalize_embeddings=True, show_progress_bar=False
        )
        return vectors.tolist()


@lru_cache(maxsize=2)
def get_embedder(model_name: str):
    if model_name == HASH_MODEL:
        return HashEmbedder()
    return SentenceTransformerEmbedder(model_name)
