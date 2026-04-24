from __future__ import annotations

import json

from app.agent.analysis_session import create_transient_analysis_session
from app.agent.graph import analysis_modules as analysis_module_graph
from app.agent.graph.analysis_modules import AnalysisModuleContract, normalize_analysis_module_output
from app.agent.graph.analysis_slots import (
    AnalysisSlotDefinition,
    SHARED_ANALYSIS_FOCUS_TAGS,
    SHARED_ENTERPRISE_NAME,
    SHARED_REPORT_GOAL,
    SHARED_STOCK_CODE,
    SHARED_TIME_RANGE,
    SCOPE_MODULE,
    VALUE_KIND_TEXT,
    parse_compound_answer_for_slots,
    parse_answer_for_group,
    shared_slot_catalog,
)
from app.agent.graph.nodes import (
    _analysis_bundle_system_section,
    analysis_intake_node,
    analysis_modules_node,
    mcp_subagent_node,
    plan_route_node,
    report_generation_node,
    search_subagent_node,
)
from app.agent.display_composition import DISPLAY_COMPOSITION_PROMPT_VERSION, load_display_composition_prompt
from app.agent.reporting import (
    ReportContributionValidationError,
    build_analysis_module_artifacts,
    build_robotics_domain_analysis,
    build_robotics_report_contribution,
    generate_analysis_report,
    generate_analysis_report_from_module_artifacts,
    normalize_visual_asset,
    render_report_pdf,
    validate_report_contribution_traceability,
)
from app.models import AnalysisModuleArtifact
from app.robotics_risk.cache import RoboticsEvidenceCache


class _FakeReportResponse:
    def __init__(self, content: str):
        self.content = content


class _FakeReportWriter:
    def __init__(self, content: str):
        self.content = content
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        return _FakeReportResponse(self.content)


def test_shared_slot_catalog_exposes_v1_baseline():
    catalog = shared_slot_catalog()

    assert {
        SHARED_ENTERPRISE_NAME,
        SHARED_STOCK_CODE,
        SHARED_TIME_RANGE,
        SHARED_REPORT_GOAL,
        SHARED_ANALYSIS_FOCUS_TAGS,
        "region_scope",
    }.issubset(set(catalog))
    assert catalog[SHARED_ENTERPRISE_NAME].normalizer == "enterprise_name"
    assert catalog[SHARED_ANALYSIS_FOCUS_TAGS].value_kind == "multi_choice"
    assert catalog[SHARED_ANALYSIS_FOCUS_TAGS].normalizer == "choice_tags"


def test_parse_answer_for_enterprise_identity_group_normalizes_name_and_stock_code():
    catalog = shared_slot_catalog()

    updates = parse_answer_for_group(
        slot_ids=[SHARED_ENTERPRISE_NAME, SHARED_STOCK_CODE],
        slot_catalog=catalog,
        user_message="石头科技 688169",
    )

    assert updates == {
        SHARED_ENTERPRISE_NAME: "石头科技",
        SHARED_STOCK_CODE: "688169",
    }


def test_parse_compound_answer_separates_enterprise_time_goal_and_focus():
    catalog = shared_slot_catalog()

    updates = parse_compound_answer_for_slots(
        slot_ids=[
            SHARED_ENTERPRISE_NAME,
            SHARED_STOCK_CODE,
            SHARED_TIME_RANGE,
            SHARED_REPORT_GOAL,
            SHARED_ANALYSIS_FOCUS_TAGS,
        ],
        slot_catalog=catalog,
        user_message="石头科技 688169，时间范围近30天，报告目标是生成机器人风险机会报告，分析重点为政策和订单",
    )

    assert updates == {
        SHARED_ENTERPRISE_NAME: "石头科技",
        SHARED_STOCK_CODE: "688169",
        SHARED_TIME_RANGE: "近30天",
        SHARED_REPORT_GOAL: "生成机器人风险机会报告",
        SHARED_ANALYSIS_FOCUS_TAGS: ["政策", "订单"],
    }


def test_plan_route_requests_clarification_for_vague_search():
    result = plan_route_node(
        {
            "user_message": "搜索",
            "rag_enabled": True,
            "web_enabled": True,
            "mcp_enabled": False,
        }
    )
    assert result["needs_clarification"] is True
    assert "具体主题" in result["clarification_question"]


def test_plan_route_prefers_analysis_intake_when_modules_enabled():
    result = plan_route_node(
        {
            "user_message": "请开始做报告",
            "enabled_analysis_modules": ["robotics_risk"],
            "debug": {},
        }
    )
    assert result["intent"] == "analysis"
    assert result["needs_search"] is False
    assert result["needs_mcp"] is False
    assert result["analysis_completed"] is False


def test_plan_route_preserves_public_only_strategy_for_explicit_web_request():
    result = plan_route_node(
        {
            "user_message": "帮我上网搜索一下京东方这个公司的情况",
            "rag_enabled": True,
            "web_enabled": True,
            "mcp_enabled": False,
        }
    )
    assert result["needs_search"] is True
    assert result["needs_clarification"] is False
    assert result["search_request"]["preferred_strategy"] == "public_only"


def test_robotics_module_runtime_uses_db_backed_cache_in_app_context(app, monkeypatch):
    captured = {}

    def _fake_run(payload, **kwargs):
        captured["payload"] = dict(payload)
        captured["db"] = kwargs.get("db")
        captured["evidence_cache"] = kwargs.get("evidence_cache")
        return {
            "status": "partial",
            "runId": "rrisk-cache-001",
            "limitations": ["未检索到可用于风险机会洞察的来源文档。"],
        }

    monkeypatch.setattr(analysis_module_graph, "run_robotics_risk_subagent", _fake_run)

    with app.app_context():
        output = analysis_module_graph._run_robotics_risk_module({"enterpriseName": "优必选"})

    assert output["runId"] == "rrisk-cache-001"
    assert captured["payload"]["enterpriseName"] == "优必选"
    assert captured["db"] is not None
    assert isinstance(captured["evidence_cache"], RoboticsEvidenceCache)


def test_partial_analysis_module_without_sources_summarizes_evidence_gap():
    contract = AnalysisModuleContract(
        module_id="robotics_risk",
        display_name="机器人风险机会洞察",
        required_slots=(),
    )

    output = normalize_analysis_module_output(
        contract,
        {
            "status": "partial",
            "runId": "rrisk-empty",
            "result": {
                "summary": {
                    "opportunity": "未发现明确机会信号。",
                    "risk": "未发现明确风险信号。",
                }
            },
            "documentHandoff": {"executiveSummary": {"sourceCount": 0}},
            "limitations": ["未检索到可用于风险机会洞察的来源文档。"],
            "sourceReferences": [],
        },
    )

    assert output["summary"] == "未检索到可用于风险机会洞察的来源文档。"


def test_analysis_bundle_system_section_blocks_no_evidence_inference():
    section = _analysis_bundle_system_section(
        {
            "analysis_handoff_bundle": {
                "enabledModules": ["robotics_risk"],
                "moduleResults": [
                    {
                        "moduleId": "robotics_risk",
                        "displayName": "机器人风险机会洞察",
                        "status": "partial",
                        "summary": "未检索到可用于风险机会洞察的来源文档。",
                        "sourceReferences": [],
                        "documentHandoff": {"executiveSummary": {"sourceCount": 0}},
                    }
                ],
                "limitations": ["未检索到可用于风险机会洞察的来源文档。"],
            }
        }
    )

    assert "sourceCount=0" in section
    assert "不得基于行业常识" in section


def test_analysis_intake_deduplicates_shared_slots_before_module_specific(monkeypatch):
    robotics_contract = AnalysisModuleContract(
        module_id="robotics_risk",
        display_name="机器人风险机会洞察",
        required_slots=(
            SHARED_ENTERPRISE_NAME,
            SHARED_TIME_RANGE,
            SHARED_REPORT_GOAL,
            SHARED_ANALYSIS_FOCUS_TAGS,
        ),
        slot_mapping=lambda slots, compatibility, context: {},
        run=lambda payload: {},
    )
    operations_contract = AnalysisModuleContract(
        module_id="enterprise_operations",
        display_name="企业运营分析",
        required_slots=(
            SHARED_ENTERPRISE_NAME,
            SHARED_TIME_RANGE,
            SHARED_REPORT_GOAL,
            "enterprise_operations.metrics",
        ),
        slot_definitions=(
            AnalysisSlotDefinition(
                slot_id="enterprise_operations.metrics",
                label="经营指标",
                scope=SCOPE_MODULE,
                value_kind=VALUE_KIND_TEXT,
                normalizer="passthrough_text",
                group_id="enterprise_operations.metrics",
                priority=80,
                depends_on=(SHARED_ENTERPRISE_NAME, SHARED_TIME_RANGE, SHARED_REPORT_GOAL),
                module_id="enterprise_operations",
            ),
        ),
        slot_mapping=lambda slots, compatibility, context: {},
        run=lambda payload: {},
    )
    monkeypatch.setattr(
        "app.agent.graph.nodes.get_analysis_module_registry",
        lambda: {
            "robotics_risk": robotics_contract,
            "enterprise_operations": operations_contract,
        },
    )

    result = analysis_intake_node(
        {
            "user_message": "请开始分析",
            "enabled_analysis_modules": ["robotics_risk", "enterprise_operations"],
            "analysis_shared_inputs": {},
            "analysis_module_inputs": {},
            "analysis_session": create_transient_analysis_session(
                enabled_modules=["robotics_risk", "enterprise_operations"]
            ),
            "debug": {},
        }
    )

    assert result["needs_clarification"] is True
    assert "企业名称" in result["clarification_question"]
    assert "经营指标" not in result["clarification_question"]
    assert result["missing_fields"] == [
        "analysis.shared.enterprise_name",
        "analysis.shared.time_range",
        "analysis.shared.report_goal",
        "analysis.shared.analysis_focus_tags",
    ]


