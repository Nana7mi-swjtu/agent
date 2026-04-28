import json
import os
from pathlib import Path

import pytest
from dotenv import load_dotenv
from sqlalchemy import select, text
from werkzeug.security import generate_password_hash

from app import create_app
from app.db import get_session
from app.models import AnalysisReport, User
from app.report_agent import (
    ReportGenerationError,
    analysis_report_to_payload,
    execute_report_request,
    generate_paginated_report,
    generate_report_artifact_from_source_documents,
    get_analysis_report,
    normalize_report_request,
    save_analysis_report_artifact,
)
from app.report_agent.bundle import _review_block_snapshot
from app.report_agent.contracts import PAGINATED_REPORT_BUNDLE_SCHEMA_VERSION
from app.report_agent.intake import intake_materials
from app.report_agent.renderers import render_bundle_html, render_bundle_markdown, render_bundle_pdf
from app.report_agent.renderers.html import PDF_TARGET, build_bundle_render_package
from app.report_agent.validation import validate_bundle

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


class _FakeReportWriter:
    def __init__(self, *, reject_review: bool = False, omit_table_visuals: bool = False):
        self.reject_review = reject_review
        self.omit_table_visuals = omit_table_visuals

    def invoke(self, messages):
        payload = json.loads(messages[-1]["content"])
        stage_id = payload["stageId"]
        if stage_id == "intake":
            return {
                "title": payload["context"]["title"] or "智能分析报告",
                "materials": [
                    {
                        "materialId": item["materialId"],
                        "title": item["title"],
                        "detectedType": item["detectedType"] or "text",
                        "reportUse": "primary" if index == 0 else "supporting",
                        "summary": f"材料 {index + 1} 提供可进入正式报告的核心信息。",
                    }
                    for index, item in enumerate(payload.get("materials", []))
                ],
                "qualityFlags": [],
            }
        if stage_id == "normalization":
            seed = payload["seed"]["semanticModel"]
            findings = [
                {
                    "title": item.get("title") or "关键发现",
                    "summary": item.get("summary") or "材料支持这一判断。",
                    "basisSummary": item.get("summary") or "材料支持这一判断。",
                    "evidenceRefs": item.get("evidenceRefs", []),
                }
                for item in seed.get("findings", [])[:4]
            ]
            if not findings:
                findings = [{"title": "材料概览", "summary": "当前材料可形成正式报告。", "basisSummary": "输入材料明确。", "evidenceRefs": []}]
            visual_opportunities = seed.get("visualOpportunities", [])
            first_visual = visual_opportunities[0] if visual_opportunities else {}
            return {
                "semanticModel": {
                    "title": payload["context"]["title"],
                    "scope": {"analysisFocus": payload["context"].get("goal", ""), "timeRange": ""},
                    "presentationDecisions": {"exposeEvidencePage": False},
                    "executiveJudgements": [
                        {
                            "title": "核心判断",
                            "summary": findings[0]["summary"],
                            "basisSummary": findings[0]["basisSummary"],
                            "interpretationBoundary": "仅基于当前输入材料。",
                            "evidenceRefs": findings[0].get("evidenceRefs", []),
                        }
                    ],
                    "keyFindings": findings,
                    "recommendations": [
                        {
                            "title": "复核重点",
                            "summary": "建议优先复核关键发现对应的原始数据与业务上下文。",
                            "basisSummary": findings[0]["summary"],
                            "interpretationBoundary": "建议只覆盖当前材料范围。",
                        }
                    ],
                    "visualNarratives": [
                        {
                            "title": first_visual.get("title") or "经营趋势",
                            "summary": "图表用于帮助读者快速理解结构化数据，并辅助正文说明趋势与结构差异。",
                            "chartId": first_visual.get("opportunityId", ""),
                            "dataRef": first_visual.get("dataRef", ""),
                            "interpretationBoundary": "图表只反映输入表格中的数据。",
                        }
                    ]
                    if first_visual
                    else [],
                    "visualOpportunities": visual_opportunities,
                    "entities": [],
                    "timeRanges": seed.get("timeRanges", []),
                    "qualityFlags": [],
                },
                "qualityFlags": [],
            }
        if stage_id == "page_planning":
            chapters = [
                {
                    "chapterId": "chapter_summary",
                    "title": "执行摘要",
                    "pageType": "executive_summary",
                    "layout": "title_text",
                    "sectionIds": ["executive_judgement"],
                }
            ]
            semantic_model = payload["semanticModel"]
            if semantic_model.get("keyFindings"):
                chapters.append(
                    {
                        "chapterId": "chapter_findings",
                        "title": "关键发现",
                        "pageType": "insight",
                        "layout": "title_text",
                        "sectionIds": ["key_findings"],
                    }
                )
            chart_refs = [item.get("opportunityId", "") for item in semantic_model.get("visualOpportunities", []) if item.get("opportunityId")]
            table_refs = [item.get("tableId", "") for item in semantic_model.get("tables", []) if item.get("tableId")]
            if chart_refs or table_refs:
                chapters.append(
                    {
                        "chapterId": "chapter_data",
                        "title": "趋势与结构观察",
                        "pageType": "chart_analysis" if chart_refs else "table_analysis",
                        "layout": "title_chart_notes" if chart_refs else "title_table_notes",
                        "sectionIds": ["model_visual_interpretation"],
                        "chartRefs": chart_refs,
                        "tableRefs": table_refs,
                    }
                )
            if semantic_model.get("presentationDecisions", {}).get("exposeEvidencePage"):
                chapters.append(
                    {
                        "chapterId": "chapter_evidence",
                        "title": "证据与来源",
                        "pageType": "evidence",
                        "layout": "evidence_list",
                        "sectionIds": ["evidence_verification"],
                    }
                )
            chapters.append(
                {
                    "chapterId": "chapter_recommendations",
                    "title": "建议与行动",
                    "pageType": "recommendation",
                    "layout": "title_text",
                    "sectionIds": ["recommendations"],
                }
            )
            return {"chapters": chapters, "qualityFlags": []}
        if stage_id == "visual_design":
            chapter_plan = payload["chapterPlan"]
            chart_specs = payload["seed"]["chartSpecs"]
            return {
                "pageDesigns": [
                    {
                        "chapterId": item["chapterId"],
                        "layout": item["layout"],
                        "styleTokens": {"accentColor": "primary" if item["pageType"] != "recommendation" else "success"},
                        "chartRefs": item.get("chartRefs", []),
                        "tableRefs": item.get("tableRefs", []),
                        "caption": "视觉说明由报告生成链统一编排。",
                    }
                    for item in chapter_plan
                ],
                "chartSpecs": chart_specs,
                "qualityFlags": [],
            }
        if stage_id == "writing":
            packet = payload["writingPacket"]
            evidence_items = packet.get("来源与核验", [])
            planned_chart_refs = []
            planned_table_refs = []
            include_evidence_section = False
            for chapter in payload.get("chapterPlan", []):
                if "evidence_verification" in chapter.get("sectionIds", []):
                    include_evidence_section = True
                for ref in chapter.get("chartRefs", []):
                    if ref and ref not in planned_chart_refs:
                        planned_chart_refs.append(ref)
                for ref in chapter.get("tableRefs", []):
                    if ref and ref not in planned_table_refs:
                        planned_table_refs.append(ref)
            chart_registry = {item.get("chartId", ""): item for item in packet.get("图表规划", []) if item.get("chartId")}
            table_registry = {item.get("tableId", ""): item for item in packet.get("数据表", []) if item.get("tableId")}
            chart_items = [
                {
                    "title": chart_registry.get(ref, {}).get("title") or "趋势图",
                    "chartId": ref,
                    "dataRef": chart_registry.get(ref, {}).get("dataRef", ""),
                    "readerSummary": (
                        f"{chart_registry.get(ref, {}).get('title') or '该图表'}围绕当前材料中最关键的趋势与结构变化展开，"
                        "先帮助读者识别主要上升、分化或波动区间，再把这些变化与正文判断对应起来。"
                        "如果后续经营节奏、区域结构或产品表现继续偏离当前轨迹，读者应优先复核与该图相关的关键数字和阶段变化。"
                    ),
                }
                for ref in planned_chart_refs[:4]
            ]
            table_items = []
            if not self.omit_table_visuals:
                table_items = [
                    {
                        "title": table_registry.get(ref, {}).get("title") or "关键数据摘录",
                        "dataRef": ref,
                        "readerSummary": (
                            f"{table_registry.get(ref, {}).get('title') or '该数据表'}补充了支撑当前判断的关键数值，"
                            "可以帮助读者核对样本差异、变化幅度以及图表中没有完全展开的明细字段。"
                            "如果需要进一步确认结论边界，应优先回看这些数值在不同对象或时间段上的分布情况。"
                        ),
                    }
                    for ref in planned_table_refs[:4]
                ]
            sections = [
                {
                    "id": "executive_judgement",
                    "title": "核心判断",
                    "blocks": [
                        {"type": "paragraph", "text": "这份报告围绕当前材料中最重要的变化、结构关系与行动重点展开。"},
                        {"type": "paragraph", "text": "正文只承接已提供材料可以支撑的事实与判断，不额外补造数字、来源或趋势外推。"},
                    ],
                },
                {
                    "id": "key_findings",
                    "title": "关键发现",
                    "blocks": [
                        {"type": "paragraph", "text": "关键发现章节用于集中呈现材料中最值得读者优先关注的经营变化与结构特征。"},
                        {"type": "items", "items": packet.get("关键发现", [])[:3]},
                    ],
                },
                {
                    "id": "model_visual_interpretation",
                    "title": "趋势与结构观察",
                    "blocks": [
                        {"type": "paragraph", "text": "相关图表与数据摘录共同呈现了经营变化的方向、结构差异及其与正文判断的对应关系。"},
                        {"type": "paragraph", "text": "图表负责概括走势与对比关系，数据表补充关键数值和样本差异，两者共同服务读者理解。"},
                        {"type": "visuals", "items": [*chart_items, *table_items]},
                    ],
                },
                {
                    "id": "recommendations",
                    "title": "建议与行动",
                    "blocks": [
                        {"type": "paragraph", "text": "建议部分面向读者提供可执行的优先动作，而不是重复材料清单。"},
                        {"type": "items", "items": packet.get("建议", [])[:3]},
                    ],
                },
            ]
            if include_evidence_section:
                sections.insert(
                    2,
                    {
                        "id": "evidence_verification",
                        "title": "证据与来源",
                        "blocks": [{"type": "evidence", "items": evidence_items[:4]}],
                    },
                )
            return {"title": packet.get("报告标题") or "正式报告", "sections": sections, "qualityFlags": []}
        if stage_id == "quality_review":
            return {
                "approved": not self.reject_review,
                "summary": "审查通过" if not self.reject_review else "审查未通过",
                "qualityFlags": [] if not self.reject_review else [{"code": "review_failed", "severity": "error", "message": "存在阻断问题"}],
            }
        raise AssertionError(f"unexpected stage: {stage_id}")


