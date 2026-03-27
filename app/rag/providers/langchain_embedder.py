from __future__ import annotations

import json
import math
from urllib import request as urllib_request

from langchain_community.embeddings import DashScopeEmbeddings
from langchain_community.embeddings.fake import DeterministicFakeEmbedding

from ..errors import RAGConfigurationError, RAGValidationError


class DashScopeEmbedder:
    provider_name = "dashscope"

    def __init__(
        self,
        *,
        model_name: str,
        model_version: str,
        dimension: int,
        api_key: str,
    ) -> None:
        if not model_name.strip():
            raise RAGConfigurationError("RAG_EMBEDDING_MODEL must be configured")
        if not api_key.strip():
            raise RAGConfigurationError("RAG_EMBEDDING_API_KEY must be configured")
        if dimension <= 0:
            raise RAGValidationError("RAG_EMBEDDING_DIMENSION must be a positive integer")
        self.model_name = model_name.strip()
        self.model_version = model_version.strip() or "1"
        self.dimension = dimension
        self._embedder = DashScopeEmbeddings(model=self.model_name, dashscope_api_key=api_key.strip())

    def _normalize_vector(self, vector: list[float]) -> list[float]:
        values = [float(item) for item in vector]
        if len(values) != self.dimension:
            raise RAGValidationError("embedding dimension mismatch from embedder provider")
        norm = math.sqrt(sum(item * item for item in values))
        if norm == 0:
            return [0.0] * self.dimension
        return [item / norm for item in values]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = self._embedder.embed_documents(texts)
        return [self._normalize_vector(list(item)) for item in vectors]

    def embed_query(self, text: str) -> list[float]:
        vector = self._embedder.embed_query(text)
        return self._normalize_vector(list(vector))


class OpenAICompatibleEmbedder:
    provider_name = "openai-compatible"

    def __init__(
        self,
        *,
        model_name: str,
        model_version: str,
        dimension: int,
        api_key: str,
        base_url: str,
        timeout_seconds: int,
    ) -> None:
        if not model_name.strip():
            raise RAGConfigurationError("RAG_EMBEDDING_MODEL must be configured")
        if not api_key.strip():
            raise RAGConfigurationError("RAG_EMBEDDING_API_KEY must be configured")
        if not base_url.strip():
            raise RAGConfigurationError("RAG_EMBEDDING_BASE_URL must be configured")
        if dimension <= 0:
            raise RAGValidationError("RAG_EMBEDDING_DIMENSION must be a positive integer")
        self.model_name = model_name.strip()
        self.model_version = model_version.strip() or "1"
        self.dimension = dimension
        self._api_key = api_key.strip()
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = max(1, int(timeout_seconds))

    def _normalize_vector(self, vector: list[float]) -> list[float]:
        values = [float(item) for item in vector]
        if len(values) != self.dimension:
            raise RAGValidationError("embedding dimension mismatch from embedder provider")
        norm = math.sqrt(sum(item * item for item in values))
        if norm == 0:
            return [0.0] * self.dimension
        return [item / norm for item in values]

    def _request_embeddings(self, inputs: list[str]) -> list[list[float]]:
        body = {
            "model": self.model_name,
            "input": inputs,
        }
        req = urllib_request.Request(
            url=f"{self._base_url}/embeddings",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            method="POST",
        )
        try:
            with urllib_request.urlopen(req, timeout=self._timeout_seconds) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            raise RAGValidationError(f"openai-compatible embedding request failed: {exc}") from exc
        try:
            items = payload["data"]
            if not isinstance(items, list):
                raise TypeError("payload data is not a list")
            indexed_vectors = []
            for idx, item in enumerate(items):
                if not isinstance(item, dict):
                    raise TypeError(f"embedding item at index {idx} is invalid")
                vector = item.get("embedding")
                if not isinstance(vector, list):
                    raise TypeError(f"embedding vector at index {idx} is invalid")
                order = int(item.get("index", idx))
                indexed_vectors.append((order, self._normalize_vector(vector)))
            indexed_vectors.sort(key=lambda pair: pair[0])
            vectors = [vector for _, vector in indexed_vectors]
        except Exception as exc:
            raise RAGValidationError("openai-compatible embedding provider returned invalid response payload") from exc
        if len(vectors) != len(inputs):
            raise RAGValidationError("embedding vector count does not match input count")
        return vectors

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._request_embeddings(texts)

    def embed_query(self, text: str) -> list[float]:
        vectors = self._request_embeddings([text])
        return vectors[0]

# 这是是使用案例，对下面的clss进行模型替换，可以以在不改变接口的前提下，替换成任何其他的embedding模型，只要它们符合Embedder协议即可。
class FakeEmbedder:
    provider_name = "fake"

    def __init__(self, *, model_name: str, model_version: str, dimension: int) -> None:
        if dimension <= 0:
            raise RAGValidationError("RAG_EMBEDDING_DIMENSION must be a positive integer")
        self.model_name = model_name.strip() or "fake-embeddings"
        self.model_version = model_version.strip() or "1"
        self.dimension = dimension
        self._embedder = DeterministicFakeEmbedding(size=dimension)

    def _normalize_vector(self, vector: list[float]) -> list[float]:
        values = [float(item) for item in vector]
        if len(values) != self.dimension:
            raise RAGValidationError("embedding dimension mismatch from embedder provider")
        norm = math.sqrt(sum(item * item for item in values))
        if norm == 0:
            return [0.0] * self.dimension
        return [item / norm for item in values]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = self._embedder.embed_documents(texts)
        return [self._normalize_vector(list(item)) for item in vectors]

    def embed_query(self, text: str) -> list[float]:
        vector = self._embedder.embed_query(text)
        return self._normalize_vector(list(vector))
