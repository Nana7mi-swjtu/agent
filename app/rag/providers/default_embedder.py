from __future__ import annotations

import hashlib
import math

from ..errors import RAGValidationError


class DeterministicEmbedder:
    provider_name = "deterministic"

    def __init__(self, *, model_name: str, model_version: str, dimension: int) -> None:
        if dimension <= 0:
            raise RAGValidationError("embedding dimension must be positive")
        self.model_name = model_name
        self.model_version = model_version
        self.dimension = dimension

    def _embed(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        seed = int.from_bytes(digest[:8], "big")
        values: list[float] = []
        state = seed or 1
        for _ in range(self.dimension):
            state = (1103515245 * state + 12345) & 0x7FFFFFFF
            values.append((state / 0x7FFFFFFF) * 2.0 - 1.0)
        norm = math.sqrt(sum(v * v for v in values))
        if norm == 0:
            return [0.0] * self.dimension
        return [v / norm for v in values]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)