def _writer() -> _FakeReportWriter:
    return _FakeReportWriter()


class _RetryingReportWriter(_FakeReportWriter):
    def __init__(self):
        super().__init__()
        self.writing_calls = 0

    def invoke(self, messages):
        payload = json.loads(messages[-1]["content"])
        if payload["stageId"] == "writing":
            self.writing_calls += 1
            response = super().invoke(messages)
            if self.writing_calls == 1:
                for section in response.get("sections", []):
                    if section.get("id") != "model_visual_interpretation":
                        continue
                    for block in section.get("blocks", []):
                        if block.get("type") != "visuals":
                            continue
                        block["items"] = [item for item in block.get("items", []) if not item.get("chartId")]
            return response
        return super().invoke(messages)


class _TableLabelingReportWriter(_FakeReportWriter):
    def invoke(self, messages):
        payload = json.loads(messages[-1]["content"])
        response = super().invoke(messages)
        if payload["stageId"] != "normalization":
            return response
        tables = payload.get("seed", {}).get("semanticModel", {}).get("tables", [])
        table_labels = []
        for table in tables:
            table_id = table.get("tableId")
            if not table_id:
                continue
            columns = []
            for column in table.get("columns", []):
                key = column.get("key")
                if key == "revenue_billion":
                    columns.append({"key": key, "label": "收入（十亿）"})
                elif key == "new_orders":
                    columns.append({"key": key, "label": "新增订单量"})
                elif key == "capacity_utilization_pct":
                    columns.append({"key": key, "label": "产能利用率"})
            if columns:
                table_labels.append({"tableId": table_id, "columns": columns})
        response.setdefault("semanticModel", {})["tableLabels"] = table_labels
        return response


