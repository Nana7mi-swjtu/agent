from __future__ import annotations

from typing import Protocol

from ..schemas import ChunkPayload, RetrievalHit, SemanticSegment


class Embedder(Protocol):
    provider_name: str
    model_name: str
    model_version: str
    dimension: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class VectorStore(Protocol):
    provider_name: str

    def upsert_chunks(
        self,
        *,
        workspace_id: str,
        collection_name: str,
        chunk_payloads: list[ChunkPayload],
        vectors: list[list[float]],
    ) -> None: ...

    def query(
        self,
        *,
        workspace_id: str,
        collection_name: str,
        query_vector: list[float],
        top_k: int,
        filters: dict[str, str | int],
    ) -> list[RetrievalHit]: ...

    def get_chunk_vector(
        self,
        *,
        workspace_id: str,
        collection_name: str,
        chunk_id: str,
    ) -> list[float] | None: ...

    def delete_document_chunks(
        self,
        *,
        workspace_id: str,
        collection_name: str,
        document_id: int,
    ) -> None: ...


class Reranker(Protocol):
    provider_name: str

    def rerank(self, *, query: str, hits: list[RetrievalHit], top_k: int) -> list[RetrievalHit]: ...


class Chunker(Protocol):
    provider_name: str

    def chunk(self, *, document_id: int, source_name: str, blocks: list[dict], chunk_size: int, overlap: int) -> list[ChunkPayload]: ...


class SemanticChunkingProvider(Protocol):
    provider_name: str
    model_name: str
    model_version: str

    def segment(
        self,
        *,
        strategy: str,
        source_name: str,
        blocks: list[dict],
    ) -> list[SemanticSegment]: ...
