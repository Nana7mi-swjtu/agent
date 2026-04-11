from __future__ import annotations

import importlib
import logging
import sys
from pathlib import Path
from typing import Any

from flask import current_app

from .base import AgentToolSpec
from .context import AgentToolContext

logger = logging.getLogger(__name__)


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_query_function():
    kg_dir = _workspace_root() / "knowledge_graph"
    if not kg_dir.exists():
        return None
    kg_dir_str = str(kg_dir)
    if kg_dir_str not in sys.path:
        sys.path.insert(0, kg_dir_str)
    try:
        module = importlib.import_module("graph_cypher_query_tool")
        query_fn = getattr(module, "query_graph_with_trace", None)
        if callable(query_fn):
            return query_fn
    except Exception:
        logger.exception("Failed to import knowledge graph query module")
    return None


def _normalize_node_id(value: Any, *, fallback_prefix: str, index: int) -> str:
    text = str(value or "").strip()
    if text:
        return text
    return f"{fallback_prefix}-{index}"


def _extract_nodes_and_edges(context: Any) -> dict[str, list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    if isinstance(context, dict):
        rows = [context]
    elif isinstance(context, list):
        rows = [item for item in context if isinstance(item, dict)]

    node_map: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    def add_node(node_id: str, label: str, node_type: str = "entity") -> None:
        key = node_id.strip()
        if not key:
            return
        if key in node_map:
            return
        node_map[key] = {"id": key, "label": label or key, "type": node_type or "entity"}

    source_keys = ("source", "src", "from", "start", "start_node", "head")
    target_keys = ("target", "dst", "to", "end", "end_node", "tail")
    relation_keys = ("relationship", "relation", "type", "label", "rel_type")
    name_keys = ("name", "company", "company_name", "entity", "title", "c.name", "n.name")
    code_keys = ("ts_code", "code", "stock_code", "ticker", "c.ts_code", "n.ts_code")
    id_keys = ("id", "node_id", "entity_id", "c.id", "n.id")
    type_keys = ("node_type", "type", "entity_type", "label")
    entity_keys = (
        "name",
        "company",
        "company_name",
        "industry",
        "industry_name",
        "entity",
        "node",
        "title",
        "source_name",
        "target_name",
    )

    def _pick_text(row: dict[str, Any], keys: tuple[str, ...]) -> str:
        for key in keys:
            if key not in row:
                continue
            value = str(row.get(key, "")).strip()
            if value:
                return value
        return ""

    def _build_label(name: str, code: str) -> str:
        if name and code:
            return f"{name} ({code})"
        return name or code

    for row_index, row in enumerate(rows, start=1):
        # 优先提取标准三元组 source-target-relationship
        src = next((row.get(key) for key in source_keys if key in row), None)
        dst = next((row.get(key) for key in target_keys if key in row), None)
        rel = next((row.get(key) for key in relation_keys if key in row), "related")

        src_text = str(src or "").strip()
        dst_text = str(dst or "").strip()

        if src_text and dst_text:
            src_id = _normalize_node_id(src_text, fallback_prefix="src", index=row_index)
            dst_id = _normalize_node_id(dst_text, fallback_prefix="dst", index=row_index)
            add_node(src_id, src_text)
            add_node(dst_id, dst_text)
            edge_id = f"{src_id}->{dst_id}:{str(rel or 'related').strip() or 'related'}"
            edges.append(
                {
                    "id": edge_id,
                    "source": src_id,
                    "target": dst_id,
                    "relationship": str(rel or "related").strip() or "related",
                }
            )
            continue

        extracted_nodes = False

        primary_name = _pick_text(row, name_keys)
        primary_code = _pick_text(row, code_keys)
        primary_id = _pick_text(row, id_keys)
        primary_type = _pick_text(row, type_keys).lower() or "entity"
        if primary_name or primary_code:
            node_id = _normalize_node_id(primary_code or primary_name or primary_id, fallback_prefix="node", index=row_index)
            node_label = _build_label(primary_name, primary_code)
            add_node(node_id, node_label, primary_type)
            extracted_nodes = True

        for key in entity_keys:
            value = row.get(key)
            text = str(value or "").strip()
            if not text:
                continue
            node_id = _normalize_node_id(text, fallback_prefix=key, index=row_index)
            node_type = "entity"
            if key == "company":
                node_type = "corporation"
            elif key == "industry":
                node_type = "industry"
            elif "type" in row:
                node_type = str(row.get("type", "entity")).strip().lower() or "entity"
            add_node(node_id, text, node_type)
            extracted_nodes = True

        # 兜底：如果字段名不在预期集合，但行里有可读字符串，也至少落一个节点
        if not extracted_nodes and row:
            fallback_label = next(
                (str(v).strip() for v in row.values() if isinstance(v, str) and str(v).strip()),
                "",
            )
            if fallback_label:
                fallback_id = _normalize_node_id(fallback_label, fallback_prefix="row", index=row_index)
                add_node(fallback_id, fallback_label)

    return {"nodes": list(node_map.values())[:80], "edges": edges[:160]}


def create_knowledge_graph_tool(_: AgentToolContext) -> AgentToolSpec | None:
    if not bool(current_app.config.get("AGENT_KNOWLEDGE_GRAPH_ENABLED", False)):
        return None

    query_fn = _load_query_function()
    if query_fn is None:
        return None

    def _invoke(
        *,
        query: str,
        entity: str | None = None,
        intent: str | None = None,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        text = str(query or "").strip()
        if not text:
            entity_text = str(entity or "").strip()
            intent_text = str(intent or "").strip()
            text = f"{entity_text} {intent_text}".strip()
        if not text:
            return {"ok": False, "error": "query is required"}

        try:
            raw = query_fn(text, conversation_history=conversation_history)
        except Exception as exc:
            logger.exception("Knowledge graph tool invocation failed")
            return {"ok": False, "error": str(exc)}

        if not isinstance(raw, dict):
            return {"ok": False, "error": "knowledge graph returned invalid payload"}

        graph_data = _extract_nodes_and_edges(raw.get("context"))
        summary = str(raw.get("answer", "")).strip()
        meta = {
            "source": str(raw.get("source", "knowledge_graph")),
            "cypher": str(raw.get("cypher", "")),
            "fallbackReason": str(raw.get("fallback_reason", "")),
            "contextSize": len(raw.get("context", [])) if isinstance(raw.get("context"), list) else 0,
        }
        return {
            "ok": True,
            "summary": summary,
            "graph": graph_data,
            "meta": meta,
        }

    return AgentToolSpec(
        name="knowledge_graph_query",
        description="Query the knowledge graph and return graph nodes/edges plus a concise summary.",
        invoke=_invoke,
        args_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language graph query."},
                "entity": {"type": "string", "description": "Optional focus entity."},
                "intent": {"type": "string", "description": "Optional analysis intent."},
                "conversation_history": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "role": {"type": "string"},
                            "content": {"type": "string"},
                        },
                        "required": ["role", "content"],
                        "additionalProperties": False,
                    },
                    "description": "Optional prior turns for context understanding.",
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        category="knowledge_graph",
    )