def test_analysis_intake_ignores_disabled_module_specific_slots(monkeypatch):
    robotics_contract = AnalysisModuleContract(
        module_id="robotics_risk",
        display_name="机器人风险机会洞察",
        required_slots=(
            SHARED_ENTERPRISE_NAME,
            SHARED_TIME_RANGE,
            SHARED_REPORT_GOAL,
            "robotics_risk.focus_detail",
        ),
        slot_definitions=(
            AnalysisSlotDefinition(
                slot_id="robotics_risk.focus_detail",
                label="机器人关注重点",
                scope=SCOPE_MODULE,
                value_kind=VALUE_KIND_TEXT,
                normalizer="passthrough_text",
                group_id="robotics_risk.focus_detail",
                priority=70,
                depends_on=(SHARED_ENTERPRISE_NAME, SHARED_TIME_RANGE, SHARED_REPORT_GOAL),
                module_id="robotics_risk",
            ),
        ),
        slot_mapping=lambda slots, compatibility, context: {},
        run=lambda payload: {},
    )
    operations_contract = AnalysisModuleContract(
        module_id="enterprise_operations",
        display_name="企业运营分析",
        required_slots=(
            SHARED_ENTERPRISE_NAME,
            SHARED_TIME_RANGE,
            SHARED_REPORT_GOAL,
            "enterprise_operations.metrics",
        ),
        slot_definitions=(
            AnalysisSlotDefinition(
                slot_id="enterprise_operations.metrics",
                label="经营指标",
                scope=SCOPE_MODULE,
                value_kind=VALUE_KIND_TEXT,
                normalizer="passthrough_text",
                group_id="enterprise_operations.metrics",
                priority=80,
                depends_on=(SHARED_ENTERPRISE_NAME, SHARED_TIME_RANGE, SHARED_REPORT_GOAL),
                module_id="enterprise_operations",
            ),
        ),
        slot_mapping=lambda slots, compatibility, context: {},
        run=lambda payload: {},
    )
    monkeypatch.setattr(
        "app.agent.graph.nodes.get_analysis_module_registry",
        lambda: {
            "robotics_risk": robotics_contract,
            "enterprise_operations": operations_contract,
        },
    )

    result = analysis_intake_node(
        {
            "user_message": "请继续",
            "enabled_analysis_modules": ["robotics_risk"],
            "analysis_shared_inputs": {
                "enterpriseName": "石头科技",
                "timeRange": "近30天",
                "reportGoal": "识别机器人行业风险与机会",
            },
            "analysis_module_inputs": {},
            "analysis_session": create_transient_analysis_session(enabled_modules=["robotics_risk"]),
            "debug": {},
        }
    )

    assert result["needs_clarification"] is True
    assert "机器人关注重点" in result["clarification_question"]
    assert "经营指标" not in result["clarification_question"]
    assert result["missing_fields"] == ["analysis.robotics_risk.focus_detail"]


def test_analysis_intake_groups_same_round_shared_slots(monkeypatch):
    grouped_contract = AnalysisModuleContract(
        module_id="grouped_module",
        display_name="分组测试模块",
        required_slots=(
            SHARED_ENTERPRISE_NAME,
            SHARED_STOCK_CODE,
            SHARED_REPORT_GOAL,
        ),
        slot_mapping=lambda slots, compatibility, context: {},
        run=lambda payload: {},
    )
    monkeypatch.setattr("app.agent.graph.nodes.get_analysis_module_registry", lambda: {"grouped_module": grouped_contract})

    result = analysis_intake_node(
        {
            "user_message": "开始",
            "enabled_analysis_modules": ["grouped_module"],
            "analysis_shared_inputs": {},
            "analysis_module_inputs": {},
            "analysis_session": create_transient_analysis_session(enabled_modules=["grouped_module"]),
            "debug": {},
        }
    )

    question_plan = result["analysis_session"]["questionPlan"]
    assert result["needs_clarification"] is True
    assert question_plan[0]["groupId"] == "enterprise_identity"
    assert question_plan[0]["slotIds"] == [SHARED_ENTERPRISE_NAME, SHARED_STOCK_CODE]
    assert question_plan[0]["labels"] == ["企业名称", "股票代码"]
    assert question_plan[1]["groupId"] == "report_goal"


def test_analysis_intake_clarification_marks_shared_vs_module_specific_gaps(monkeypatch):
    robotics_contract = AnalysisModuleContract(
        module_id="robotics_risk",
        display_name="机器人风险机会洞察",
        required_slots=(
            SHARED_ENTERPRISE_NAME,
            SHARED_TIME_RANGE,
            SHARED_REPORT_GOAL,
            "robotics_risk.focus_detail",
        ),
        slot_definitions=(
            AnalysisSlotDefinition(
                slot_id="robotics_risk.focus_detail",
                label="机器人关注重点",
                scope=SCOPE_MODULE,
                value_kind=VALUE_KIND_TEXT,
                normalizer="passthrough_text",
                group_id="robotics_risk.focus_detail",
                priority=70,
                depends_on=(SHARED_ENTERPRISE_NAME, SHARED_TIME_RANGE, SHARED_REPORT_GOAL),
                module_id="robotics_risk",
            ),
        ),
        slot_mapping=lambda slots, compatibility, context: {},
        run=lambda payload: {},
    )
    monkeypatch.setattr("app.agent.graph.nodes.get_analysis_module_registry", lambda: {"robotics_risk": robotics_contract})

    shared_gap = analysis_intake_node(
        {
            "user_message": "开始",
            "enabled_analysis_modules": ["robotics_risk"],
            "analysis_shared_inputs": {},
            "analysis_module_inputs": {},
            "analysis_session": create_transient_analysis_session(enabled_modules=["robotics_risk"]),
            "debug": {},
        }
    )
    assert "共享信息" in shared_gap["clarification_question"]
    assert "模块特有信息" in shared_gap["clarification_question"]

    module_gap = analysis_intake_node(
        {
            "user_message": "石头科技，时间范围近30天，报告目标是生成风险机会报告",
            "enabled_analysis_modules": ["robotics_risk"],
            "analysis_shared_inputs": {},
            "analysis_module_inputs": {},
            "analysis_session": create_transient_analysis_session(enabled_modules=["robotics_risk"]),
            "debug": {},
        }
    )
    assert module_gap["needs_clarification"] is True
    assert "共享信息已齐备" in module_gap["clarification_question"]
    assert "机器人关注重点" in module_gap["clarification_question"]


def test_analysis_intake_marks_ready_when_required_slots_are_prefilled():
    result = analysis_intake_node(
        {
            "user_message": "请开始机器人风险机会分析",
            "enabled_analysis_modules": ["robotics_risk"],
            "analysis_shared_inputs": {
                "enterpriseName": "石头科技",
                "timeRange": "近30天",
                "reportGoal": "形成风险机会简报",
            },
            "analysis_module_inputs": {
                "robotics_risk": {
                    "focus": "政策、订单",
                }
            },
            "analysis_session": create_transient_analysis_session(enabled_modules=["robotics_risk"]),
            "debug": {},
        }
    )

    assert result["needs_clarification"] is False
    assert result["missing_fields"] == []
    assert result["analysis_completed"] is False
    assert result["analysis_session"]["status"] == "ready"
    assert result["analysis_session"]["slotValues"][SHARED_ANALYSIS_FOCUS_TAGS] == ["政策", "订单"]


