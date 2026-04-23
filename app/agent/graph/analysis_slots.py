from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


VALUE_KIND_TEXT = "text"
VALUE_KIND_SINGLE_CHOICE = "single_choice"
VALUE_KIND_MULTI_CHOICE = "multi_choice"
VALUE_KIND_BOOLEAN = "boolean"

NORMALIZER_PASSTHROUGH_TEXT = "passthrough_text"
NORMALIZER_ENTERPRISE_NAME = "enterprise_name"
NORMALIZER_STOCK_CODE = "stock_code"
NORMALIZER_TIME_RANGE = "time_range"
NORMALIZER_CHOICE_TAGS = "choice_tags"
NORMALIZER_REGION = "region"

SCOPE_SHARED = "shared"
SCOPE_MODULE = "module"

SHARED_ENTERPRISE_NAME = "enterprise_name"
SHARED_STOCK_CODE = "stock_code"
SHARED_TIME_RANGE = "time_range"
SHARED_REPORT_GOAL = "report_goal"
SHARED_ANALYSIS_FOCUS_TAGS = "analysis_focus_tags"
SHARED_REGION_SCOPE = "region_scope"

_SPLIT_PATTERN = re.compile(r"[,\n\r\t;|/，、；]+")
_STOCK_CODE_PATTERN = re.compile(r"(?<!\d)(\d{6})(?!\d)")
_REQUEST_PREFIX_PATTERN = re.compile(
    r"^(?:请|麻烦|帮我|帮忙|可以)?(?:生成|出具|写|做|分析|查看|评估|开始|继续|改成|改为|调整为|更新为|换成)?",
)
_CONTEXT_MARKERS = (
    "时间范围",
    "报告目标",
    "分析目标",
    "分析重点",
    "关注重点",
    "区域范围",
    "时间",
    "目标",
    "重点",
    "关注",
    "聚焦",
    "区域",
    "模块",
    "功能",
)
_CONTEXT_MARKER_PATTERN = re.compile(
    r"(?:" + "|".join(re.escape(marker) for marker in sorted(_CONTEXT_MARKERS, key=len, reverse=True)) + r")\s*(?:是|为|:|：)?"
)
_TIME_RANGE_PATTERN = re.compile(
    r"(?:近\s*\d+\s*(?:天|日|周|个月|月|年)|过去\s*\d+\s*(?:天|日|周|个月|月|年)|"
    r"本(?:周|月|季度|季|年)|上(?:周|月|季度|季|年)|"
    r"\d{4}[-/年]\d{1,2}(?:[-/月]\d{1,2}日?)?(?:\s*(?:至|到|-|~)\s*\d{4}[-/年]\d{1,2}(?:[-/月]\d{1,2}日?)?)?)"
)


@dataclass(frozen=True)
class AnalysisSlotOption:
    value: str
    label: str


@dataclass(frozen=True)
class AnalysisSlotDefinition:
    slot_id: str
    label: str
    scope: str
    value_kind: str
    normalizer: str
    group_id: str
    priority: int
    depends_on: tuple[str, ...] = field(default_factory=tuple)
    prompt_hint: str = ""
    options: tuple[AnalysisSlotOption, ...] = field(default_factory=tuple)
    module_id: str = ""