class _SubsectionPlanningReportWriter(_FakeReportWriter):
    def invoke(self, messages):
        payload = json.loads(messages[-1]["content"])
        response = super().invoke(messages)
        if payload["stageId"] != "page_planning":
            return response
        for chapter in response.get("chapters", []):
            if chapter.get("chapterId") != "chapter_data":
                continue
            chart_refs = chapter.get("chartRefs", [])
            chapter["subsections"] = [
                {"title": "月度经营趋势", "chartRefs": chart_refs[:1], "sectionIds": ["model_visual_interpretation"]},
                {"title": "区域收入结构", "chartRefs": chart_refs[1:2], "sectionIds": ["model_visual_interpretation"]},
            ]
        return response


@pytest.fixture
def db_session():
    test_db_url = os.getenv("TEST_DATABASE_URL")
    if not test_db_url:
        pytest.skip("TEST_DATABASE_URL is required for MySQL tests")
    if not test_db_url.startswith("mysql"):
        pytest.skip("TEST_DATABASE_URL must be a MySQL connection string")

    tmp_root = Path("C:/vscode/AIProjectTest/agent/.tmp/test_report_agent_fixture")
    session_dir = tmp_root / "sessions"
    rag_upload_dir = tmp_root / "rag_uploads"
    rag_chroma_dir = tmp_root / "chromadb"
    bankruptcy_upload_dir = tmp_root / "bankruptcy_csv"
    bankruptcy_plot_dir = tmp_root / "bankruptcy_plots"
    log_dir = tmp_root / "logs"
    for path in (session_dir, rag_upload_dir, rag_chroma_dir, bankruptcy_upload_dir, bankruptcy_plot_dir, log_dir):
        path.mkdir(parents=True, exist_ok=True)

    app = create_app(
        {
            "DATABASE_URL": test_db_url,
            "AUTO_CREATE_DB": True,
            "TESTING": True,
            "LOG_DIR": str(log_dir),
            "LOG_LEVEL": "INFO",
            "LOG_SERVICE_NAME": "agent-test",
            "LOG_ENVIRONMENT": "test",
            "LOG_MAX_BYTES": 1024 * 1024,
            "LOG_BACKUP_COUNT": 2,
            "EMAIL_BACKEND": "memory",
            "SESSION_TYPE": "filesystem",
            "SESSION_FILE_DIR": str(session_dir),
            "SECRET_KEY": "test-secret",
            "CORS_ENABLED": True,
            "CORS_ALLOWED_ORIGINS": ("http://localhost:4273",),
            "CORS_ALLOW_CREDENTIALS": True,
            "RAG_EMBEDDER_PROVIDER": "fake",
            "RAG_EMBEDDING_MODEL": "fake-embeddings",
            "RAG_EMBEDDING_VERSION": "1",
            "RAG_EMBEDDING_DIMENSION": 8,
            "RAG_EMBEDDING_API_KEY": "",
            "RAG_RERANKER_PROVIDER": "fake",
            "RAG_RERANKER_MODEL": "",
            "RAG_UPLOAD_DIR": str(rag_upload_dir),
            "RAG_ALLOWED_FILE_TYPES": ("pdf", "docx", "md", "txt"),
            "RAG_FILELOADER_VERSION": "v1",
            "RAG_OCR_PROVIDER": "fake",
            "RAG_OCR_MODEL": "fake-ocr",
            "RAG_OCR_API_KEY": "",
            "RAG_OCR_BASE_URL": "",
            "RAG_CHROMADB_PERSIST_DIR": str(rag_chroma_dir),
            "RAG_CHROMADB_COLLECTION_PREFIX": "test_rag",
            "RAG_CHUNK_STRATEGY_DEFAULT": "paragraph",
            "RAG_CHUNK_STRATEGY_ALLOWED": ("paragraph", "semantic_llm"),
            "RAG_CHUNK_FALLBACK_STRATEGY": "paragraph",
            "BANKRUPTCY_ANALYSIS_ENABLED": True,
            "BANKRUPTCY_MODEL_PATH": "assets/bankruptcy/model/xgb_borderline_smote.pkl",
            "BANKRUPTCY_SCALER_PATH": "assets/bankruptcy/model/scaler_borderline_smote.pkl",
            "BANKRUPTCY_UPLOAD_DIR": str(bankruptcy_upload_dir),
            "BANKRUPTCY_PLOT_DIR": str(bankruptcy_plot_dir),
        }
    )

    with app.app_context():
        session = get_session()
        try:
            session.execute(text("DELETE FROM agent_chat_jobs"))
            session.execute(text("DELETE FROM agent_conversation_messages"))
            session.execute(text("DELETE FROM agent_conversation_threads"))
            session.execute(text("DELETE FROM analysis_reports"))
            session.execute(text("DELETE FROM analysis_module_artifacts"))
            session.execute(text("DELETE FROM analysis_sessions"))
            session.execute(text("DELETE FROM rag_query_logs"))
            session.execute(text("DELETE FROM rag_index_jobs"))
            session.execute(text("DELETE FROM rag_chunks"))
            session.execute(text("DELETE FROM rag_documents"))
            session.execute(text("DELETE FROM robotics_insight_runs"))
            session.execute(text("DELETE FROM robotics_policy_documents"))
            session.execute(text("DELETE FROM robotics_cninfo_announcements"))
            session.execute(text("DELETE FROM robotics_bidding_documents"))
            session.execute(text("DELETE FROM robotics_listed_company_profiles"))
            session.execute(text("DELETE FROM bankruptcy_analysis_records"))
            session.execute(text("DELETE FROM email_codes"))
            session.execute(text("DELETE FROM users"))
            session.commit()
            yield session
        finally:
            session.close()


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