def test_analysis_intake_first_turn_compound_prompt_fills_required_slots():
    result = analysis_intake_node(
        {
            "user_message": "石头科技 688169，时间范围近30天，报告目标是生成机器人风险机会报告，分析重点为政策和订单",
            "enabled_analysis_modules": ["robotics_risk"],
            "analysis_shared_inputs": {},
            "analysis_module_inputs": {},
            "analysis_session": create_transient_analysis_session(enabled_modules=["robotics_risk"]),
            "debug": {},
        }
    )

    slot_values = result["analysis_session"]["slotValues"]
    assert result["needs_clarification"] is False
    assert result["missing_fields"] == []
    assert result["analysis_session"]["status"] == "ready"
    assert slot_values[SHARED_ENTERPRISE_NAME] == "石头科技"
    assert slot_values[SHARED_STOCK_CODE] == "688169"
    assert slot_values[SHARED_TIME_RANGE] == "近30天"
    assert slot_values[SHARED_REPORT_GOAL] == "生成机器人风险机会报告"
    assert slot_values[SHARED_ANALYSIS_FOCUS_TAGS] == ["政策", "订单"]


def test_analysis_intake_follow_up_time_change_does_not_mutate_enterprise(monkeypatch):
    contract = AnalysisModuleContract(
        module_id="robotics_risk",
        display_name="机器人风险机会洞察",
        required_slots=(
            SHARED_ENTERPRISE_NAME,
            SHARED_TIME_RANGE,
            SHARED_REPORT_GOAL,
            SHARED_ANALYSIS_FOCUS_TAGS,
        ),
        slot_mapping=lambda slots, compatibility, context: {},
        run=lambda payload: {},
    )
    monkeypatch.setattr("app.agent.graph.nodes.get_analysis_module_registry", lambda: {"robotics_risk": contract})
    session = create_transient_analysis_session(enabled_modules=["robotics_risk"])
    session["status"] = "collecting"
    session["revision"] = 1
    session["slotValues"] = {
        SHARED_ENTERPRISE_NAME: "石头科技",
        SHARED_STOCK_CODE: "688169",
        SHARED_REPORT_GOAL: "生成机器人风险机会报告",
        SHARED_ANALYSIS_FOCUS_TAGS: ["政策", "订单"],
    }
    session["questionPlan"] = [
        {
            "groupId": "time_range",
            "slotIds": [SHARED_TIME_RANGE],
            "requiredSlotIds": [SHARED_TIME_RANGE],
            "labels": ["时间范围"],
            "question": "请补充时间范围。",
        }
    ]

    result = analysis_intake_node(
        {
            "user_message": "改成近90天",
            "enabled_analysis_modules": ["robotics_risk"],
            "analysis_shared_inputs": {},
            "analysis_module_inputs": {},
            "analysis_session": session,
            "debug": {},
        }
    )

    slot_values = result["analysis_session"]["slotValues"]
    assert slot_values[SHARED_ENTERPRISE_NAME] == "石头科技"
    assert slot_values[SHARED_STOCK_CODE] == "688169"
    assert slot_values[SHARED_TIME_RANGE] == "近90天"
    assert result["debug"]["analysisIntake"]["changedSlots"] == [SHARED_TIME_RANGE]


def test_analysis_intake_follow_up_time_only_reply_does_not_overwrite_enterprise(monkeypatch):
    contract = AnalysisModuleContract(
        module_id="robotics_risk",
        display_name="机器人风险机会洞察",
        required_slots=(
            SHARED_ENTERPRISE_NAME,
            SHARED_TIME_RANGE,
            SHARED_REPORT_GOAL,
            SHARED_ANALYSIS_FOCUS_TAGS,
        ),
        slot_mapping=lambda slots, compatibility, context: {},
        run=lambda payload: {},
    )
    monkeypatch.setattr("app.agent.graph.nodes.get_analysis_module_registry", lambda: {"robotics_risk": contract})
    session = create_transient_analysis_session(enabled_modules=["robotics_risk"])
    session["status"] = "collecting"
    session["revision"] = 1
    session["slotValues"] = {
        SHARED_ENTERPRISE_NAME: "石头科技",
        SHARED_STOCK_CODE: "688169",
        SHARED_REPORT_GOAL: "生成机器人风险机会报告",
        SHARED_ANALYSIS_FOCUS_TAGS: ["政策", "订单"],
    }
    session["questionPlan"] = [
        {
            "groupId": "time_range",
            "slotIds": [SHARED_TIME_RANGE],
            "requiredSlotIds": [SHARED_TIME_RANGE],
            "labels": ["时间范围"],
            "question": "请补充时间范围。",
        }
    ]

    result = analysis_intake_node(
        {
            "user_message": "一年",
            "enabled_analysis_modules": ["robotics_risk"],
            "analysis_shared_inputs": {},
            "analysis_module_inputs": {},
            "analysis_session": session,
            "debug": {},
        }
    )

    slot_values = result["analysis_session"]["slotValues"]
    assert slot_values[SHARED_ENTERPRISE_NAME] == "石头科技"
    assert slot_values[SHARED_STOCK_CODE] == "688169"
    assert slot_values[SHARED_TIME_RANGE] == "一年"
    assert result["debug"]["analysisIntake"]["changedSlots"] == [SHARED_TIME_RANGE]


def test_analysis_intake_follow_up_focus_only_reply_does_not_overwrite_enterprise(monkeypatch):
    contract = AnalysisModuleContract(
        module_id="robotics_risk",
        display_name="机器人风险机会洞察",
        required_slots=(
            SHARED_ENTERPRISE_NAME,
            SHARED_TIME_RANGE,
            SHARED_REPORT_GOAL,
            SHARED_ANALYSIS_FOCUS_TAGS,
        ),
        slot_mapping=lambda slots, compatibility, context: {},
        run=lambda payload: {},
    )
    monkeypatch.setattr("app.agent.graph.nodes.get_analysis_module_registry", lambda: {"robotics_risk": contract})
    session = create_transient_analysis_session(enabled_modules=["robotics_risk"])
    session["status"] = "collecting"
    session["revision"] = 1
    session["slotValues"] = {
        SHARED_ENTERPRISE_NAME: "石头科技",
        SHARED_STOCK_CODE: "688169",
        SHARED_TIME_RANGE: "近90天",
        SHARED_REPORT_GOAL: "生成机器人风险机会报告",
    }
    session["questionPlan"] = [
        {
            "groupId": "analysis_focus",
            "slotIds": [SHARED_ANALYSIS_FOCUS_TAGS],
            "requiredSlotIds": [SHARED_ANALYSIS_FOCUS_TAGS],
            "labels": ["分析重点"],
            "question": "请补充分析重点。",
        }
    ]

    result = analysis_intake_node(
        {
            "user_message": "政策",
            "enabled_analysis_modules": ["robotics_risk"],
            "analysis_shared_inputs": {},
            "analysis_module_inputs": {},
            "analysis_session": session,
            "debug": {},
        }
    )

    slot_values = result["analysis_session"]["slotValues"]
    assert slot_values[SHARED_ENTERPRISE_NAME] == "石头科技"
    assert slot_values[SHARED_STOCK_CODE] == "688169"
    assert slot_values[SHARED_ANALYSIS_FOCUS_TAGS] == ["政策"]
    assert result["debug"]["analysisIntake"]["changedSlots"] == [SHARED_ANALYSIS_FOCUS_TAGS]


def test_analysis_intake_explicit_correction_can_update_resolved_enterprise(monkeypatch):
    contract = AnalysisModuleContract(
        module_id="robotics_risk",
        display_name="机器人风险机会洞察",
        required_slots=(
            SHARED_ENTERPRISE_NAME,
            SHARED_TIME_RANGE,
            SHARED_REPORT_GOAL,
            SHARED_ANALYSIS_FOCUS_TAGS,
        ),
        slot_mapping=lambda slots, compatibility, context: {},
        run=lambda payload: {},
    )
    monkeypatch.setattr("app.agent.graph.nodes.get_analysis_module_registry", lambda: {"robotics_risk": contract})
    session = create_transient_analysis_session(enabled_modules=["robotics_risk"])
    session["status"] = "collecting"
    session["revision"] = 1
    session["slotValues"] = {
        SHARED_ENTERPRISE_NAME: "石头科技",
        SHARED_STOCK_CODE: "688169",
        SHARED_TIME_RANGE: "近90天",
        SHARED_REPORT_GOAL: "生成机器人风险机会报告",
    }
    session["questionPlan"] = [
        {
            "groupId": "analysis_focus",
            "slotIds": [SHARED_ANALYSIS_FOCUS_TAGS],
            "requiredSlotIds": [SHARED_ANALYSIS_FOCUS_TAGS],
            "labels": ["分析重点"],
            "question": "请补充分析重点。",
        }
    ]

    result = analysis_intake_node(
        {
            "user_message": "企业改成优必选",
            "enabled_analysis_modules": ["robotics_risk"],
            "analysis_shared_inputs": {},
            "analysis_module_inputs": {},
            "analysis_session": session,
            "debug": {},
        }
    )

    slot_values = result["analysis_session"]["slotValues"]
    assert slot_values[SHARED_ENTERPRISE_NAME] == "优必选"
    assert SHARED_ANALYSIS_FOCUS_TAGS not in slot_values
    assert result["needs_clarification"] is True
    assert "分析重点" in result["clarification_question"]
    assert result["debug"]["analysisIntake"]["changedSlots"] == [SHARED_ENTERPRISE_NAME]


