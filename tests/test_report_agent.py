from sqlalchemy import select
from werkzeug.security import generate_password_hash

from app.models import AnalysisReport, User
from app.report_agent import (
    analysis_report_to_payload,
    execute_report_request,
    generate_paginated_report,
    generate_report_artifact_from_source_documents,
    get_analysis_report,
    normalize_report_request,
    save_analysis_report_artifact,
)
from app.report_agent.contracts import PAGINATED_REPORT_BUNDLE_SCHEMA_VERSION
from app.report_agent.intake import intake_materials
from app.report_agent.renderers import render_bundle_html, render_bundle_markdown, render_bundle_pdf
from app.report_agent.validation import validate_bundle


def test_intake_accepts_heterogeneous_materials_and_detects_types():
    result = intake_materials(
        [
            {"title": "摘要", "contentType": "auto", "content": "收入: 120亿元。风险事件减少。"},
            {"title": "表格", "content": [{"year": "2024", "revenue": 100}, {"year": "2025", "revenue": 120}]},
            {"title": "JSON", "content": {"metric": "订单", "value": 42, "unit": "项"}},
        ]
    )

    assert [item["detectedType"] for item in result["materials"]] == ["text", "table", "metric"]
    assert result["materials"][0]["schemaVersion"] == "report_material.v1"


def test_generate_paginated_report_outputs_portable_bundle_with_toc_and_prompt_versions():
    bundle = generate_paginated_report(
        title="机器人风险机会报告",
        goal="识别政策与订单机会",
        render_style="chart_focus",
        materials=[
            {"title": "政策摘要", "content": "政策支持: 3项。订单机会增加。建议关注招投标节奏。"},
            {"title": "订单表", "content": [{"month": "1月", "orders": 10}, {"month": "2月", "orders": 18}]},
        ],
    )

    assert bundle["schemaVersion"] == PAGINATED_REPORT_BUNDLE_SCHEMA_VERSION
    assert bundle["renderProfile"]["style"] == "chart_focus"
    assert bundle["promptVersions"]["visual_designer"] == "v1"
    assert [page["pageType"] for page in bundle["pages"]][:2] == ["cover", "table_of_contents"]
    toc = bundle["pages"][1]
    assert toc["items"]
    assert all(item["pageNumber"] >= 3 for item in toc["items"])
    assert bundle["exportManifest"]["availableFormats"] == ["pdf", "html", "bundle"]


def test_visual_chart_specs_are_grounded_in_extracted_tables():
    bundle = generate_paginated_report(
        title="经营报告",
        materials=[{"title": "收入表", "content": [{"year": 2024, "revenue": 100}, {"year": 2025, "revenue": 130}]}],
    )

    table_ids = {table["tableId"] for table in bundle["semanticModel"]["tables"]}
    assert bundle["chartSpecs"]
    assert all(chart["dataRef"] in table_ids for chart in bundle["chartSpecs"])
    assert validate_bundle(bundle) == []


def test_generate_report_artifact_from_source_documents_persists_snapshot_and_preview():
    artifact = generate_report_artifact_from_source_documents(
        [
            {
                "sourceId": "source-alpha",
                "title": "石头科技近30天订单观察",
                "contentType": "markdown",
                "content": "# 石头科技\n\n收入: 120亿元。\n订单机会增加。",
            }
        ]
    )

    assert artifact is not None
    assert artifact["schemaVersion"] == "analysis_report_artifact.v1"
    assert artifact["paginatedReportBundle"]["schemaVersion"] == PAGINATED_REPORT_BUNDLE_SCHEMA_VERSION
    assert artifact["sourceSnapshot"]["documents"][0]["sourceId"] == "source-alpha"
    assert artifact["sourceSnapshot"]["documents"][0]["content"] == "# 石头科技\n\n收入: 120亿元。\n订单机会增加。"
    assert artifact["scope"]["sourceDocumentCount"] == 1
    assert artifact["preview"]
    assert "sourceModuleArtifactIds" not in artifact


def test_normalize_report_request_accepts_raw_text_and_rejects_legacy_module_fields():
    normalized_single = normalize_report_request({"sourceText": "收入: 120亿元。"})
    normalized_multi = normalize_report_request(
        {
            "documents": [
                "收入: 120亿元。",
                {"title": "订单材料", "content": "订单机会增加。"},
            ]
        }
    )

    assert normalized_single["mode"] == "generate"
    assert normalized_single["documents"][0]["content"] == "收入: 120亿元。"
    assert normalized_multi["mode"] == "generate"
    assert len(normalized_multi["documents"]) == 2
    assert normalize_report_request({"moduleArtifactIds": ["artifact-1"]}) == {}


