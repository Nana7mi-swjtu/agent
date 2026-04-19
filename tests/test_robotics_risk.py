from __future__ import annotations

import inspect

import pytest

from app.robotics_risk import (
    RoboticsInsightRequest,
    RoboticsInsightValidationError,
    analyze_robotics_enterprise_risk_opportunity,
)
from app.robotics_risk.adapters import SourceCollectionResult, SourceUnavailableError
from app.robotics_risk.adapters.bidding import BiddingProcurementAdapter
from app.robotics_risk.adapters.cninfo import CninfoAnnouncementAdapter
from app.robotics_risk.adapters.policy import GovPolicyAdapter
from app.robotics_risk.profiling import build_enterprise_profile
from app.robotics_risk.schemas import EnterpriseProfile, RoboticsInsightRequest, SourceDocument
from app.robotics_risk import service as robotics_service


def _policy_doc() -> SourceDocument:
    return SourceDocument(
        id="src_policy_001",
        source_type="gov_policy",
        source_name="国务院政策文件库",
        title="关于推动智能制造和机器人应用场景建设的政策",
        content="政策鼓励智能制造、服务机器人、清洁机器人和养老机器人应用，推动设备更新。",
        url="https://www.gov.cn/example",
        published_at="2026-04-01",
        authority_score=0.95,
        relevance_scope="industry",
    )


def _announcement_doc() -> SourceDocument:
    return SourceDocument(
        id="src_cninfo_001",
        source_type="cninfo_announcement",
        source_name="巨潮资讯网",
        title="石头科技关于新产品研发和重大合同的公告",
        content="公司发布新产品并签订重大合同，研发投入持续增长。",
        url="https://static.cninfo.com.cn/example.pdf",
        published_at="2026-04-02",
        authority_score=0.95,
        relevance_scope="enterprise",
    )


def _bidding_doc() -> SourceDocument:
    return SourceDocument(
        id="src_bid_001",
        source_type="bidding_procurement",
        source_name="全国公共资源交易/招标采购信息源",
        title="某地清洁机器人采购项目中标公告",
        content="该项目采购清洁机器人、服务机器人，用于公共场所智能清洁。",
        url="https://www.ggzy.gov.cn/example",
        published_at="2026-04-03",
        authority_score=0.85,
        relevance_scope="market_demand",
    )


class FakeFailingAdapter:
    source_type = "bidding_procurement"

    def collect(self, *, request: RoboticsInsightRequest, profile: EnterpriseProfile):
        raise SourceUnavailableError(self.source_type, "captcha required")


def test_minimal_enterprise_request_uses_defaults():
    result = analyze_robotics_enterprise_risk_opportunity(
        RoboticsInsightRequest(enterprise_name="石头科技"),
        adapters=[GovPolicyAdapter(documents=[_policy_doc()])],
    )

    payload = result.to_dict()
    assert payload["targetCompany"]["name"] == "石头科技"
    assert payload["analysisScope"]["time_range"] == "近30天"
    assert "扫地机器人" in payload["enterpriseProfile"]["segments"]
    assert payload["module"] == "robotics_enterprise_risk_opportunity"


def test_missing_enterprise_name_is_rejected():
    with pytest.raises(RoboticsInsightValidationError):
        analyze_robotics_enterprise_risk_opportunity({"enterpriseName": ""}, adapters=[])


@pytest.mark.parametrize(
    ("enterprise", "context", "expected"),
    [
        ("石头科技", "", "扫地机器人"),
        ("优必选", "人形机器人", "人形机器人"),
        ("埃斯顿", "工业机器人", "工业机器人"),
        ("绿的谐波", "减速器", "核心零部件"),
    ],
)
def test_robotics_profile_infers_segments(enterprise, context, expected):
    profile = build_enterprise_profile(RoboticsInsightRequest(enterprise_name=enterprise, context=context))

    assert expected in profile.segments
    assert profile.keywords


def test_fake_adapters_produce_sources_events_signals_and_payload_refs():
    result = analyze_robotics_enterprise_risk_opportunity(
        RoboticsInsightRequest(
            enterprise_name="石头科技",
            stock_code="688169",
            time_range="近30天",
            focus="综合",
            dimensions=["政策", "公告", "招中标"],
        ),
        adapters=[
            GovPolicyAdapter(documents=[_policy_doc()]),
            CninfoAnnouncementAdapter(documents=[_announcement_doc()]),
            BiddingProcurementAdapter(documents=[_bidding_doc()]),
        ],
    )
    payload = result.to_dict()

    assert len(payload["sources"]) == 3
    assert payload["events"]
    assert payload["opportunities"]
    assert payload["briefMarkdown"].startswith("# 石头科技风险与机会洞察简报")
    source_ids = {item["id"] for item in payload["sources"]}
    for event in payload["events"]:
        assert event["source_document_id"] in source_ids
    for signal in payload["opportunities"] + payload.get("risks", []):
        assert signal["source_ids"]
        assert set(signal["source_ids"]).issubset(source_ids)


def test_source_failures_degrade_independently_and_record_limitations():
    result = analyze_robotics_enterprise_risk_opportunity(
        RoboticsInsightRequest(enterprise_name="石头科技"),
        adapters=[
            GovPolicyAdapter(documents=[_policy_doc()]),
            FakeFailingAdapter(),
        ],
    )
    payload = result.to_dict()

    assert payload["sources"]
    assert any("captcha required" in item for item in payload["limitations"])
    assert payload["opportunities"]


def test_boundary_service_does_not_depend_on_main_agent_or_workspace_chat():
    source = inspect.getsource(robotics_service)

    assert "app.agent" not in source
    assert "workspace" not in source.lower()
    assert "langgraph" not in source.lower()
    assert "flask" not in source.lower()