def test_analysis_modules_node_builds_aggregate_bundle(monkeypatch):
    contract = AnalysisModuleContract(
        module_id="robotics_risk",
        display_name="机器人风险机会洞察",
        required_slots=(
            SHARED_ENTERPRISE_NAME,
            SHARED_TIME_RANGE,
            SHARED_REPORT_GOAL,
            "robotics_risk.focus_detail",
        ),
        slot_definitions=(
            AnalysisSlotDefinition(
                slot_id="robotics_risk.focus_detail",
                label="关注重点",
                scope=SCOPE_MODULE,
                value_kind=VALUE_KIND_TEXT,
                normalizer="passthrough_text",
                group_id="robotics_risk.focus_detail",
                priority=70,
                depends_on=(SHARED_ENTERPRISE_NAME, SHARED_TIME_RANGE, SHARED_REPORT_GOAL),
                module_id="robotics_risk",
            ),
        ),
        slot_mapping=lambda slots, compatibility, context: {
            "enterpriseName": slots[SHARED_ENTERPRISE_NAME],
            "focus": slots["robotics_risk.focus_detail"],
            "conversationContext": context["conversationContext"],
        },
        run=lambda payload: {
            "status": "done",
            "runId": "run-robotics-001",
            "result": {
                "summary": {
                    "opportunity": "政策和订单侧存在增长信号。",
                    "risk": "竞争和招投标节奏存在波动。",
                },
                "opportunities": [{"id": "sig_policy_001", "source_ids": ["src_policy_001"]}],
                "events": [{"id": "evt_policy_001", "source_document_id": "src_policy_001"}],
            },
            "documentHandoff": {
                "title": "石头科技风险机会简报",
                "executiveSummary": {"headline": "政策与订单是当前主线。"},
                "readerPacket": {
                    "schemaVersion": "robotics_reader_packet.v1",
                    "executiveSummary": {"headline": "政策与订单是当前主线。"},
                    "evidenceReferences": [
                        {
                            "id": "evidence_policy_001",
                            "title": "机器人产业支持政策",
                            "readerSummary": "该政策用于支撑机会侧判断。",
                        }
                    ],
                    "visualSummaries": [
                        {
                            "id": "visual_theme_001",
                            "title": "机会主题强度分布",
                            "caption": "用于比较当前机会主线的相对强弱。",
                        }
                    ],
                },
                "factTables": [
                    {
                        "tableId": "opportunity_themes",
                        "title": "机会主题",
                        "columns": [{"key": "theme", "label": "主题"}],
                        "rows": [{"rowId": "opp_01", "cells": {"theme": "政策与设备更新"}}],
                    }
                ],
                "chartCandidates": [
                    {
                        "chartId": "chart_theme_001",
                        "sourceTableId": "opportunity_themes",
                        "chartType": "bar",
                        "title": "机会主题强度分布",
                        "caption": "用于比较当前机会主线的相对强弱。",
                        "interpretationBoundary": "图中分值用于相对排序。",
                        "series": [{"label": "政策与设备更新", "value": 88}],
                    }
                ],
                "renderedAssets": [
                    {
                        "assetId": "asset_chart_theme_001",
                        "chartId": "chart_theme_001",
                        "sourceTableId": "opportunity_themes",
                        "contentType": "image/png",
                        "title": "机会主题强度分布",
                        "caption": "用于比较当前机会主线的相对强弱。",
                        "altText": "机会主题强度分布",
                        "renderPayload": {"dataUrl": "data:image/png;base64,ZmFrZQ=="},
                    }
                ],
                "evidenceReferences": [
                    {
                        "id": "evidence_policy_001",
                        "title": "机器人产业支持政策",
                        "readerSummary": "该政策用于支撑机会侧判断。",
                    }
                ],
                "visualSummaries": [
                    {
                        "id": "visual_theme_001",
                        "title": "机会主题强度分布",
                        "caption": "用于比较当前机会主线的相对强弱。",
                    }
                ],
            },
            "limitations": ["公告样本有限"],
        },
    )
    monkeypatch.setattr("app.agent.graph.nodes.get_analysis_module_registry", lambda: {"robotics_risk": contract})
    analysis_session = create_transient_analysis_session(enabled_modules=["robotics_risk"])
    analysis_session["revision"] = 2
    analysis_session["status"] = "ready"
    analysis_session["slotValues"] = {
        SHARED_ENTERPRISE_NAME: "石头科技",
        SHARED_TIME_RANGE: "近30天",
        SHARED_REPORT_GOAL: "形成风险机会简报",
        "robotics_risk.focus_detail": "订单与政策",
    }

    result = analysis_modules_node(
        {
            "user_message": "请开始分析",
            "conversation_context": "最近对话：用户希望关注订单机会。",
            "enabled_analysis_modules": ["robotics_risk"],
            "analysis_session": analysis_session,
            "debug": {},
        }
    )

    assert result["analysis_completed"] is True
    assert result["analysis_results"]["robotics_risk"]["runId"] == "run-robotics-001"
    assert result["analysis_results"]["robotics_risk"]["inputSnapshotRevision"] == 2
    bundle = result["analysis_handoff_bundle"]
    assert bundle["enabledModules"] == ["robotics_risk"]
    assert bundle["analysisSession"]["revision"] == 2
    assert bundle["sharedInputSummary"]["enterpriseName"] == "石头科技"
    assert bundle["moduleRunIds"]["robotics_risk"] == "run-robotics-001"
    assert bundle["documentHandoffs"]["robotics_risk"]["title"] == "石头科技风险机会简报"
    assert bundle["moduleReaderPackets"]["robotics_risk"]["schemaVersion"] == "robotics_reader_packet.v1"
    assert bundle["moduleTabularArtifacts"]["robotics_risk"]["factTables"][0]["tableId"] == "opportunity_themes"
    assert bundle["limitations"] == ["公告样本有限"]
    assert result["analysis_results"]["robotics_risk"]["domainAnalysis"]["moduleId"] == "robotics_risk"
    assert result["analysis_results"]["robotics_risk"]["reportContribution"]["moduleId"] == "robotics_risk"
    assert result["analysis_results"]["robotics_risk"]["readerPacket"]["schemaVersion"] == "robotics_reader_packet.v1"
    assert result["analysis_results"]["robotics_risk"]["evidenceReferences"][0]["title"] == "机器人产业支持政策"
    assert result["analysis_results"]["robotics_risk"]["factTables"][0]["tableId"] == "opportunity_themes"
    assert result["analysis_results"]["robotics_risk"]["chartCandidates"][0]["chartId"] == "chart_theme_001"
    assert result["analysis_results"]["robotics_risk"]["renderedAssets"][0]["assetId"] == "asset_chart_theme_001"
    assert result["analysis_results"]["robotics_risk"]["visualSummaries"][0]["title"] == "机会主题强度分布"
    assert result["analysis_results"]["robotics_risk"]["result"]["events"][0]["id"] == "evt_policy_001"
    assert result["analysis_report_generated"] is False
    assert result["analysis_report"] == {}
    assert result["analysis_module_artifacts"][0]["moduleId"] == "robotics_risk"
    assert result["analysis_module_artifacts"][0]["moduleRunId"] == "run-robotics-001"
    assert result["analysis_module_artifacts"][0]["executiveSummary"]["headline"] == "政策与订单是当前主线。"
    assert result["analysis_module_artifacts"][0]["evidenceReferences"][0]["title"] == "机器人产业支持政策"
    assert result["analysis_module_artifacts"][0]["factTables"][0]["tableId"] == "opportunity_themes"
    assert result["analysis_module_artifacts"][0]["chartCandidates"][0]["chartId"] == "chart_theme_001"
    assert result["analysis_module_artifacts"][0]["renderedAssets"][0]["assetId"] == "asset_chart_theme_001"
    assert result["analysis_module_artifacts"][0]["visualSummaries"][0]["title"] == "机会主题强度分布"
    assert result["analysis_report_request"]["moduleArtifactIds"] == [
        result["analysis_module_artifacts"][0]["artifactId"]
    ]


