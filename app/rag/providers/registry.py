from __future__ import annotations

from flask import current_app

from ..errors import RAGConfigurationError
from .chromadb_store import ChromaVectorStore
from .interfaces import Chunker, Embedder, Reranker, SemanticChunkingProvider, VectorStore
from .langchain_embedder import DashScopeEmbedder, FakeEmbedder, OpenAICompatibleEmbedder
from .langchain_reranker import FakeReranker, OpenAICompatibleReranker
from .semantic_chunking_provider import (
    NoopSemanticChunkingProvider,
    OpenAICompatibleSemanticChunkingProvider,
)
from .simple_chunker import DeterministicChunker


def get_embedder() -> Embedder:
    provider = str(current_app.config.get("RAG_EMBEDDER_PROVIDER", "")).strip().lower()
    if not provider:
        raise RAGConfigurationError("RAG_EMBEDDER_PROVIDER must be explicitly configured")
    if provider == "dashscope":
        return DashScopeEmbedder(
            model_name=str(current_app.config["RAG_EMBEDDING_MODEL"]),
            model_version=str(current_app.config["RAG_EMBEDDING_VERSION"]),
            dimension=int(current_app.config["RAG_EMBEDDING_DIMENSION"]),
            api_key=str(current_app.config.get("RAG_EMBEDDING_API_KEY", "")),
        )
    if provider in {"openai", "openai-compatible"}:
        return OpenAICompatibleEmbedder(
            model_name=str(current_app.config["RAG_EMBEDDING_MODEL"]),
            model_version=str(current_app.config["RAG_EMBEDDING_VERSION"]),
            dimension=int(current_app.config["RAG_EMBEDDING_DIMENSION"]),
            api_key=str(current_app.config.get("RAG_EMBEDDING_API_KEY", "")),
            base_url=str(current_app.config.get("RAG_EMBEDDING_BASE_URL", "")),
            timeout_seconds=int(current_app.config.get("RAG_EMBEDDING_TIMEOUT_SECONDS", 20)),
        )
    if provider == "fake":
        return FakeEmbedder(
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


def get_reranker() -> Reranker:
    provider = str(current_app.config.get("RAG_RERANKER_PROVIDER", "")).strip().lower()
    if not provider:
        raise RAGConfigurationError("RAG_RERANKER_PROVIDER must be explicitly configured")
    if provider in {"openai", "openai-compatible", "qwen"}:
        return OpenAICompatibleReranker(
            model_name=str(current_app.config.get("RAG_RERANKER_MODEL", "")),
            api_key=str(current_app.config.get("RAG_RERANKER_API_KEY", "")),
            base_url=str(current_app.config.get("RAG_RERANKER_BASE_URL", "")),
            timeout_seconds=int(current_app.config.get("RAG_RERANKER_TIMEOUT_SECONDS", 20)),
        )
    if provider == "fake":
        return FakeReranker()
    raise RAGConfigurationError(f"unsupported reranker provider: {provider}")


def get_chunker() -> Chunker:
    return DeterministicChunker()


def get_semantic_chunking_provider() -> SemanticChunkingProvider:
    provider = str(current_app.config.get("RAG_CHUNK_AI_PROVIDER", "noop")).strip().lower()
    if provider == "noop":
        return NoopSemanticChunkingProvider()
    if provider in {"openai", "openai-compatible"}:
        return OpenAICompatibleSemanticChunkingProvider(
            model_name=str(current_app.config.get("RAG_CHUNK_AI_MODEL", "semantic-chunker-v1")),
            api_key=str(current_app.config.get("RAG_CHUNK_AI_API_KEY", "")),
            base_url=str(current_app.config.get("RAG_CHUNK_AI_BASE_URL", "")),
            timeout_seconds=int(current_app.config.get("RAG_CHUNK_AI_TIMEOUT_SECONDS", 20)),
        )
    raise RAGConfigurationError(f"unsupported chunking ai provider: {provider}")