def test_generate_paginated_report_outputs_prompt_driven_bundle_with_stage_trace():
    bundle = generate_paginated_report(
        title="机器人风险机会报告",
        goal="识别政策与订单机会",
        render_style="chart_focus",
        materials=[
            {"title": "政策摘要", "content": "政策支持: 3项。订单机会增加。建议关注招投标节奏。"},
            {"title": "订单表", "content": [{"month": "1月", "orders": 10}, {"month": "2月", "orders": 18}]},
        ],
        report_writer=_writer(),
    )

    assert bundle["schemaVersion"] == PAGINATED_REPORT_BUNDLE_SCHEMA_VERSION
    assert bundle["renderProfile"]["style"] == "chart_focus"
    assert bundle["promptVersions"]["visual_designer"] == "v1"
    assert "riskSignals" not in bundle["semanticModel"]
    assert "opportunitySignals" not in bundle["semanticModel"]
    assert [page["pageType"] for page in bundle["pages"]][:2] == ["cover", "table_of_contents"]
    assert all(page["pageType"] != "evidence" for page in bundle["pages"][2:])
    assert bundle["pages"][1]["items"]
    toc_titles = [item["title"] for item in bundle["pages"][1]["items"]]
    assert "证据与来源" not in toc_titles
    assert "逻辑拆解" not in toc_titles
    assert "边界与限制" not in toc_titles
    assert bundle["stageTrace"]
    assert bundle["qualityReview"]["approved"] is True
    assert bundle["exportManifest"]["availableFormats"] == ["pdf", "html", "bundle"]