def test_analysis_modules_node_passes_main_llm_to_module_runtime_input(monkeypatch):
    captured = {}
    writer = _FakeReportWriter("{}")
    contract = AnalysisModuleContract(
        module_id="robotics_risk",
        display_name="机器人风险机会洞察",
        required_slots=(SHARED_ENTERPRISE_NAME, SHARED_TIME_RANGE, SHARED_REPORT_GOAL, "robotics_risk.focus_detail"),
        slot_definitions=(
            AnalysisSlotDefinition(
                slot_id="robotics_risk.focus_detail",
                label="关注重点",
                scope=SCOPE_MODULE,
                value_kind=VALUE_KIND_TEXT,
                normalizer="passthrough_text",
                group_id="robotics_risk.focus_detail",
                priority=70,
                depends_on=(SHARED_ENTERPRISE_NAME, SHARED_TIME_RANGE, SHARED_REPORT_GOAL),
                module_id="robotics_risk",
            ),
        ),
        slot_mapping=lambda slots, compatibility, context: {
            "enterpriseName": slots[SHARED_ENTERPRISE_NAME],
            "readerWriter": context.get("readerWriter"),
        },
        run=lambda payload: (
            captured.update({"reader_writer": payload.get("readerWriter")}) or {"status": "done", "limitations": ["无实质材料"]}
        ),
    )
    monkeypatch.setattr("app.agent.graph.nodes.get_analysis_module_registry", lambda: {"robotics_risk": contract})
    analysis_session = create_transient_analysis_session(enabled_modules=["robotics_risk"])
    analysis_session["status"] = "ready"
    analysis_session["slotValues"] = {
        SHARED_ENTERPRISE_NAME: "石头科技",
        SHARED_TIME_RANGE: "近30天",
        SHARED_REPORT_GOAL: "形成风险机会简报",
        "robotics_risk.focus_detail": "订单与政策",
    }

    analysis_modules_node(
        {
            "user_message": "请开始分析",
            "enabled_analysis_modules": ["robotics_risk"],
            "analysis_session": analysis_session,
            "main_llm": writer,
            "debug": {},
        }
    )

    assert captured["reader_writer"] is writer


def test_build_analysis_module_artifacts_uses_fixed_prompt_and_composed_snapshot():
    writer = _FakeReportWriter(
        "# 石头科技风险与机会洞察简报\n\n## 执行摘要\n\n政策与订单节奏需要联动跟踪。\n\n{{table:opportunity_themes}}\n\n## 关键图表\n\n{{asset:asset_chart_theme_001}}"
    )
    artifacts = build_analysis_module_artifacts(
        analysis_session={"sessionId": "asess_display_001", "revision": 2, "enabledModules": ["robotics_risk"]},
        module_results={
            "robotics_risk": {
                "moduleId": "robotics_risk",
                "displayName": "机器人风险机会洞察",
                "status": "done",
                "runId": "run-display-001",
                "summary": "政策与订单节奏需要联动跟踪。",
                "result": {"briefMarkdown": "# 旧版模块 markdown\n\n旧版兜底正文。"},
                "documentHandoff": {
                    "title": "石头科技风险与机会洞察简报",
                    "executiveSummary": {
                        "headline": "政策与订单是当前主线。",
                        "opportunity": "政策支持改善需求预期。",
                        "risk": "订单兑现仍需持续核验。",
                    },
                    "factTables": [
                        {
                            "tableId": "opportunity_themes",
                            "title": "机会主题",
                            "columns": [{"key": "theme", "label": "主题"}],
                            "rows": [{"rowId": "opp_01", "cells": {"theme": "政策与设备更新"}}],
                        }
                    ],
                    "renderedAssets": [
                        {
                            "assetId": "asset_chart_theme_001",
                            "chartId": "chart_theme_001",
                            "sourceTableId": "opportunity_themes",
                            "contentType": "image/png",
                            "title": "机会主题强度分布",
                            "caption": "用于比较当前机会主线的相对强弱。",
                            "renderPayload": {"dataUrl": "data:image/png;base64,ZmFrZQ=="},
                        }
                    ],
                    "sectionResources": {
                        "opportunities": {
                            "tableIds": ["opportunity_themes"],
                            "assetIds": ["asset_chart_theme_001"],
                        }
                    },
                },
            }
        },
        composer_writer=writer,
    )

    assert len(artifacts) == 1
    artifact = artifacts[0]
    assert writer.calls
    assert writer.calls[0][0]["content"] == load_display_composition_prompt()
    assert artifact["markdownBody"].startswith("# 石头科技风险与机会洞察简报")
    assert "{{table:opportunity_themes}}" in artifact["markdownBody"]
    assert "{{asset:asset_chart_theme_001}}" in artifact["markdownBody"]
    assert "composedMarkdown" not in artifact
    assert "fallbackMarkdown" not in artifact
    assert artifact["displayComposition"]["mode"] == "composed"
    assert artifact["displayComposition"]["promptVersion"] == DISPLAY_COMPOSITION_PROMPT_VERSION


def test_build_analysis_module_artifacts_falls_back_when_composed_snapshot_is_invalid():
    writer = _FakeReportWriter(
        "# 石头科技风险与机会洞察简报\n\nmoduleId=robotics_risk\n\n{{table:missing_table}}"
    )
    artifacts = build_analysis_module_artifacts(
        analysis_session={"sessionId": "asess_display_002", "revision": 3, "enabledModules": ["robotics_risk"]},
        module_results={
            "robotics_risk": {
                "moduleId": "robotics_risk",
                "displayName": "机器人风险机会洞察",
                "status": "done",
                "runId": "run-display-002",
                "result": {"briefMarkdown": "# 旧版模块 markdown\n\n旧版兜底正文。"},
                "documentHandoff": {
                    "title": "石头科技风险与机会洞察简报",
                    "factTables": [
                        {
                            "tableId": "opportunity_themes",
                            "title": "机会主题",
                            "columns": [{"key": "theme", "label": "主题"}],
                            "rows": [{"rowId": "opp_01", "cells": {"theme": "政策与设备更新"}}],
                        }
                    ],
                },
            }
        },
        composer_writer=writer,
    )

    artifact = artifacts[0]
    assert artifact["markdownBody"] == "# 石头科技风险与机会洞察简报"
    assert "fallbackMarkdown" not in artifact
    assert artifact["displayComposition"]["mode"] == "fallback_handoff"
    assert "blocked_internal_field" in artifact["displayComposition"]["validationErrors"]
    assert "unknown_table:missing_table" in artifact["displayComposition"]["validationErrors"]


def test_report_contribution_traceability_validation_rejects_unknown_refs():
    contribution = {
        "findings": [
            {
                "id": "finding_1",
                "title": "未追溯发现",
                "traceRefs": {"domainOutputIds": ["missing"]},
            }
        ]
    }
    domain_analysis = {"domainOutputs": [{"id": "known"}]}

    try:
        validate_report_contribution_traceability(contribution, domain_analysis)
    except ReportContributionValidationError as exc:
        assert "unknown trace ids" in str(exc)
    else:
        raise AssertionError("expected traceability validation error")


def _basic_report_inputs():
    return {
        "analysis_session": {"sessionId": "asess_writer", "revision": 3, "enabledModules": ["robotics_risk"]},
        "handoff_bundle": {
            "analysisSession": {"sessionId": "asess_writer", "revision": 3},
            "enabledModules": ["robotics_risk"],
            "sharedInputSummary": {
                "enterpriseName": "石头科技",
                "stockCode": "688169",
                "timeRange": "近30天",
                "reportGoal": "形成可下载的风险机会报告",
                "analysisFocusTags": ["政策", "订单"],
            },
            "moduleRunIds": {"robotics_risk": "run-robotics-001"},
        },
        "module_results": {
            "robotics_risk": {
                "moduleId": "robotics_risk",
                "displayName": "机器人风险机会洞察",
                "status": "done",
                "runId": "run-robotics-001",
                "summary": "政策支持和订单兑现节奏需要同步跟踪。",
                "domainAnalysis": {
                    "moduleId": "robotics_risk",
                    "domainOutputs": [{"id": "domain_policy_order", "summary": "政策支持和订单兑现节奏需要同步跟踪。"}],
                    "evidence": [{"id": "source_policy_001", "summary": "公开政策文件提及机器人应用支持。"}],
                },
                "documentHandoff": {
                    "factTables": [
                        {
                            "tableId": "opportunity_themes",
                            "title": "机会主题",
                            "columns": [
                                {"key": "theme", "label": "主题"},
                                {"key": "impactScore", "label": "影响分"},
                            ],
                            "rows": [
                                {
                                    "rowId": "opp_theme_001",
                                    "cells": {"theme": "政策与设备更新", "impactScore": 88},
                                }
                            ],
                        }
                    ]
                },
                "reportContribution": {
                    "moduleId": "robotics_risk",
                    "displayName": "机器人风险机会洞察",
                    "status": "done",
                    "findings": [
                        {
                            "id": "finding_policy_order",
                            "kind": "opportunity",
                            "title": "政策支持与订单兑现存在联动机会",
                            "summary": "政策支持提升需求预期，但仍需观察订单兑现节奏。",
                            "traceRefs": {"domainOutputIds": ["domain_policy_order"], "sourceIds": ["source_policy_001"]},
                        }
                    ],
                    "evidence": [
                        {
                            "id": "source_policy_001",
                            "title": "公开政策文件",
                            "summary": "政策文件提及机器人应用支持方向。",
                            "sourceType": "policy",
                            "traceRefs": {"domainOutputIds": ["domain_policy_order"]},
                        }
                    ],
                    "recommendationInputs": [
                        {
                            "id": "recommendation_policy_order",
                            "title": "跟踪政策落地与订单兑现节奏",
                            "summary": "围绕政策落地节点与订单公告建立复核清单。",
                            "traceRefs": {"findingIds": ["finding_policy_order"], "sourceIds": ["source_policy_001"]},
                        }
                    ],
                },
            }
        },
    }


