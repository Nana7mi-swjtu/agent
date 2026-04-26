from __future__ import annotations

import json
import re
from typing import Any

from .contracts import NORMALIZED_MATERIAL_SCHEMA_VERSION, as_dict, as_list, clean_text, drop_empty, utc_now_iso

_DATE_RE = re.compile(r"(?:20\d{2}|19\d{2})(?:[-/.年]\d{1,2})?(?:[-/.月]\d{1,2}日?)?")
_NUMBER_RE = re.compile(r"(?P<label>[\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z0-9_ -]{0,24})[:： ]+(?P<value>-?\d+(?:\.\d+)?)(?P<unit>%|亿元|万元|元|家|个|次|项)?")


def _parse_json_text(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return None


def _table_from_content(content: Any) -> dict[str, Any] | None:
    rows = []
    columns = []
    if isinstance(content, list) and all(isinstance(item, dict) for item in content):
        rows = content[:50]
        keys = []
        for row in rows:
            for key in row.keys():
                if key not in keys:
                    keys.append(key)
        columns = [{"key": clean_text(key), "label": clean_text(key)} for key in keys[:12]]
    elif isinstance(content, dict):
        raw_rows = content.get("rows")
        raw_columns = content.get("columns")
        if isinstance(raw_rows, list):
            rows = [item for item in raw_rows if isinstance(item, dict)][:50]
        if isinstance(raw_columns, list):
            for item in raw_columns[:12]:
                if isinstance(item, dict):
                    key = clean_text(item.get("key") or item.get("name") or item.get("label"))
                    if key:
                        columns.append({"key": key, "label": clean_text(item.get("label") or key)})
                else:
                    key = clean_text(item)
                    if key:
                        columns.append({"key": key, "label": key})
        if rows and not columns:
            columns = [{"key": key, "label": key} for key in list(rows[0].keys())[:12]]
    if not rows or not columns:
        return None
    return {"columns": columns, "rows": rows}


def _extract_metrics(text: str, material_id: str) -> list[dict[str, Any]]:
    metrics = []
    for match in _NUMBER_RE.finditer(text[:3000]):
        label = clean_text(match.group("label"), limit=40)
        if not label:
            continue
        metrics.append(
            {
                "metricId": f"metric_{material_id}_{len(metrics) + 1}",
                "label": label,
                "value": float(match.group("value")),
                "unit": clean_text(match.group("unit")),
                "sourceMaterialId": material_id,
            }
        )
        if len(metrics) >= 8:
            break
    return metrics


def _extract_findings(text: str, material: dict[str, Any]) -> list[dict[str, Any]]:
    material_id = clean_text(material.get("materialId"))
    title = clean_text(material.get("title"), limit=80)
    chunks = [item.strip(" -•\t") for item in re.split(r"[。；;\n]+", text) if clean_text(item)]
    findings = []
    for chunk in chunks[:6]:
        clean = clean_text(chunk, limit=220)
        if len(clean) < 8:
            continue
        findings.append(
            {
                "findingId": f"finding_{material_id}_{len(findings) + 1}",
                "title": title or "材料要点",
                "summary": clean,
                "sourceMaterialId": material_id,
                "evidenceRefs": [f"evidence_{material_id}_1"],
                "confidence": 0.74,
            }
        )
    return findings[:5]


def _material_text(material: dict[str, Any]) -> str:
    content = material.get("content")
    if isinstance(content, str):
        parsed = _parse_json_text(content)
        if isinstance(parsed, (dict, list)):
            return json.dumps(parsed, ensure_ascii=False)
        return content
    if isinstance(content, (dict, list)):
        return json.dumps(content, ensure_ascii=False)
    return clean_text(content)


def normalize_materials(materials: list[dict[str, Any]]) -> dict[str, Any]:
    normalized_materials = []
    findings = []
    metrics = []
    tables = []
    evidence_refs = []
    visual_opportunities = []
    quality_flags = []
    entities = []
    time_ranges = []
    for material in materials:
        material_id = clean_text(material.get("materialId"))
        detected_type = clean_text(material.get("detectedType")) or "text"
        text = _material_text(material)
        table = _table_from_content(material.get("content"))
        if table:
            table_id = f"table_{material_id}_1"
            table_payload = {
                "tableId": table_id,
                "title": clean_text(material.get("title"), limit=80) or "数据表",
                "columns": table["columns"],
                "rows": table["rows"],
                "sourceMaterialId": material_id,
            }
            tables.append(table_payload)
            numeric_columns = [c["key"] for c in table["columns"] if any(isinstance(row.get(c["key"]), (int, float)) for row in table["rows"])]
            if numeric_columns:
                visual_opportunities.append(
                    {
                        "opportunityId": f"visual_{material_id}_1",
                        "type": "bar_chart",
                        "title": table_payload["title"],
                        "dataRef": table_id,
                        "reason": "table_contains_numeric_columns",
                        "sourceMaterialId": material_id,
                    }
                )
        material_metrics = _extract_metrics(text, material_id)
        metrics.extend(material_metrics)
        material_findings = _extract_findings(text, material)
        findings.extend(material_findings)
        if material_findings or table or material_metrics:
            evidence_refs.append(
                {
                    "evidenceId": f"evidence_{material_id}_1",
                    "title": clean_text(material.get("title"), limit=100) or material_id,
                    "summary": clean_text(text, limit=260),
                    "sourceMaterialId": material_id,
                }
            )
        else:
            quality_flags.append({"code": "no_report_worthy_content", "severity": "info", "materialId": material_id})
        dates = [clean_text(item) for item in _DATE_RE.findall(text)]
        if dates:
            time_ranges.extend(dates[:3])
        normalized_materials.append(
            {
                "schemaVersion": NORMALIZED_MATERIAL_SCHEMA_VERSION,
                "materialId": material_id,
                "title": clean_text(material.get("title"), limit=120),
                "detectedType": detected_type,
                "contains": [
                    name
                    for name, present in {
                        "findings": bool(material_findings),
                        "metrics": bool(material_metrics),
                        "table": bool(table),
                        "evidence": bool(material_findings or table or material_metrics),
                    }.items()
                    if present
                ],
                "confidence": 0.82 if material_findings or table or material_metrics else 0.35,
            }
        )
    semantic_model = drop_empty(
        {
            "schemaVersion": "paginated_report_semantic_model.v1",
            "createdAt": utc_now_iso(),
            "materials": normalized_materials,
            "findings": findings[:20],
            "metrics": metrics[:20],
            "tables": tables[:12],
            "evidenceRefs": evidence_refs[:30],
            "visualOpportunities": visual_opportunities[:12],
            "entities": entities,
            "timeRanges": sorted(set(time_ranges))[:8],
            "qualityFlags": quality_flags,
        }
    )
    return {"semanticModel": semantic_model, "qualityFlags": quality_flags}