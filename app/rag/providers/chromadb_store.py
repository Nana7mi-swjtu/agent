from __future__ import annotations

import json
import math
from pathlib import Path
from threading import Lock
from typing import Any

from ..errors import RAGValidationError
from ..schemas import ChunkPayload, RetrievalHit

_fallback_lock = Lock()
_fallback_data: dict[str, dict[str, dict[str, Any]]] = {}


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return -1.0
    numerator = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(v * v for v in left))
    right_norm = math.sqrt(sum(v * v for v in right))
    if left_norm == 0 or right_norm == 0:
        return -1.0
    return numerator / (left_norm * right_norm)


class ChromaVectorStore:
    provider_name = "chromadb"

    def __init__(self, *, persist_dir: str, collection_prefix: str) -> None:
        self._persist_dir = Path(persist_dir)
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        self._collection_prefix = collection_prefix
        self._chroma_client = None
        try:
            import chromadb

            self._chroma_client = chromadb.PersistentClient(path=str(self._persist_dir))
        except Exception:
            self._chroma_client = None

    def _collection_key(self, workspace_id: str, collection_name: str) -> str:
        return f"{self._collection_prefix}_{workspace_id}_{collection_name}".replace(" ", "_")

    def _fallback_path(self, key: str) -> Path:
        return self._persist_dir / f"{key}.json"

    def _load_fallback_collection(self, key: str) -> dict[str, Any]:
        with _fallback_lock:
            if key in _fallback_data:
                return _fallback_data[key]
            path = self._fallback_path(key)
            if path.exists():
                _fallback_data[key] = json.loads(path.read_text(encoding="utf-8"))
            else:
                _fallback_data[key] = {"vectors": {}, "documents": {}, "metadatas": {}}
            return _fallback_data[key]

    def _persist_fallback_collection(self, key: str) -> None:
        with _fallback_lock:
            path = self._fallback_path(key)
            path.write_text(json.dumps(_fallback_data[key], ensure_ascii=False), encoding="utf-8")

    def upsert_chunks(
        self,
        *,
        workspace_id: str,
        collection_name: str,
        chunk_payloads: list[ChunkPayload],
        vectors: list[list[float]],
    ) -> None:
        if len(chunk_payloads) != len(vectors):
            raise RAGValidationError("chunk payload count does not match embedding vector count")
        if not chunk_payloads:
            return

        key = self._collection_key(workspace_id, collection_name)
        if self._chroma_client is not None:
            collection = self._chroma_client.get_or_create_collection(name=key)
            ids = [payload.chunk_id for payload in chunk_payloads]
            documents = [payload.text for payload in chunk_payloads]
            metadatas = [dict(payload.metadata) for payload in chunk_payloads]
            collection.upsert(ids=ids, embeddings=vectors, documents=documents, metadatas=metadatas)
            return

        collection = self._load_fallback_collection(key)
        for payload, vector in zip(chunk_payloads, vectors, strict=False):
            metadata = dict(payload.metadata)
            collection["vectors"][payload.chunk_id] = vector
            collection["documents"][payload.chunk_id] = payload.text
            collection["metadatas"][payload.chunk_id] = metadata
        self._persist_fallback_collection(key)

    def query(
        self,
        *,
        workspace_id: str,
        collection_name: str,
        query_vector: list[float],
        top_k: int,
        filters: dict[str, str | int],
    ) -> list[RetrievalHit]:
        key = self._collection_key(workspace_id, collection_name)
        if self._chroma_client is not None:
            collection = self._chroma_client.get_or_create_collection(name=key)
            where = None
            if filters:
                if len(filters) == 1:
                    where = dict(filters)
                else:
                    where = {"$and": [{k: v} for k, v in filters.items()]}
            result = collection.query(query_embeddings=[query_vector], n_results=top_k, where=where or None)
            ids = (result.get("ids") or [[]])[0]
            docs = (result.get("documents") or [[]])[0]
            metadatas = (result.get("metadatas") or [[]])[0]
            distances = (result.get("distances") or [[]])[0]
            hits: list[RetrievalHit] = []
            for chunk_id, content, metadata, distance in zip(ids, docs, metadatas, distances, strict=False):
                metadata = metadata or {}
                source = str(metadata.get("source", "")).strip() or "unknown"
                page = metadata.get("page")
                section = metadata.get("section")
                score = 1.0 - float(distance)
                hits.append(
                    RetrievalHit(
                        chunk_id=str(chunk_id),
                        score=score,
                        source=source,
                        page=page if isinstance(page, int) else None,
                        section=section if isinstance(section, str) else None,
                        content=str(content or ""),
                        metadata=dict(metadata),
                    )
                )
            return hits

        collection = self._load_fallback_collection(key)

        def _matches(metadata: dict[str, Any]) -> bool:
            for k, v in filters.items():
                if metadata.get(k) != v:
                    return False
            return True

        ranked: list[tuple[float, str, dict[str, Any]]] = []
        for chunk_id, vector in collection["vectors"].items():
            metadata = collection["metadatas"].get(chunk_id) or {}
            if not _matches(metadata):
                continue
            score = _cosine_similarity(query_vector, vector)
            ranked.append((score, chunk_id, metadata))

        ranked.sort(key=lambda item: item[0], reverse=True)
        hits: list[RetrievalHit] = []
        for score, chunk_id, metadata in ranked[:top_k]:
            source = str(metadata.get("source", "")).strip()
            if not source:
                source = "unknown"
            page = metadata.get("page")
            section = metadata.get("section")
            hits.append(
                RetrievalHit(
                    chunk_id=chunk_id,
                    score=float(score),
                    source=source,
                    page=page if isinstance(page, int) else None,
                    section=section if isinstance(section, str) else None,
                    content=str(collection["documents"].get(chunk_id, "")),
                    metadata=metadata,
                )
            )
        return hits

    def get_chunk_vector(
        self,
        *,
        workspace_id: str,
        collection_name: str,
        chunk_id: str,
    ) -> list[float] | None:
        key = self._collection_key(workspace_id, collection_name)
        target = str(chunk_id).strip()
        if not target:
            return None
        if self._chroma_client is not None:
            collection = self._chroma_client.get_or_create_collection(name=key)
            result = collection.get(ids=[target], include=["embeddings"])
            raw_embeddings = result.get("embeddings")
            embeddings = list(raw_embeddings) if raw_embeddings is not None else []
            if len(embeddings) == 0:
                return None
            vector = embeddings[0]
            if not isinstance(vector, (list, tuple)):
                try:
                    vector = list(vector)
                except TypeError:
                    return None
            if len(vector) == 0:
                return None
            return [float(item) for item in vector]

        collection = self._load_fallback_collection(key)
        vector = collection["vectors"].get(target)
        if not isinstance(vector, list):
            return None
        return [float(item) for item in vector]