def test_generate_analysis_report_omits_unselected_modules_and_renders_visuals():
    visual_asset = normalize_visual_asset(
        {
            "assetId": "shap_001",
            "type": "chart",
            "subtype": "shap_summary_plot",
            "title": "SHAP特征贡献",
            "altText": "模型特征贡献图",
            "renderPayload": {"text": "feature_a=0.42"},
            "traceRefs": {"modelOutputIds": ["model_001"], "findingIds": ["bankruptcy_finding_1"]},
            "limitations": ["模型贡献不等于现实因果。"],
        },
        module_id="bankruptcy_risk",
    )
    module_results = {
        "bankruptcy_risk": {
            "moduleId": "bankruptcy_risk",
            "displayName": "企业破产风险分析",
            "status": "done",
            "runId": "bankruptcy_run_001",
            "summary": "模型输出显示风险偏高。",
            "domainAnalysis": {
                "moduleId": "bankruptcy_risk",
                "domainOutputs": [{"id": "domain_risk_score", "summary": "风险偏高"}],
                "modelOutputs": [{"id": "model_001", "summary": "probability=0.78"}],
                "visualAssets": [visual_asset],
            },
            "reportContribution": {
                "moduleId": "bankruptcy_risk",
                "displayName": "企业破产风险分析",
                "status": "done",
                "findings": [
                    {
                        "id": "bankruptcy_finding_1",
                        "title": "破产风险偏高",
                        "summary": "模型输出显示风险偏高。",
                        "traceRefs": {"domainOutputIds": ["domain_risk_score"], "modelOutputIds": ["model_001"]},
                    }
                ],
                "modelOutputs": [{"id": "model_001", "title": "破产概率", "summary": "probability=0.78"}],
                "visualAssets": [visual_asset],
                "limitations": ["模型贡献不等于现实因果。"],
            },
        },
        "unselected_policy": {
            "moduleId": "unselected_policy",
            "displayName": "未选择政策分析",
            "status": "done",
            "summary": "不应进入报告。",
        },
    }

    artifact = generate_analysis_report(
        analysis_session={"sessionId": "asess_001", "revision": 4, "enabledModules": ["bankruptcy_risk"]},
        handoff_bundle={
            "analysisSession": {"sessionId": "asess_001", "revision": 4},
            "enabledModules": ["bankruptcy_risk"],
            "sharedInputSummary": {"enterpriseName": "测试公司", "reportGoal": "评估破产风险"},
            "moduleRunIds": {"bankruptcy_risk": "bankruptcy_run_001"},
        },
        module_results=module_results,
    )

    assert artifact["status"] == "completed"
    assert artifact["scope"]["enabledModules"] == ["bankruptcy_risk"]
    assert artifact["semanticModel"]["schemaVersion"] == "report_semantic_model.v1"
    assert artifact["semanticModel"]["keyFindings"][0]["title"] == "破产风险偏高"
    assert artifact["semanticModel"]["modelExplanations"][0]["interpretationBoundary"]
    assert artifact["semanticModel"]["visualNarratives"][0]["interpretationBoundary"]
    assert artifact["internalTraceIndex"]["items"]
    assert "破产风险偏高" in artifact["markdownBody"]
    assert "未选择政策分析" not in artifact["markdownBody"]
    assert "bankruptcy_risk" not in artifact["markdownBody"]
    assert "企业破产风险分析" not in artifact["markdownBody"]
    assert "moduleId" not in artifact["markdownBody"]
    assert "domainOutputIds" not in artifact["markdownBody"]
    assert "modelOutputIds" not in artifact["markdownBody"]
    assert artifact["visualAssets"][0]["downloadUrl"].endswith("/assets/shap_001/download")
    assert "模型贡献不等于现实因果" in artifact["markdownBody"]
    assert artifact["document"]["schemaVersion"] == "analysis_report_document.v1"
    assert [page["type"] for page in artifact["document"]["pages"]] == ["cover", "table_of_contents", "body"]
    assert artifact["document"]["pages"][1]["items"][0]["title"] == "报告范围"


def test_generate_analysis_report_uses_valid_llm_writer_content():
    inputs = _basic_report_inputs()
    writer = _FakeReportWriter(
        json.dumps(
            {
                "title": "石头科技风险机会决策报告",
                "sections": [
                    {
                        "id": "executive_judgement",
                        "title": "核心判断",
                        "blocks": [
                            {
                                "type": "paragraph",
                                "text": "石头科技当前应把政策落地节奏与订单兑现作为同一条决策线索来跟踪。",
                            }
                        ],
                    },
                    {
                        "id": "key_findings",
                        "title": "关键发现",
                        "blocks": [
                            {
                                "type": "items",
                                "items": [
                                    {
                                        "title": "政策与订单节奏需要联动观察",
                                        "readerSummary": "现有材料显示政策支持改善需求预期，但订单兑现仍需要持续核验。",
                                    }
                                ],
                            }
                        ],
                    },
                    {
                        "id": "evidence_verification",
                        "title": "来源与核验",
                        "blocks": [
                            {
                                "type": "evidence",
                                "items": [
                                    {
                                        "title": "公开政策材料",
                                        "readerSummary": "该材料用于支撑政策侧需求预期的判断。",
                                        "verificationStatus": "已纳入本次分析，仍需后续事实更新复核。",
                                    }
                                ],
                            }
                        ],
                    },
                    {
                        "id": "recommendations",
                        "title": "决策建议",
                        "blocks": [
                            {
                                "type": "items",
                                "items": [
                                    {
                                        "title": "建立政策与订单复核清单",
                                        "readerSummary": "按政策落地节点、订单公告和收入兑现进度进行复核。",
                                    }
                                ],
                            }
                        ],
                    },
                ],
            },
            ensure_ascii=False,
        )
    )

    artifact = generate_analysis_report(**inputs, report_writer=writer)

    assert writer.calls
    assert artifact["title"] == "石头科技风险机会决策报告"
    assert "石头科技当前应把政策落地节奏" in artifact["markdownBody"]
    assert "robotics_risk" not in artifact["markdownBody"]
    assert "moduleId" not in artifact["markdownBody"]
    assert any(flag["type"] == "llm_writer" for flag in artifact["qualityFlags"])


def test_generate_analysis_report_rejects_unsafe_llm_writer_content():
    inputs = _basic_report_inputs()
    writer = _FakeReportWriter(
        json.dumps(
            {
                "title": "石头科技报告",
                "sections": [
                    {
                        "id": "executive_judgement",
                        "title": "核心判断",
                        "blocks": [{"type": "paragraph", "text": "moduleId=robotics_risk，run-robotics-001 表明可以新增事实。"}],
                    },
                    {
                        "id": "key_findings",
                        "title": "关键发现",
                        "blocks": [{"type": "items", "items": [{"title": "新增事实", "readerSummary": "自行假设的判断。"}]}],
                    },
                ],
            },
            ensure_ascii=False,
        )
    )

    artifact = generate_analysis_report(**inputs, report_writer=writer)

    assert artifact["status"] == "completed"
    assert "moduleId=robotics_risk" not in artifact["preview"]
    assert "run-robotics-001" not in artifact["markdownBody"]
    assert "自行假设" not in artifact["htmlBody"]
    assert "政策支持与订单兑现存在联动机会" in artifact["markdownBody"]
    assert any(flag["type"] == "llm_writer_fallback" for flag in artifact["qualityFlags"])