def test_visual_chart_specs_are_grounded_in_extracted_tables():
    bundle = generate_paginated_report(
        title="经营报告",
        materials=[{"title": "收入表", "content": [{"year": 2024, "revenue": 100}, {"year": 2025, "revenue": 130}]}],
        report_writer=_writer(),
    )

    table_ids = {table["tableId"] for table in bundle["semanticModel"]["tables"]}
    assert bundle["chartSpecs"]
    assert all(chart["dataRef"] in table_ids for chart in bundle["chartSpecs"])
    assert validate_bundle(bundle) == []


def test_generate_report_artifact_from_source_documents_keeps_structured_payloads_chartable():
    artifact = generate_report_artifact_from_source_documents(
        [
            {
                "sourceId": "source-trend",
                "title": "月度经营趋势",
                "contentType": "application/json",
                "content": [
                    {"month": "2025-01", "revenue": 100, "orders": 80},
                    {"month": "2025-02", "revenue": 112, "orders": 91},
                    {"month": "2025-03", "revenue": 126, "orders": 108},
                ],
            }
        ],
        report_writer=_writer(),
    )

    assert artifact is not None
    bundle = artifact["paginatedReportBundle"]
    assert bundle["semanticModel"]["tables"]
    assert bundle["chartSpecs"]
    assert bundle["chartSpecs"][0]["type"] == "line_chart"
    assert artifact["sourceSnapshot"]["documents"][0]["content"].startswith("[")
    assert any(page["pageType"] == "chart_analysis" for page in bundle["pages"] if isinstance(page, dict))


def test_semantic_normalizer_can_override_table_labels_with_model_translations():
    artifact = generate_report_artifact_from_source_documents(
        [
            {
                "sourceId": "source-trend",
                "title": "月度经营趋势",
                "contentType": "application/json",
                "content": [
                    {"month": "2025-01", "revenue_billion": 100, "new_orders": 80, "capacity_utilization_pct": 73.5},
                    {"month": "2025-02", "revenue_billion": 112, "new_orders": 91, "capacity_utilization_pct": 76.1},
                ],
            }
        ],
        report_writer=_TableLabelingReportWriter(),
    )

    assert artifact is not None
    columns = artifact["paginatedReportBundle"]["semanticModel"]["tables"][0]["columns"]
    assert [column["label"] for column in columns] == ["月份", "收入（十亿）", "新增订单量", "产能利用率"]


