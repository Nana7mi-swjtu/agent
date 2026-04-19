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