def test_generate_analysis_report_cleans_polluted_subject_and_synthesizes_judgement():
    inputs = _basic_report_inputs()
    inputs["handoff_bundle"]["sharedInputSummary"]["enterpriseName"] = "石头科技 688169，时间范围近30天，报告目标是生成风险机会报告"

    artifact = generate_analysis_report(**inputs)

    assert artifact["title"] == "石头科技定制化分析报告"
    assert artifact["scope"]["targetCompany"] == "石头科技"
    assert "688169，时间范围" not in artifact["markdownBody"]
    assert "核心发现包括" not in artifact["markdownBody"]
    assert "已识别 1 项需要关注的判断方向" in artifact["markdownBody"]


def test_report_generation_node_passes_main_llm_to_report_writer():
    inputs = _basic_report_inputs()
    writer = _FakeReportWriter(
        json.dumps(
            {
                "title": "石头科技可下载报告",
                "sections": [
                    {
                        "id": "executive_judgement",
                        "title": "核心判断",
                        "blocks": [{"type": "paragraph", "text": "报告正文已由写作模型面向读者重写。"}],
                    },
                    {
                        "id": "limitations",
                        "title": "限制说明",
                        "blocks": [{"type": "items", "items": [{"title": "复核边界", "readerSummary": "结论需随后续事实更新复核。"}]}],
                    },
                ],
            },
            ensure_ascii=False,
        )
    )

    result = report_generation_node(
        {
            "analysis_session": inputs["analysis_session"],
            "analysis_handoff_bundle": inputs["handoff_bundle"],
            "analysis_results": inputs["module_results"],
            "main_llm": writer,
            "debug": {},
        }
    )

    assert writer.calls
    assert result["analysis_report_generated"] is True
    assert result["analysis_report"]["title"] == "石头科技可下载报告"
    assert "报告正文已由写作模型面向读者重写" in result["analysis_report"]["preview"]


def test_generate_analysis_report_persists_dynamic_outline_and_render_style():
    artifact = generate_analysis_report(**_basic_report_inputs(), render_style="brand_cover")

    outline_titles = [item["title"] for item in artifact["sectionPlan"]]
    assert artifact["renderStyle"] == "brand_cover"
    assert artifact["rendering"]["style"] == "brand_cover"
    assert artifact["document"]["renderStyle"] == "brand_cover"
    assert artifact["semanticModel"]["chapterOutline"][2]["title"] == "关键发现"
    assert "外部环境与风险机会评估" in outline_titles
    assert artifact["document"]["chapterOutline"][3]["title"] == "外部环境与风险机会评估"


def test_generate_analysis_report_from_module_artifacts_prefers_semantic_path():
    inputs = _basic_report_inputs()
    row = AnalysisModuleArtifact(
        artifact_id="mart_semantic_001",
        user_id=1,
        workspace_id="ws-semantic",
        role="investor",
        conversation_id="conv-semantic",
        analysis_session_id="asess_writer",
        analysis_session_revision=3,
        module_id="robotics_risk",
        module_run_id="run-robotics-001",
        title="机器人政策与订单分析",
        status="completed",
        content_type="text/markdown",
        markdown_body="# 石头科技风险与机会洞察简报\n\n## 执行摘要\n\n展示快照只用于前端展示。\n\n{{table:opportunity_themes}}",
        artifact_json={"fallbackMarkdown": "# 机器人政策与订单分析\n\n模块原文分析结果。"},
        metadata_json={
            "displayName": "机器人风险机会洞察",
            "moduleResult": inputs["module_results"]["robotics_risk"],
        },
    )

    artifact = generate_analysis_report_from_module_artifacts([row], render_style="dark_research")

    assert artifact["renderStyle"] == "dark_research"
    assert artifact["rendering"]["style"] == "dark_research"
    assert artifact["document"]["renderStyle"] == "dark_research"
    assert "模块原文分析结果" not in artifact["markdownBody"]
    assert "展示快照只用于前端展示" not in artifact["markdownBody"]
    assert "{{table:opportunity_themes}}" not in artifact["markdownBody"]
    assert "政策支持与订单兑现存在联动机会" in artifact["markdownBody"]
    assert "结构化表格" in artifact["markdownBody"]
    assert "机会主题" in artifact["markdownBody"]
    body_sections = artifact["document"]["pages"][2]["sections"]
    grounded_tables = next(section for section in body_sections if section["id"] == "grounded_tables")
    assert any(block["type"] == "table_block" for block in grounded_tables["blocks"])
    assert all(flag["type"] != "structured_input_missing" for flag in artifact["qualityFlags"])


def test_generate_analysis_report_uses_grounded_table_fallback_for_missing_visual_asset():
    inputs = _basic_report_inputs()
    module_result = inputs["module_results"]["robotics_risk"]
    module_result["documentHandoff"] = {
        "factTables": [
            {
                "tableId": "opportunity_themes",
                "title": "机会主题",
                "columns": [
                    {"key": "theme", "label": "主题"},
                    {"key": "impactScore", "label": "影响分"},
                ],
                "rows": [
                    {
                        "rowId": "opp_theme_001",
                        "cells": {"theme": "政策与设备更新", "impactScore": 88},
                    }
                ],
            }
        ],
        "chartCandidates": [
            {
                "chartId": "chart_theme_001",
                "sourceTableId": "opportunity_themes",
                "fallbackTableId": "opportunity_themes",
                "chartType": "bar",
                "title": "机会主题强度分布",
                "caption": "用于比较当前机会主线的相对强弱。",
                "interpretationBoundary": "图中分值用于相对排序。",
                "series": [{"label": "政策与设备更新", "value": 88, "rowId": "opp_theme_001"}],
            }
        ],
        "evidenceReferences": [
            {
                "id": "source_policy_001",
                "title": "公开政策文件",
                "readerSummary": "政策文件提及机器人应用支持方向。",
            }
        ],
    }
    module_result["domainAnalysis"] = build_robotics_domain_analysis(module_result)
    module_result["reportContribution"] = build_robotics_report_contribution(
        module_result,
        module_result["domainAnalysis"],
    )

    artifact = generate_analysis_report(**inputs)

    assert artifact["semanticModel"]["visualNarratives"][0]["fallbackTableId"] == "opportunity_themes"
    assert "机会主题强度分布" in artifact["htmlBody"]
    assert "图像资产不可用，已按关联结构化表格降级呈现" in artifact["htmlBody"]
    assert "政策与设备更新" in artifact["htmlBody"]


def test_generate_analysis_report_from_module_artifacts_marks_degraded_fallback():
    row = AnalysisModuleArtifact(
        artifact_id="mart_fallback_001",
        user_id=1,
        workspace_id="ws-fallback",
        role="investor",
        conversation_id="conv-fallback",
        analysis_session_id="asess_fallback",
        analysis_session_revision=1,
        module_id="robotics_risk",
        module_run_id="run-fallback-001",
        title="机器人政策与订单分析",
        status="completed",
        content_type="text/markdown",
        markdown_body="# 机器人政策与订单分析\n\n模块原文分析结果。",
        metadata_json={"displayName": "机器人风险机会洞察"},
    )

    artifact = generate_analysis_report_from_module_artifacts([row], render_style="professional")

    assert artifact["status"] == "degraded"
    assert "模块原文分析结果" not in artifact["markdownBody"]
    assert "结构化输入" in artifact["markdownBody"]
    assert "文本拼接回退路径" in artifact["markdownBody"]
    assert any(flag["type"] == "structured_input_missing" for flag in artifact["qualityFlags"])


def test_generate_analysis_report_blocks_published_internal_field_leakage():
    artifact = generate_analysis_report(
        analysis_session={"sessionId": "asess_leak", "revision": 1, "enabledModules": ["leaky_module"]},
        handoff_bundle={
            "analysisSession": {"sessionId": "asess_leak", "revision": 1},
            "enabledModules": ["leaky_module"],
            "sharedInputSummary": {"enterpriseName": "测试公司", "reportGoal": "验证泄露校验"},
            "moduleRunIds": {"leaky_module": "run_leak_001"},
        },
        module_results={
            "leaky_module": {
                "moduleId": "leaky_module",
                "displayName": "泄露测试模块",
                "status": "done",
                "runId": "run_leak_001",
                "domainAnalysis": {"domainOutputs": [{"id": "domain_001", "summary": "已知输出"}]},
                "reportContribution": {
                    "moduleId": "leaky_module",
                    "displayName": "泄露测试模块",
                    "status": "done",
                    "findings": [
                        {
                            "id": "finding_001",
                            "title": "moduleId 不应进入正文",
                            "summary": "traceRefs 不应进入正文。",
                            "traceRefs": {"domainOutputIds": ["domain_001"]},
                        }
                    ],
                },
            }
        },
    )

    assert artifact["status"] == "failed"
    assert "发布报告未通过内部字段泄露校验" in artifact["markdownBody"]
    assert "moduleId 不应进入正文" not in artifact["markdownBody"]
    assert any(flag["type"] == "published_output" for flag in artifact["qualityFlags"])