def shared_slot_catalog() -> dict[str, AnalysisSlotDefinition]:
    return {
        SHARED_ENTERPRISE_NAME: AnalysisSlotDefinition(
            slot_id=SHARED_ENTERPRISE_NAME,
            label="企业名称",
            scope=SCOPE_SHARED,
            value_kind=VALUE_KIND_TEXT,
            normalizer=NORMALIZER_ENTERPRISE_NAME,
            group_id="enterprise_identity",
            priority=10,
            prompt_hint="请提供需要分析的企业名称，如有股票代码可一并补充。",
        ),
        SHARED_STOCK_CODE: AnalysisSlotDefinition(
            slot_id=SHARED_STOCK_CODE,
            label="股票代码",
            scope=SCOPE_SHARED,
            value_kind=VALUE_KIND_TEXT,
            normalizer=NORMALIZER_STOCK_CODE,
            group_id="enterprise_identity",
            priority=10,
            prompt_hint="如企业已上市，可补充 6 位股票代码。",
        ),
        SHARED_TIME_RANGE: AnalysisSlotDefinition(
            slot_id=SHARED_TIME_RANGE,
            label="时间范围",
            scope=SCOPE_SHARED,
            value_kind=VALUE_KIND_TEXT,
            normalizer=NORMALIZER_TIME_RANGE,
            group_id="time_range",
            priority=20,
            prompt_hint="例如：近30天、近90天、2026-01-01 至 2026-03-31。",
        ),
        SHARED_REPORT_GOAL: AnalysisSlotDefinition(
            slot_id=SHARED_REPORT_GOAL,
            label="报告目标",
            scope=SCOPE_SHARED,
            value_kind=VALUE_KIND_TEXT,
            normalizer=NORMALIZER_PASSTHROUGH_TEXT,
            group_id="report_goal",
            priority=30,
            prompt_hint="说明你希望这份分析最后服务什么目标。",
        ),
        SHARED_ANALYSIS_FOCUS_TAGS: AnalysisSlotDefinition(
            slot_id=SHARED_ANALYSIS_FOCUS_TAGS,
            label="分析重点",
            scope=SCOPE_SHARED,
            value_kind=VALUE_KIND_MULTI_CHOICE,
            normalizer=NORMALIZER_CHOICE_TAGS,
            group_id="analysis_focus",
            priority=40,
            prompt_hint="可填写多个重点，例如：政策、订单、竞争、供应链。",
            options=(
                AnalysisSlotOption(value="政策", label="政策"),
                AnalysisSlotOption(value="公告", label="公告"),
                AnalysisSlotOption(value="招中标", label="招中标"),
                AnalysisSlotOption(value="竞争", label="竞争"),
                AnalysisSlotOption(value="订单", label="订单"),
                AnalysisSlotOption(value="供应链", label="供应链"),
            ),
        ),
        SHARED_REGION_SCOPE: AnalysisSlotDefinition(
            slot_id=SHARED_REGION_SCOPE,
            label="区域范围",
            scope=SCOPE_SHARED,
            value_kind=VALUE_KIND_MULTI_CHOICE,
            normalizer=NORMALIZER_REGION,
            group_id="region_scope",
            priority=50,
            prompt_hint="如需要限定区域，可补充国家、省份或城市。",
        ),
    }


def normalize_slot_value(definition: AnalysisSlotDefinition, raw_value: Any) -> Any:
    if raw_value in (None, "", [], {}):
        return None
    normalizer = definition.normalizer
    if normalizer == NORMALIZER_ENTERPRISE_NAME:
        return _normalize_enterprise_name(raw_value)
    if normalizer == NORMALIZER_STOCK_CODE:
        return _normalize_stock_code(raw_value)
    if normalizer == NORMALIZER_TIME_RANGE:
        return _normalize_time_range(raw_value)
    if normalizer == NORMALIZER_CHOICE_TAGS:
        return _normalize_choice_tags(raw_value, definition=definition)
    if normalizer == NORMALIZER_REGION:
        return _normalize_region(raw_value)
    return _normalize_by_kind(raw_value, definition=definition)


def has_slot_value(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value)
    if isinstance(value, dict):
        return bool(value)
    return value is not None


def slot_label(slot_catalog: dict[str, AnalysisSlotDefinition], slot_id: str) -> str:
    definition = slot_catalog.get(slot_id)
    return definition.label if definition is not None else slot_id


def parse_answer_for_group(
    *,
    slot_ids: list[str],
    slot_catalog: dict[str, AnalysisSlotDefinition],
    user_message: str,
) -> dict[str, Any]:
    message = str(user_message or "").strip()
    if not message:
        return {}
    if "enterprise_identity" in {slot_catalog.get(slot_id).group_id for slot_id in slot_ids if slot_catalog.get(slot_id)}:
        return _parse_enterprise_identity_answer(slot_ids=slot_ids, slot_catalog=slot_catalog, message=message)
    updates: dict[str, Any] = {}
    for slot_id in slot_ids:
        definition = slot_catalog.get(slot_id)
        if definition is None:
            continue
        normalized = normalize_slot_value(definition, message)
        if has_slot_value(normalized):
            updates[slot_id] = normalized
    return updates


