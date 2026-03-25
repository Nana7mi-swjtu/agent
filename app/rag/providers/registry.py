from __future__ import annotations

from flask import current_app

from ..errors import RAGConfigurationError
from .chromadb_store import ChromaVectorStore
from .default_embedder import DeterministicEmbedder
from .interfaces import Chunker, Embedder, Reranker, VectorStore
from .simple_chunker import DeterministicChunker


class NoopReranker:
    provider_name = "noop"

    def rerank(self, *, query: str, hits: list, top_k: int) -> list:
        return list(hits[:top_k])


def get_embedder() -> Embedder:
    provider = str(current_app.config.get("RAG_EMBEDDER_PROVIDER", "deterministic")).strip().lower()
    if provider == "deterministic":
        return DeterministicEmbedder(
            model_name=str(current_app.config["RAG_EMBEDDING_MODEL"]),
            model_version=str(current_app.config["RAG_EMBEDDING_VERSION"]),
            dimension=int(current_app.config["RAG_EMBEDDING_DIMENSION"]),
        )
    raise RAGConfigurationError(f"unsupported embedder provider: {provider}")


def get_vector_store() -> VectorStore:
    provider = str(current_app.config.get("RAG_VECTOR_PROVIDER", "chromadb")).strip().lower()
    if provider == "chromadb":
        return ChromaVectorStore(
            persist_dir=str(current_app.config["RAG_CHROMADB_PERSIST_DIR"]),
            collection_prefix=str(current_app.config["RAG_CHROMADB_COLLECTION_PREFIX"]),
        )
    raise RAGConfigurationError(f"unsupported vector provider: {provider}")


def get_reranker() -> Reranker | None:
    provider = str(current_app.config.get("RAG_RERANKER_PROVIDER", "")).strip().lower()
    if not provider:
        return None
    if provider == "noop":
        return NoopReranker()
    raise RAGConfigurationError(f"unsupported reranker provider: {provider}")


def get_chunker() -> Chunker:
    return DeterministicChunker()