def test_generate_analysis_report_marks_stale_modules_as_degraded():
    artifact = generate_analysis_report(
        analysis_session={"sessionId": "asess_stale", "revision": 2, "enabledModules": ["robotics_risk"]},
        handoff_bundle={
            "analysisSession": {"sessionId": "asess_stale", "revision": 2},
            "enabledModules": ["robotics_risk"],
            "sharedInputSummary": {"enterpriseName": "石头科技"},
            "staleModules": ["robotics_risk"],
            "limitations": ["输入已更新，模块结果过期。"],
        },
        module_results={
            "robotics_risk": {
                "moduleId": "robotics_risk",
                "displayName": "机器人风险机会洞察",
                "status": "stale",
                "limitations": ["输入已更新，模块结果过期。"],
            }
        },
    )

    assert artifact["status"] == "degraded"
    assert "报告只能作为降级快照使用" in artifact["markdownBody"]
    assert "robotics_risk" not in artifact["markdownBody"]


def test_render_report_pdf_uses_dedicated_cover_and_toc_pages_for_structured_reports():
    artifact = generate_analysis_report(**_basic_report_inputs())

    import fitz

    pdf_bytes = render_report_pdf(artifact)
    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        page_texts = [page.get_text("text") for page in document]

    assert len(page_texts) >= 3
    assert "石头科技定制化分析报告" in page_texts[0]
    assert "目录" not in page_texts[0]
    assert "目录" in page_texts[1]
    assert "报告范围" in page_texts[2]


def test_analysis_session_marks_stale_and_reruns_module_when_shared_slot_changes(monkeypatch):
    run_inputs: list[dict[str, str]] = []

    contract = AnalysisModuleContract(
        module_id="robotics_risk",
        display_name="机器人风险机会洞察",
        required_slots=(
            SHARED_ENTERPRISE_NAME,
            SHARED_TIME_RANGE,
            SHARED_REPORT_GOAL,
            SHARED_ANALYSIS_FOCUS_TAGS,
        ),
        slot_mapping=lambda slots, compatibility, context: {
            "enterpriseName": slots[SHARED_ENTERPRISE_NAME],
            "timeRange": slots[SHARED_TIME_RANGE],
            "reportGoal": slots[SHARED_REPORT_GOAL],
            "focus": "、".join(slots[SHARED_ANALYSIS_FOCUS_TAGS]),
        },
        run=lambda payload: (
            run_inputs.append(dict(payload))
            or {
                "status": "done",
                "runId": f"rerun-{len(run_inputs)}",
                "result": {
                    "summary": {
                        "opportunity": f"{payload['timeRange']} 内的机会信号已汇总。",
                        "risk": f"{payload['timeRange']} 内的风险信号已汇总。",
                    }
                },
                "documentHandoff": {"title": f"{payload['enterpriseName']}-{payload['timeRange']}"},
            }
        ),
    )
    monkeypatch.setattr("app.agent.graph.nodes.get_analysis_module_registry", lambda: {"robotics_risk": contract})

    ready_session = create_transient_analysis_session(enabled_modules=["robotics_risk"])
    ready_session["status"] = "ready"
    ready_session["revision"] = 1
    ready_session["slotValues"] = {
        SHARED_ENTERPRISE_NAME: "石头科技",
        SHARED_TIME_RANGE: "近30天",
        SHARED_REPORT_GOAL: "形成风险机会简报",
        SHARED_ANALYSIS_FOCUS_TAGS: ["政策", "订单"],
    }

    first_run = analysis_modules_node(
        {
            "user_message": "先跑一次",
            "enabled_analysis_modules": ["robotics_risk"],
            "analysis_session": ready_session,
            "debug": {},
        }
    )

    assert first_run["analysis_session"]["status"] == "completed"
    assert first_run["analysis_results"]["robotics_risk"]["runId"] == "rerun-1"
    assert first_run["analysis_results"]["robotics_risk"]["inputSnapshotRevision"] == 1

    updated_intake = analysis_intake_node(
        {
            "user_message": "改成近90天",
            "enabled_analysis_modules": ["robotics_risk"],
            "analysis_shared_inputs": {"timeRange": "近90天"},
            "analysis_module_inputs": {},
            "analysis_session": first_run["analysis_session"],
            "debug": {},
        }
    )

    stale_result = updated_intake["analysis_session"]["moduleResults"]["robotics_risk"]
    stale_state = updated_intake["analysis_session"]["moduleStates"]["robotics_risk"]
    assert updated_intake["needs_clarification"] is False
    assert updated_intake["analysis_session"]["status"] == "stale"
    assert updated_intake["analysis_session"]["revision"] == 2
    assert stale_result["status"] == "stale"
    assert stale_result["stale"] is True
    assert stale_result["staleSlots"] == [SHARED_TIME_RANGE]
    assert stale_state["status"] == "stale"

    rerun = analysis_modules_node(
        {
            "user_message": "重新跑",
            "enabled_analysis_modules": ["robotics_risk"],
            "analysis_session": updated_intake["analysis_session"],
            "debug": {},
        }
    )

    assert rerun["analysis_session"]["status"] == "completed"
    assert rerun["analysis_results"]["robotics_risk"]["runId"] == "rerun-2"
    assert rerun["analysis_results"]["robotics_risk"]["inputSnapshotRevision"] == 2
    assert rerun["analysis_handoff_bundle"]["analysisSession"]["revision"] == 2
    assert rerun["analysis_handoff_bundle"]["sharedInputSummary"]["timeRange"] == "近90天"
    assert rerun["analysis_handoff_bundle"].get("staleModules", []) == []
    assert [item["timeRange"] for item in run_inputs] == ["近30天", "近90天"]


def test_search_subagent_reports_missing_evidence(app):
    with app.app_context():
        result = search_subagent_node(
            {
                "user_message": "根据文档回答",
                "user_id": 1,
                "workspace_id": "ws-1",
                "rag_enabled": False,
                "rag_debug_enabled": False,
                "search_request": {"query": "根据文档回答", "preferred_strategy": "private_only"},
                "debug": {},
            }
        )
    assert result["search_completed"] is True
    assert result["needs_clarification"] is True
    assert result["rag_no_evidence"] is True


def test_search_subagent_queries_knowledge_graph(app, monkeypatch):
    class _FakeKnowledgeGraphTool:
        name = "knowledge_graph_query"

        def invoke(self, **kwargs):
            assert kwargs["entity"] == "京东方"
            assert kwargs["intent"] == "股权关系"
            return {
                "ok": True,
                "summary": "知识图谱命中了京东方股权关系。",
                "graph": {"nodes": [{"id": "boe", "label": "京东方", "type": "company"}], "edges": []},
                "meta": {"source": "knowledge_graph", "contextSize": 1},
            }

    def _fake_get_agent_tools(**kwargs):
        categories = tuple(kwargs.get("categories", ()))
        if categories == ("knowledge_graph",):
            return [_FakeKnowledgeGraphTool()]
        return []

    app.config["AGENT_KNOWLEDGE_GRAPH_ENABLED"] = True
    monkeypatch.setattr("app.agent.graph.search.get_agent_tools", _fake_get_agent_tools)

    with app.app_context():
        result = search_subagent_node(
            {
                "user_message": "请查知识图谱",
                "user_id": 1,
                "workspace_id": "ws-1",
                "kg_enabled": True,
                "entity": "京东方",
                "graph_intent": "股权关系",
                "rag_enabled": False,
                "rag_debug_enabled": False,
                "search_request": {
                    "query": "请查知识图谱",
                    "preferred_strategy": "private_only",
                    "entity": "京东方",
                    "graph_intent": "股权关系",
                },
                "debug": {},
            }
        )

    assert result["search_completed"] is True
    assert result["graph_data"]["nodes"][0]["label"] == "京东方"
    assert result["graph_meta"]["source"] == "knowledge_graph"
    assert result["search_result"]["status"] == "done"


def test_mcp_subagent_requests_server_clarification_when_ambiguous(app):
    app.config["AGENT_MCP_ENABLED"] = True
    app.config["AGENT_MCP_SERVERS_JSON"] = '{"alpha":{"endpoint":"http://127.0.0.1:8080/a"},"beta":{"endpoint":"http://127.0.0.1:8080/b"}}'
    with app.app_context():
        result = mcp_subagent_node(
            {
                "user_message": "列出mcp工具",
                "user_id": 1,
                "workspace_id": "ws-1",
                "mcp_request": {"request": "列出mcp工具"},
                "debug": {},
            }
        )
    assert result["mcp_completed"] is True
    assert result["needs_clarification"] is True
    assert "server" in result["clarification_question"].lower()