def parse_compound_answer_for_slots(
    *,
    slot_ids: list[str],
    slot_catalog: dict[str, AnalysisSlotDefinition],
    user_message: str,
) -> dict[str, Any]:
    """Extract multiple shared slots from one natural-language answer.

    This stays intentionally conservative: only labelled/contextual fragments are
    consumed beyond enterprise identity, so follow-up answers like "改成近90天"
    do not overwrite an already clean enterprise slot.
    """
    message = str(user_message or "").strip()
    if not message:
        return {}
    available = set(slot_ids)
    updates: dict[str, Any] = {}

    if {SHARED_ENTERPRISE_NAME, SHARED_STOCK_CODE}.intersection(available):
        identity_updates = _parse_enterprise_identity_answer(
            slot_ids=[slot_id for slot_id in (SHARED_ENTERPRISE_NAME, SHARED_STOCK_CODE) if slot_id in available],
            slot_catalog=slot_catalog,
            message=message,
        )
        updates.update(identity_updates)

    if SHARED_TIME_RANGE in available:
        time_definition = slot_catalog.get(SHARED_TIME_RANGE)
        time_value = _extract_labeled_segment(message, ("时间范围", "时间")) or _extract_time_range(message)
        if time_definition is not None:
            normalized = normalize_slot_value(time_definition, time_value)
            if has_slot_value(normalized):
                updates[SHARED_TIME_RANGE] = normalized

    if SHARED_REPORT_GOAL in available:
        goal_definition = slot_catalog.get(SHARED_REPORT_GOAL)
        goal_value = _extract_labeled_segment(message, ("报告目标", "分析目标", "目标"))
        if goal_definition is not None:
            normalized = normalize_slot_value(goal_definition, goal_value)
            if has_slot_value(normalized):
                updates[SHARED_REPORT_GOAL] = normalized

    if SHARED_ANALYSIS_FOCUS_TAGS in available:
        focus_definition = slot_catalog.get(SHARED_ANALYSIS_FOCUS_TAGS)
        focus_value = _extract_labeled_segment(message, ("分析重点", "关注重点", "重点", "关注", "聚焦"))
        if focus_definition is not None:
            normalized = normalize_slot_value(focus_definition, _normalize_focus_text(focus_value))
            if has_slot_value(normalized):
                updates[SHARED_ANALYSIS_FOCUS_TAGS] = normalized

    if SHARED_REGION_SCOPE in available:
        region_definition = slot_catalog.get(SHARED_REGION_SCOPE)
        region_value = _extract_labeled_segment(message, ("区域范围", "区域"))
        if region_definition is not None:
            normalized = normalize_slot_value(region_definition, region_value)
            if has_slot_value(normalized):
                updates[SHARED_REGION_SCOPE] = normalized

    return updates


def _parse_enterprise_identity_answer(
    *,
    slot_ids: list[str],
    slot_catalog: dict[str, AnalysisSlotDefinition],
    message: str,
) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    stock_match = _STOCK_CODE_PATTERN.search(message)
    enterprise_text = message
    if stock_match:
        enterprise_text = (message[: stock_match.start()] + " " + message[stock_match.end() :]).strip(" ,，、")
        if SHARED_STOCK_CODE in slot_ids:
            stock_definition = slot_catalog.get(SHARED_STOCK_CODE)
            if stock_definition is not None:
                stock_value = normalize_slot_value(stock_definition, stock_match.group(1))
                if has_slot_value(stock_value):
                    updates[SHARED_STOCK_CODE] = stock_value
    if SHARED_ENTERPRISE_NAME in slot_ids:
        enterprise_definition = slot_catalog.get(SHARED_ENTERPRISE_NAME)
        if enterprise_definition is not None:
            enterprise_value = normalize_slot_value(enterprise_definition, enterprise_text or message)
            if has_slot_value(enterprise_value):
                updates[SHARED_ENTERPRISE_NAME] = enterprise_value
    return updates


