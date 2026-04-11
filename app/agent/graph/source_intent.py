from __future__ import annotations

_EXPLICIT_PUBLIC_WEB_HINTS = (
    "上网",
    "网上",
    "联网",
    "网页",
    "web",
    "互联网",
    "网络上",
    "上网搜索",
    "网上搜索",
    "公开信息",
    "公开资料",
)

_PRIVATE_KNOWLEDGE_HINTS = (
    "根据文档",
    "根据文件",
    "根据资料",
    "结合文档",
    "结合文件",
    "结合资料",
    "知识库",
    "上传文档",
    "上传文件",
    "内部文档",
    "内部资料",
    "workspace",
)

_FRESHNESS_HINTS = (
    "最新",
    "news",
    "today",
    "recent",
    "最近",
    "监管新闻",
)


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in tokens)


def has_explicit_public_web_intent(text: str) -> bool:
    return _contains_any(text, _EXPLICIT_PUBLIC_WEB_HINTS)


def has_private_knowledge_intent(text: str) -> bool:
    return _contains_any(text, _PRIVATE_KNOWLEDGE_HINTS)


def has_mixed_source_intent(text: str) -> bool:
    return has_explicit_public_web_intent(text) and has_private_knowledge_intent(text)


def has_fresh_public_info_intent(text: str) -> bool:
    return _contains_any(text, _FRESHNESS_HINTS)
