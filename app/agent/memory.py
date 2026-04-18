from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..models import AgentConversationMessage, AgentConversationThread

_MEMORY_HISTORY_LIMIT = 8
_MAX_MESSAGE_SNIPPET_LENGTH = 360


def _trim_text(value: object, *, limit: int = _MAX_MESSAGE_SNIPPET_LENGTH) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _role_label(role: str) -> str:
    normalized = str(role or "").strip().lower()
    if normalized == "user":
        return "用户"
    if normalized == "assistant":
        return "助手"
    if normalized == "system":
        return "系统"
    return normalized or "消息"


def get_or_create_conversation_thread(
    db: Session,
    *,
    user_id: int,
    workspace_id: str,
    role: str,
    conversation_id: str,
) -> AgentConversationThread:
    thread = (
        db.execute(
            select(AgentConversationThread).where(
                AgentConversationThread.user_id == user_id,
                AgentConversationThread.workspace_id == workspace_id,
                AgentConversationThread.role == role,
                AgentConversationThread.conversation_id == conversation_id,
            )
        )
        .scalars()
        .one_or_none()
    )
    if thread is not None:
        return thread

    thread = AgentConversationThread(
        user_id=user_id,
        workspace_id=workspace_id,
        role=role,
        conversation_id=conversation_id,
        summary=None,
        last_user_message=None,
        last_assistant_message=None,
        last_intent=None,
        last_clarification_question=None,
        turn_count=0,
        last_message_at=None,
    )
    db.add(thread)
    db.flush()
    return thread


def load_conversation_history(
    db: Session,
    *,
    user_id: int,
    workspace_id: str,
    role: str,
    conversation_id: str,
    limit: int = _MEMORY_HISTORY_LIMIT,
) -> tuple[AgentConversationThread, list[dict[str, str]], str]:
    thread = get_or_create_conversation_thread(
        db,
        user_id=user_id,
        workspace_id=workspace_id,
        role=role,
        conversation_id=conversation_id,
    )

    messages = (
        db.execute(
            select(AgentConversationMessage)
            .where(AgentConversationMessage.thread_id == thread.id)
            .order_by(desc(AgentConversationMessage.created_at), desc(AgentConversationMessage.id))
            .limit(limit)
        )
        .scalars()
        .all()
    )
    history = [
        {"role": str(item.role), "content": str(item.content)}
        for item in reversed(messages)
        if str(item.content or "").strip()
    ]
    return thread, history, build_conversation_context(history)


def build_conversation_context(history: list[dict[str, str]]) -> str:
    if not history:
        return ""

    lines = ["最近对话："]
    for item in history:
        if not isinstance(item, dict):
            continue
        role = _role_label(str(item.get("role", "")))
        content = _trim_text(item.get("content", ""))
        if not content:
            continue
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def history_to_messages(history: list[dict[str, str]]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "")).strip()
        content = str(item.get("content", "")).strip()
        if not role or not content:
            continue
        messages.append({"role": role, "content": content})
    return messages


def _build_message_metadata(
    *,
    result: dict[str, Any],
    conversation_context: str,
) -> dict[str, Any]:
    trace = result.get("trace")
    debug_payload = result.get("debug")
    citations = result.get("citations", [])
    metadata: dict[str, Any] = {
        "reply": str(result.get("reply", "")).strip(),
        "noEvidence": bool(result.get("noEvidence", False)),
        "citationCount": len(citations) if isinstance(citations, list) else 0,
        "conversationContext": conversation_context,
    }
    if isinstance(debug_payload, dict) and debug_payload:
        metadata["debugKeys"] = sorted(debug_payload.keys())
    if isinstance(trace, dict) and trace:
        metadata["traceEnabled"] = True
        metadata["traceStepCount"] = len(trace.get("steps", [])) if isinstance(trace.get("steps"), list) else 0
    graph = result.get("graph", {})
    if isinstance(graph, dict) and graph:
        metadata["graphMeta"] = result.get("graphMeta", {}) if isinstance(result.get("graphMeta"), dict) else {}
    return metadata


def save_conversation_turn(
    db: Session,
    *,
    thread: AgentConversationThread,
    user_message: str,
    assistant_result: dict[str, Any],
    intent: str = "",
    conversation_context: str = "",
) -> None:
    user_content = str(user_message or "").strip()
    assistant_content = str(assistant_result.get("reply", "")).strip()
    if not user_content and not assistant_content:
        return

    now = datetime.utcnow()
    if user_content:
        db.add(
            AgentConversationMessage(
                thread_id=thread.id,
                user_id=thread.user_id,
                workspace_id=thread.workspace_id,
                role="user",
                content=user_content,
                intent=intent or None,
                metadata_json={"conversationContext": conversation_context} if conversation_context else None,
                created_at=now,
            )
        )
        thread.last_user_message = user_content

    if assistant_content:
        assistant_metadata = _build_message_metadata(result=assistant_result, conversation_context=conversation_context)
        db.add(
            AgentConversationMessage(
                thread_id=thread.id,
                user_id=thread.user_id,
                workspace_id=thread.workspace_id,
                role="assistant",
                content=assistant_content,
                intent=intent or None,
                metadata_json=assistant_metadata,
                created_at=now,
            )
        )
        thread.last_assistant_message = assistant_content

    thread.last_intent = intent or None
    thread.last_message_at = now
    thread.turn_count = int(thread.turn_count or 0) + 1
    if assistant_content:
        thread.summary = _trim_text(assistant_content or user_content)

    clarification_question = str(assistant_result.get("clarificationQuestion", "")).strip()
    if clarification_question:
        thread.last_clarification_question = clarification_question
    elif str(intent or "").strip().lower() == "clarify" and assistant_content:
        thread.last_clarification_question = assistant_content

    db.flush()