def test_generate_report_artifact_from_source_documents_persists_snapshot_and_review_metadata():
    artifact = generate_report_artifact_from_source_documents(
        [
            {
                "sourceId": "source-alpha",
                "title": "石头科技近30天订单观察",
                "contentType": "markdown",
                "content": "# 石头科技\n\n收入: 120亿元。\n订单机会增加。",
            }
        ],
        report_writer=_writer(),
    )

    assert artifact is not None
    assert artifact["schemaVersion"] == "analysis_report_artifact.v1"
    assert artifact["paginatedReportBundle"]["schemaVersion"] == PAGINATED_REPORT_BUNDLE_SCHEMA_VERSION
    assert artifact["sourceSnapshot"]["documents"][0]["sourceId"] == "source-alpha"
    assert artifact["scope"]["sourceDocumentCount"] == 1
    assert artifact["preview"]
    assert artifact["qualityReview"]["approved"] is True
    assert artifact["stageTrace"]
    assert artifact["document"]["pages"][0]["type"] == "cover"
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
        report_writer=_writer(),
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
        report_writer=_writer(),
    )

    assert first_artifact["sourceSnapshot"]["documents"][0]["content"] == regenerated_artifact["sourceSnapshot"]["documents"][0]["content"]
    assert regenerated_artifact["reportId"] != saved_row.report_id
    assert regenerated_artifact["paginatedReportBundle"]["schemaVersion"] == PAGINATED_REPORT_BUNDLE_SCHEMA_VERSION
    assert regenerated_artifact["qualityReview"]["approved"] is True


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
        ],
        report_writer=_writer(),
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


def test_bundle_renderers_share_page_model_and_emit_svg_chart():
    bundle = generate_paginated_report(
        title="渲染测试",
        materials=[{"title": "材料", "content": [{"month": "1月", "orders": 12}, {"month": "2月", "orders": 16}]}],
        report_writer=_writer(),
    )

    html = render_bundle_html(bundle)
    markdown = render_bundle_markdown(bundle)
    pdf = render_bundle_pdf(bundle)

    assert [block["type"] for block in bundle["pages"][0]["blocks"]] == ["hero"]
    assert "report-page-cover" in html
    assert "report-cover-title" in html
    assert "阅读说明" not in html
    assert "报告类型" not in html
    assert "report-cover-photo" not in html
    assert "<svg" in html
    assert "## 目录" in markdown
    assert pdf.startswith(b"%PDF")


def test_paginated_renderers_reserve_footer_safe_area_for_non_cover_pages():
    bundle = generate_paginated_report(
        title="页脚安全区测试",
        materials=[{"title": "材料", "content": [{"month": "1月", "orders": 12}, {"month": "2月", "orders": 16}]}],
        report_writer=_writer(),
    )

    screen_package = build_bundle_render_package(bundle)
    pdf_package = build_bundle_render_package(bundle, target=PDF_TARGET)

    assert '.report-page:not(.report-page-cover) .report-page-surface::after{content:"";display:block;height:24mm}' in screen_package["css"]
    assert '.report-page:not(.report-page-cover) .report-page-surface::after{content:"";display:block;height:56px}' in pdf_package["css"]


def test_toc_uses_planned_chapters_instead_of_listing_each_chart_page():
    bundle = generate_paginated_report(
        title="章节规划测试",
        materials=[
            {"title": "月度收入", "content": [{"month": "1月", "revenue": 12}, {"month": "2月", "revenue": 16}, {"month": "3月", "revenue": 18}]},
            {"title": "区域结构", "content": [{"region": "华东", "revenue": 10}, {"region": "华南", "revenue": 14}, {"region": "华北", "revenue": 18}]},
            {"title": "产品结构", "content": [{"product": "A", "margin": 12}, {"product": "B", "margin": 16}, {"product": "C", "margin": 19}]},
        ],
        report_writer=_writer(),
    )

    toc_titles = [item["title"] for item in bundle["pages"][1]["items"]]
    chart_pages = [page for page in bundle["pages"] if page.get("pageType") == "chart_analysis"]

    assert len(chart_pages) >= 2
    assert "趋势与结构观察" in toc_titles
    assert toc_titles.count("趋势与结构观察") == 1


