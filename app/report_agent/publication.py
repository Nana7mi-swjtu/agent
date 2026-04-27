from __future__ import annotations

from typing import Any

from .contracts import (
    PAGINATED_REPORT_BUNDLE_SCHEMA_VERSION,
    as_dict,
    clean_text,
    default_render_profile,
    prompt_versions,
    utc_now_iso,
)
from .renderers import render_bundle_pdf

REPORT_DOWNLOAD_FORMAT = "pdf"
SUPPORTED_REPORT_DOWNLOAD_FORMATS = {REPORT_DOWNLOAD_FORMAT}
PUBLISHED_REPORT_FORBIDDEN_LABELS = {
    "moduleId",
    "displayName",
    "runId",
    "moduleRunIds",
    "enabledModules",
    "analysisSessionId",
    "analysisSessionRevision",
    "traceRefs",
    "sourceIds",
    "eventIds",
    "domainOutputIds",
    "findingIds",
    "modelOutputIds",
    "assetId",
    "storageRef",
    "rawResult",
    "artifact_json",
    "analysis_reports",
}
PUBLISHED_REPORT_FORBIDDEN_PHRASES = (
    "生成阶段",
    "重新运行分析模块",
    "模块 rerun",
    "module rerun",
    "generation-stage",
    "generation stage",
    "orchestration stage",
    "内部快照字段",
    "snapshot fields",
    "internal snapshot",
    "internal trace",
)


class PublishedReportValidationError(ValueError):
    pass


def validate_published_report(*bodies: str, forbidden_values: list[str] | None = None) -> list[str]:
    text = "\n".join(str(body or "") for body in bodies)
    errors: list[str] = []
    for token in sorted(PUBLISHED_REPORT_FORBIDDEN_LABELS, key=len, reverse=True):
        if token and token in text:
            errors.append(f"internal label leaked: {token}")
    lowered = text.lower()
    for phrase in PUBLISHED_REPORT_FORBIDDEN_PHRASES:
        clean = clean_text(phrase)
        if clean and clean.lower() in lowered:
            errors.append(f"internal orchestration wording leaked: {clean}")
    for value in forbidden_values or []:
        clean = clean_text(value)
        if len(clean) >= 4 and clean in text:
            errors.append(f"internal value leaked: {clean}")
    return errors


def validate_report_pdf_bytes(pdf_bytes: bytes, *, forbidden_values: list[str] | None = None) -> list[str]:
    try:
        import fitz
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("pdf validation requires pymupdf dependency") from exc
    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        text = "\n".join(page.get_text("text") for page in document)
    return validate_published_report(text, forbidden_values=forbidden_values)


def render_report_pdf(
    artifact: dict[str, Any],
    *,
    markdown_body: str | None = None,
    forbidden_values: list[str] | None = None,
) -> bytes:
    del markdown_body
    payload = as_dict(artifact)
    paginated_bundle = as_dict(payload.get("paginatedReportBundle"))
    if not paginated_bundle:
        raise ValueError("paginated report bundle is required for PDF rendering")
    pdf_bytes = render_bundle_pdf(paginated_bundle)
    validation_errors = validate_report_pdf_bytes(pdf_bytes, forbidden_values=forbidden_values)
    if validation_errors:
        raise PublishedReportValidationError("；".join(validation_errors[:5]))
    return pdf_bytes


def render_failure_report_pdf(title: str, message: str) -> bytes:
    bundle = {
        "schemaVersion": PAGINATED_REPORT_BUNDLE_SCHEMA_VERSION,
        "reportId": "report_failure",
        "title": clean_text(title) or "报告生成失败",
        "status": "failed",
        "generatedAt": utc_now_iso(),
        "renderProfile": default_render_profile(),
        "promptVersions": prompt_versions(),
        "semanticModel": {
            "chapterOutline": [{"id": "failure_notice", "title": "说明", "origin": "system"}],
            "tables": [],
        },
        "pages": [
            {
                "id": "cover",
                "pageType": "cover",
                "title": "封面",
                "layout": "cover",
                "styleTokens": {"accentColor": "primary"},
                "blocks": [
                    {"type": "hero", "title": clean_text(title) or "报告生成失败"},
                    {"type": "subtitle", "text": "系统已阻止不安全或无效的下载版报告输出。"},
                ],
            },
            {
                "id": "table_of_contents",
                "pageType": "table_of_contents",
                "title": "目录",
                "layout": "toc",
                "styleTokens": {"accentColor": "muted"},
                "items": [{"id": "failure_notice", "title": "说明"}],
            },
            {
                "id": "failure_notice",
                "pageType": "insight",
                "title": "说明",
                "tocTitle": "说明",
                "layout": "title_text",
                "styleTokens": {"accentColor": "primary"},
                "blocks": [{"type": "paragraph", "text": clean_text(message) or "下载版报告暂不可用。"}],
            },
        ],
        "qualityFlags": [],
        "stageTrace": [],
        "exportManifest": {},
        "assets": [],
        "evidenceRefs": [],
    }
    return render_bundle_pdf(bundle)
