from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import chromadb
from dotenv import load_dotenv


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect embedding vectors stored in ChromaDB.")
    parser.add_argument(
        "--persist-dir",
        default=None,
        help="Chroma persist directory. Defaults to RAG_CHROMADB_PERSIST_DIR from .env.",
    )
    parser.add_argument(
        "--collection",
        default=None,
        help="Collection name. If omitted, the script selects the first available collection.",
    )
    parser.add_argument(
        "--chunk-id",
        default=None,
        help="Read vector by chunk_id. If omitted, read the first vector in collection.",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=16,
        help="How many vector dimensions to print as sample (default: 16).",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Print the full vector (may be long).",
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="Only list collections and exit.",
    )
    return parser.parse_args()


def _collection_name(item: Any) -> str:
    name = getattr(item, "name", None)
    if isinstance(name, str):
        return name
    return str(item)


def _resolve_persist_dir(raw: str | None) -> Path:
    root = Path(__file__).resolve().parent
    candidate = raw or os.getenv("RAG_CHROMADB_PERSIST_DIR") or "uploads/chromadb"
    path = Path(candidate)
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def _pick_collection(client: chromadb.PersistentClient, explicit_name: str | None) -> str:
    names = [_collection_name(item) for item in client.list_collections()]
    if not names:
        raise RuntimeError("No collections found in ChromaDB.")
    if explicit_name:
        if explicit_name not in names:
            raise RuntimeError(f"Collection '{explicit_name}' not found. Available: {', '.join(names)}")
        return explicit_name
    return names[0]


def _to_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    try:
        return list(value)
    except TypeError:
        return []


def _get_by_chunk_id(collection: Any, chunk_id: str) -> dict[str, Any]:
    result = collection.get(ids=[chunk_id], include=["embeddings", "documents", "metadatas"])
    ids = _to_list(result.get("ids"))
    if not ids:
        raise RuntimeError(f"chunk_id '{chunk_id}' not found in collection.")
    embeddings = _to_list(result.get("embeddings"))
    documents = _to_list(result.get("documents"))
    metadatas = _to_list(result.get("metadatas"))
    vector = _to_list(embeddings[0] if embeddings else [])
    return {
        "chunk_id": str(ids[0]),
        "vector": [float(item) for item in vector],
        "document": str(documents[0]) if documents else "",
        "metadata": metadatas[0] if metadatas else {},
    }


def _get_first_item(collection: Any) -> dict[str, Any]:
    result = collection.get(limit=1, include=["embeddings", "documents", "metadatas"])
    ids = _to_list(result.get("ids"))
    if not ids:
        raise RuntimeError("Collection has no vectors yet.")
    embeddings = _to_list(result.get("embeddings"))
    documents = _to_list(result.get("documents"))
    metadatas = _to_list(result.get("metadatas"))
    vector = _to_list(embeddings[0] if embeddings else [])
    return {
        "chunk_id": str(ids[0]),
        "vector": [float(item) for item in vector],
        "document": str(documents[0]) if documents else "",
        "metadata": metadatas[0] if metadatas else {},
    }


def main() -> int:
    load_dotenv()
    args = _parse_args()
    sample_size = max(1, min(int(args.sample_size), 512))
    persist_dir = _resolve_persist_dir(args.persist_dir)
    if not persist_dir.exists():
        print(f"[ERROR] Chroma persist dir not found: {persist_dir}", file=sys.stderr)
        return 1

    client = chromadb.PersistentClient(path=str(persist_dir))
    collections = [_collection_name(item) for item in client.list_collections()]
    print(f"persist_dir={persist_dir}")
    print(f"collections={collections}")

    if args.list_only:
        return 0

    try:
        collection_name = _pick_collection(client, args.collection)
    except RuntimeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    collection = client.get_collection(collection_name)
    try:
        item = (
            _get_by_chunk_id(collection, str(args.chunk_id).strip())
            if args.chunk_id
            else _get_first_item(collection)
        )
    except RuntimeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    vector = item["vector"]
    payload = {
        "collection": collection_name,
        "chunk_id": item["chunk_id"],
        "dimension": len(vector),
        "sample": [round(float(v), 6) for v in vector[:sample_size]],
        "metadata": item["metadata"],
        "document_preview": str(item["document"])[:240],
    }
    if args.full:
        payload["vector"] = vector
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