def test_toc_can_render_planner_defined_subsections():
    bundle = generate_paginated_report(
        title="目录二级标题测试",
        materials=[
            {"title": "月度收入", "content": [{"month": "1月", "revenue": 12}, {"month": "2月", "revenue": 16}, {"month": "3月", "revenue": 18}]},
            {"title": "区域结构", "content": [{"region": "华东", "revenue": 10}, {"region": "华南", "revenue": 14}, {"region": "华北", "revenue": 18}]},
            {"title": "产品结构", "content": [{"product": "A", "margin": 12}, {"product": "B", "margin": 16}, {"product": "C", "margin": 19}]},
        ],
        report_writer=_SubsectionPlanningReportWriter(),
    )

    toc_items = bundle["pages"][1]["items"]
    html = render_bundle_html(bundle)
    subsection_items = [item for item in toc_items if item.get("level") == 2]
    chart_pages = [page for page in bundle["pages"] if page.get("pageType") == "chart_analysis"]

    assert [item["title"] for item in subsection_items] == ["月度经营趋势", "区域收入结构"]
    assert [item["numberLabel"] for item in subsection_items] == ["3.1", "3.2"]
    assert [item["pageNumber"] for item in subsection_items] == [chart_pages[0]["pageNumber"], chart_pages[1]["pageNumber"]]
    assert chart_pages[0].get("subsectionTitle") == "月度经营趋势"
    assert chart_pages[0].get("subsectionNumberLabel") == "3.1"
    assert chart_pages[1].get("subsectionTitle") == "区域收入结构"
    assert chart_pages[1].get("subsectionNumberLabel") == "3.2"
    assert "3.1" in html
    assert "月度经营趋势" in html
    assert "区域收入结构" in html
    assert "<td class='report-toc-title'>执行摘要</td>" in html
    assert "<td class='report-toc-title'>一、执行摘要</td>" not in html
    assert ".report-toc-row-sub .report-toc-ordinal{width:58px;padding-left:22px}" in html
    assert ".report-toc-row-sub .report-toc-title{padding-left:18px}" in html
    assert "<h2 class='report-page-title'>1. 执行摘要</h2>" in html
    assert "<h2 class='report-page-title'>一、执行摘要</h2>" not in html
    assert "class='report-page-subtitle'" in html


def test_chartable_data_prefers_chart_refs_over_duplicate_table_refs():
    bundle = generate_paginated_report(
        title="图表优先测试",
        materials=[{"title": "收入表", "content": [{"year": 2024, "revenue": 100}, {"year": 2025, "revenue": 130}]}],
        report_writer=_writer(),
    )

    visual_chapters = [chapter for chapter in bundle["chapterPlan"] if chapter.get("chartRefs") or chapter.get("tableRefs")]

    assert visual_chapters
    assert all(chapter.get("chartRefs") for chapter in visual_chapters)
    assert all(not chapter.get("tableRefs") for chapter in visual_chapters)
    assert all(page.get("pageType") != "table_analysis" for page in bundle["pages"])


def test_each_chart_page_contains_only_one_chart_block():
    bundle = generate_paginated_report(
        title="单图分页测试",
        materials=[
            {"title": "月度收入", "content": [{"month": "1月", "revenue": 12}, {"month": "2月", "revenue": 16}, {"month": "3月", "revenue": 18}]},
            {"title": "区域结构", "content": [{"region": "华东", "revenue": 10}, {"region": "华南", "revenue": 14}, {"region": "华北", "revenue": 18}]},
            {"title": "产品结构", "content": [{"product": "A", "margin": 12}, {"product": "B", "margin": 16}, {"product": "C", "margin": 19}]},
        ],
        report_writer=_writer(),
    )

    chart_pages = [page for page in bundle["pages"] if page.get("pageType") == "chart_analysis"]

    assert len(chart_pages) >= 3
    assert all(sum(1 for block in page.get("blocks", []) if block.get("type") == "chart") == 1 for page in chart_pages)


def test_continuation_pages_do_not_repeat_chapter_header_titles():
    bundle = generate_paginated_report(
        title="续页标题测试",
        materials=[
            {"title": "月度收入", "content": [{"month": "1月", "revenue": 12}, {"month": "2月", "revenue": 16}, {"month": "3月", "revenue": 18}]},
            {"title": "区域结构", "content": [{"region": "华东", "revenue": 10}, {"region": "华南", "revenue": 14}, {"region": "华北", "revenue": 18}]},
            {"title": "产品结构", "content": [{"product": "A", "margin": 12}, {"product": "B", "margin": 16}, {"product": "C", "margin": 19}]},
        ],
        report_writer=_writer(),
    )

    html = render_bundle_html(bundle)
    chart_pages = [page for page in bundle["pages"] if page.get("pageType") == "chart_analysis"]

    assert len(chart_pages) >= 3
    assert chart_pages[0].get("showHeader") is True
    assert any(page.get("showHeader") is False for page in chart_pages[1:])
    assert html.count("<h2 class='report-page-title'>3. 趋势与结构观察</h2>") == 1
    assert "趋势与结构观察（续）" not in html


def test_review_snapshot_keeps_all_evidence_titles_needed_for_quality_review():
    snapshot = _review_block_snapshot(
        {
            "type": "evidence",
            "items": [
                {"title": "经营观察摘要", "summary": "摘要"},
                {"title": "月度经营趋势", "summary": "趋势"},
                {"title": "区域收入结构", "summary": "区域"},
                {"title": "产品线表现", "summary": "产品"},
                {"title": "供应链质量与交付", "summary": "供应链"},
            ],
        }
    )

    assert snapshot["itemCount"] == 5
    assert "供应链质量与交付" in snapshot["itemTitles"]