def _normalize_enterprise_name(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    match = _STOCK_CODE_PATTERN.search(text)
    if match:
        text = (text[: match.start()] + " " + text[match.end() :]).strip(" ,，、")
    text = _strip_enterprise_context(text)
    return text or None


def _normalize_stock_code(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    match = _STOCK_CODE_PATTERN.search(text)
    if match:
        return match.group(1)
    return None


def _normalize_time_range(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _normalize_choice_tags(value: Any, *, definition: AnalysisSlotDefinition) -> list[str]:
    values = _string_items(value)
    allowed_values = {option.value for option in definition.options}
    allowed_labels = {option.label: option.value for option in definition.options}
    result: list[str] = []
    for item in values:
        canonical = allowed_labels.get(item, item)
        if allowed_values and canonical not in allowed_values:
            canonical = item
        if canonical and canonical not in result:
            result.append(canonical)
    return result


def _normalize_region(value: Any) -> list[str]:
    result: list[str] = []
    for item in _string_items(value):
        if item and item not in result:
            result.append(item)
    return result


def _normalize_by_kind(value: Any, *, definition: AnalysisSlotDefinition) -> Any:
    if definition.value_kind == VALUE_KIND_BOOLEAN:
        return _normalize_boolean(value)
    if definition.value_kind == VALUE_KIND_MULTI_CHOICE:
        return _string_items(value)
    if definition.value_kind == VALUE_KIND_SINGLE_CHOICE:
        items = _string_items(value)
        return items[0] if items else None
    text = str(value or "").strip()
    return text or None


def _normalize_boolean(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"true", "1", "yes", "y", "是", "开启", "开"}:
        return True
    if text in {"false", "0", "no", "n", "否", "关闭", "关"}:
        return False
    return None


def _string_items(value: Any) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = _SPLIT_PATTERN.split(str(value or ""))
    result: list[str] = []
    for item in raw_items:
        clean = str(item or "").strip()
        if clean and clean not in result:
            result.append(clean)
    return result


def _strip_enterprise_context(value: str) -> str:
    text = str(value or "").strip(" ,，、；;。")
    if not text:
        return ""
    text = _REQUEST_PREFIX_PATTERN.sub("", text, count=1).strip(" ,，、；;。")
    cut_points: list[int] = []
    marker_match = _CONTEXT_MARKER_PATTERN.search(text)
    if marker_match:
        cut_points.append(marker_match.start())
    time_match = _TIME_RANGE_PATTERN.search(text)
    if time_match:
        cut_points.append(time_match.start())
    if cut_points:
        text = text[: min(cut_points)]
    text = re.sub(r"(?:的)?(?:定制化)?(?:分析)?(?:报告|简报|研报|洞察)$", "", text).strip(" ,，、；;。")
    if text in {"改成", "改为", "调整为", "更新为", "换成", "生成", "分析", "请生成", "请分析"}:
        return ""
    return text


def _extract_labeled_segment(message: str, labels: tuple[str, ...]) -> str:
    text = str(message or "").strip()
    if not text:
        return ""
    label_pattern = re.compile(
        r"(?:" + "|".join(re.escape(label) for label in sorted(labels, key=len, reverse=True)) + r")\s*(?:是|为|:|：)?"
    )
    match = label_pattern.search(text)
    if not match:
        return ""
    start = match.end()
    end = len(text)
    marker_match = _CONTEXT_MARKER_PATTERN.search(text, start)
    if marker_match:
        end = min(end, marker_match.start())
    separator_match = re.search(r"[；;\n\r]", text[start:end])
    if separator_match:
        end = min(end, start + separator_match.start())
    return text[start:end].strip(" ,，、；;。")


def _extract_time_range(message: str) -> str:
    match = _TIME_RANGE_PATTERN.search(str(message or ""))
    return match.group(0).replace(" ", "") if match else ""


def _normalize_focus_text(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return re.sub(r"(?<=[\u4e00-\u9fff])(?:和|与|及)(?=[\u4e00-\u9fff])", "、", text)