def test_execute_report_request_generates_and_regenerates_from_source_snapshot(db_session):
    user = User(email="report-agent-generate@example.com", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()

    first_artifact = execute_report_request(
        db_session,
        user_id=user.id,
        workspace_id="ws-report-agent",
        request={
            "documents": [
                {
                    "sourceId": "doc-1",
                    "title": "机器人行业近30天摘要",
                    "content": "收入: 120亿元。订单机会增加。政策支持增强。",
                }
            ]
        },
    )
    saved_row = save_analysis_report_artifact(
        db_session,
        user_id=user.id,
        workspace_id="ws-report-agent",
        role="investor",
        conversation_id="conv-report-agent",
        artifact=first_artifact,
    )

    regenerated_artifact = execute_report_request(
        db_session,
        user_id=user.id,
        workspace_id="ws-report-agent",
        request={"reportId": saved_row.report_id},
    )

    assert first_artifact["sourceSnapshot"]["documents"][0]["content"] == regenerated_artifact["sourceSnapshot"]["documents"][0]["content"]
    assert regenerated_artifact["reportId"] != saved_row.report_id
    assert regenerated_artifact["paginatedReportBundle"]["schemaVersion"] == PAGINATED_REPORT_BUNDLE_SCHEMA_VERSION
    assert "sourceModuleArtifactIds" not in regenerated_artifact


def test_save_analysis_report_artifact_replaces_legacy_workspace_rows(db_session):
    user = User(email="report-agent-persist@example.com", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()

    legacy_row = AnalysisReport(
        report_id="legacy-report-1",
        user_id=user.id,
        workspace_id="ws-report-agent",
        role="investor",
        conversation_id="conv-report-agent",
        status="completed",
        title="历史报告",
        artifact_json={"preview": "旧预览"},
        markdown_body="旧正文",
        html_body="<p>旧正文</p>",
    )
    db_session.add(legacy_row)
    db_session.commit()

    artifact = generate_report_artifact_from_source_documents(
        [
            {
                "sourceId": "source-persist-1",
                "title": "石头科技风险分析",
                "contentType": "markdown",
                "content": "收入: 120亿元。政策机会增加。",
            }
        ]
    )

    saved_row = save_analysis_report_artifact(
        db_session,
        user_id=user.id,
        workspace_id="ws-report-agent",
        role="investor",
        conversation_id="conv-report-agent",
        artifact=artifact,
    )

    db_session.expire_all()
    deleted_legacy = db_session.execute(
        select(AnalysisReport).where(AnalysisReport.report_id == "legacy-report-1")
    ).scalar_one_or_none()
    loaded = get_analysis_report(
        db_session,
        user_id=user.id,
        workspace_id="ws-report-agent",
        report_id=saved_row.report_id,
    )
    payload = analysis_report_to_payload(loaded)

    assert deleted_legacy is None
    assert loaded is not None
    assert loaded.report_id == saved_row.report_id
    assert payload["sourceDocumentCount"] == 1
    assert payload["downloadUrls"]["pdf"].endswith("/download?format=pdf")


def test_bundle_renderers_do_not_require_report_reasoning():
    bundle = generate_paginated_report(title="渲染测试", materials=[{"title": "材料", "content": "订单: 12项。"}])

    html = render_bundle_html(bundle)
    markdown = render_bundle_markdown(bundle)
    pdf = render_bundle_pdf(bundle)

    assert "渲染测试" in html
    assert "## 目录" in markdown
    assert pdf.startswith(b"%PDF")


def test_quality_review_rejects_ungrounded_chart_specs():
    bundle = generate_paginated_report(title="图表校验", materials=[{"title": "材料", "content": "订单: 12项。"}])
    bundle["chartSpecs"] = [{"chartId": "chart_bad", "type": "line_chart", "dataRef": "missing_table"}]

    errors = validate_bundle(bundle)

    assert any(error["code"] == "ungrounded_chart" for error in errors)


def test_quality_review_rejects_internal_reader_terms():
    bundle = generate_paginated_report(title="泄露校验", materials=[{"title": "材料", "content": "订单: 12项。"}])
    bundle["pages"][2]["blocks"].append({"type": "paragraph", "text": "moduleId should not appear"})

    errors = validate_bundle(bundle)

    assert any(error["code"] == "internal_term_leakage" for error in errors)