def test_table_pages_use_table_specific_prose_and_batch_small_tables():
    bundle = generate_paginated_report(
        title="表格续页测试",
        materials=[
            {"title": "项目状态", "content": [{"阶段": "立项", "状态": "完成", "责任人": "张三"}, {"阶段": "评审", "状态": "进行中", "责任人": "李四"}, {"阶段": "交付", "状态": "待开始", "责任人": "王五"}]},
            {"title": "区域排期", "content": [{"区域": "华东", "排期": "已确认", "窗口": "五月上旬"}, {"区域": "华南", "排期": "待确认", "窗口": "五月中旬"}, {"区域": "华北", "排期": "已确认", "窗口": "五月下旬"}]},
            {"title": "供应商备注", "content": [{"供应商": "A", "结论": "继续观察", "备注": "等待补件"}, {"供应商": "B", "结论": "保持合作", "备注": "交付稳定"}, {"供应商": "C", "结论": "重点跟进", "备注": "质量波动"}]},
        ],
        report_writer=_writer(),
    )

    table_pages = [page for page in bundle["pages"] if page.get("pageType") == "table_analysis"]
    first_table_page_texts = [block["text"] for block in table_pages[0]["blocks"] if block.get("type") == "paragraph"]

    assert len(table_pages) == 2
    assert any("关键数值" in text for text in first_table_page_texts)
    assert all("本章结合趋势图与数据摘录" not in text for text in first_table_page_texts)


def test_generate_paginated_report_fails_when_table_bound_visual_prose_is_missing():
    with pytest.raises(ReportGenerationError, match="table-bound prose"):
        generate_paginated_report(
            title="表格文案缺失",
            materials=[{"title": "项目状态表", "content": [{"阶段": "立项", "状态": "完成", "责任人": "张三"}, {"阶段": "评审", "状态": "进行中", "责任人": "李四"}]}],
            report_writer=_FakeReportWriter(omit_table_visuals=True),
        )


def test_generate_paginated_report_retries_writing_when_first_attempt_misses_chart_prose():
    writer = _RetryingReportWriter()

    bundle = generate_paginated_report(
        title="写作重试测试",
        materials=[{"title": "收入表", "content": [{"year": 2024, "revenue": 100}, {"year": 2025, "revenue": 130}]}],
        report_writer=writer,
    )

    assert writer.writing_calls == 2
    assert bundle["qualityReview"]["approved"] is True


def test_quality_review_rejects_ungrounded_chart_specs():
    bundle = generate_paginated_report(
        title="图表校验",
        materials=[{"title": "收入表", "content": [{"year": 2024, "revenue": 100}, {"year": 2025, "revenue": 130}]}],
        report_writer=_writer(),
    )
    bundle["chartSpecs"] = [{"chartId": "chart_bad", "type": "line_chart", "dataRef": "missing_table"}]

    errors = validate_bundle(bundle)

    assert any(error["code"] == "ungrounded_chart" for error in errors)


def test_quality_review_rejects_internal_reader_terms():
    bundle = generate_paginated_report(
        title="泄露校验",
        materials=[{"title": "材料", "content": "订单: 12项。"}],
        report_writer=_writer(),
    )
    bundle["pages"][2]["blocks"].append({"type": "paragraph", "text": "moduleId should not appear"})

    errors = validate_bundle(bundle)

    assert any(error["code"] == "internal_term_leakage" for error in errors)


def test_quality_review_rejects_template_terms():
    bundle = generate_paginated_report(
        title="模板词校验",
        materials=[{"title": "材料", "content": "订单: 12项。"}],
        report_writer=_writer(),
    )
    bundle["pages"][2]["blocks"].append({"type": "paragraph", "text": "本页列出由材料支持的进一步发现。"})

    errors = validate_bundle(bundle)

    assert any(error["code"] == "template_term_leakage" and error["term"] == "本页" for error in errors)


def test_quality_review_rejects_forbidden_tail_chapter_titles():
    bundle = generate_paginated_report(
        title="章节标题校验",
        materials=[{"title": "材料", "content": "订单: 12项。"}],
        report_writer=_writer(),
    )
    bundle["pages"][2]["title"] = "逻辑拆解"

    errors = validate_bundle(bundle)

    assert any(error["code"] == "forbidden_page_title" and error["title"] == "逻辑拆解" for error in errors)


def test_generate_paginated_report_fails_when_quality_review_blocks():
    with pytest.raises(ReportGenerationError):
        generate_paginated_report(
            title="失败测试",
            materials=[{"title": "材料", "content": "订单: 12项。"}],
            report_writer=_FakeReportWriter(reject_review=True),
        )
