"""Embedding provider abstraction.

hash = deterministic local vectors for tests/dev (no external API)
openai = optional remote embeddings when EMBEDDING_API_KEY is set
"""

from __future__ import annotations

import hashlib
import math
from typing import Protocol

from app.core.config import get_settings


class EmbeddingProvider(Protocol):
    model_name: str
    version: str
    dims: int

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashEmbeddingProvider:
    """Stable pseudo-embeddings from token hashes — good enough for tests & local RAG wiring."""

    def __init__(self, dims: int | None = None, model_name: str | None = None):
        settings = get_settings()
        self.dims = dims or settings.embedding_dims
        self.model_name = model_name or settings.embedding_model
        self.version = "1"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * self.dims
        tokens = text.lower().split() or [""]
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            for i in range(self.dims):
                vec[i] += digest[i % len(digest)] / 255.0
        compact = text.lower().replace(" ", "")
        for i in range(max(1, len(compact) - 2)):
            gram = compact[i : i + 3]
            h = int(hashlib.md5(gram.encode("utf-8")).hexdigest()[:8], 16)
            vec[h % self.dims] += 0.25
        return _l2_normalize(vec)


class OpenAIEmbeddingProvider:
    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        model_name: str | None = None,
        dims: int | None = None,
    ):
        settings = get_settings()
        self.api_key = api_key or settings.embedding_api_key
        self.api_base = (api_base or settings.embedding_api_base).rstrip("/")
        self.model_name = model_name or "text-embedding-3-small"
        self.dims = dims or settings.embedding_dims
        self.version = "1"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        import httpx

        if not self.api_key:
            raise RuntimeError("EMBEDDING_API_KEY is required for openai provider")
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.api_base}/embeddings",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model_name, "input": texts},
            )
            resp.raise_for_status()
            data = resp.json()["data"]
            data = sorted(data, key=lambda d: d["index"])
            return [d["embedding"] for d in data]


def get_embedding_provider() -> EmbeddingProvider:
    settings = get_settings()
    if settings.embedding_provider == "openai" and settings.embedding_api_key:
        return OpenAIEmbeddingProvider()
    return HashEmbeddingProvider()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0:
        return vec
    return [x / norm for x in vec]
