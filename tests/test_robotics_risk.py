from __future__ import annotations

import inspect
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.models import (
    RagChunk,
    RagDocument,
    RagIndexJob,
    RoboticsBiddingDocument,
    RoboticsCninfoAnnouncement,
    RoboticsInsightRun,
    RoboticsListedCompanyProfile,
    RoboticsPolicyDocument,
)
from app.robotics_risk import (
    RoboticsRiskSubagentInput,
    RoboticsInsightRequest,
    RoboticsInsightValidationError,
    analyze_robotics_enterprise_risk_opportunity,
    build_document_handoff,
    run_robotics_risk_subagent,
)
from app.robotics_risk.adapters import SourceCollectionResult, SourceUnavailableError
from app.robotics_risk.adapters.bidding import (
    BiddingPage,
    BiddingProcurementAdapter,
    parse_bidding_candidates_page,
    parse_bidding_detail_page,
)
from app.robotics_risk.adapters.cninfo import CninfoAnnouncementAdapter, CninfoAnnouncementRecord, CninfoQueryPlan
from app.robotics_risk.adapters.policy import GovPolicyAdapter, GovPolicyPage, parse_policy_candidates_page, parse_policy_detail_page
from app.robotics_risk.cache import RoboticsEvidenceCache, SourceFreshnessPolicy
from app.robotics_risk.bidding_planning import DEFAULT_BIDDING_NOTICE_CATEGORIES, build_bidding_search_plan
from app.robotics_risk.company_resolution import ListedCompanyResolver
from app.robotics_risk.company_seed import seed_robotics_listed_company_profiles
from app.robotics_risk.pdf_text import PdfTextExtractionResult, extract_pdf_text
from app.robotics_risk.policy_planning import build_policy_search_plan
from app.robotics_risk.profiling import build_enterprise_profile
from app.robotics_risk.repository import RoboticsEvidenceRepository, build_cache_key
from app.robotics_risk.run_repository import RoboticsInsightRunRepository
from app.robotics_risk.schemas import EnterpriseProfile, RoboticsInsightRequest, SourceDocument
from app.robotics_risk import subagent as robotics_subagent
from app.robotics_risk import service as robotics_service


class _FakeReaderResponse:
    def __init__(self, content):
        self.content = content


class _FakeReaderWriter:
    def __init__(self, content):
        self.content = content
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        return _FakeReaderResponse(self.content)


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


class CountingAdapter:
    def __init__(self, *, source_type: str, documents: list[SourceDocument] | None = None, fail: str = "") -> None:
        self.source_type = source_type
        self.documents = list(documents or [])
        self.fail = fail
        self.calls = 0

    def collect(self, *, request: RoboticsInsightRequest, profile: EnterpriseProfile):
        self.calls += 1
        if self.fail:
            raise SourceUnavailableError(self.source_type, self.fail)
        return SourceCollectionResult(documents=self.documents)


class ShouldNotCallAdapter:
    def __init__(self, source_type: str) -> None:
        self.source_type = source_type
        self.calls = 0

    def collect(self, *, request: RoboticsInsightRequest, profile: EnterpriseProfile):
        self.calls += 1
        raise AssertionError(f"{self.source_type} adapter should not be called")


class FakeCninfoClient:
    def __init__(self, records: list[CninfoAnnouncementRecord] | None = None, fail: Exception | None = None) -> None:
        self.records = list(records or [])
        self.fail = fail
        self.plans: list[CninfoQueryPlan] = []

    def query_announcements(self, plan: CninfoQueryPlan) -> list[CninfoAnnouncementRecord]:
        self.plans.append(plan)
        if self.fail is not None:
            raise self.fail
        return list(self.records)


class PlanAwareCninfoClient:
    def __init__(self, records_by_query_type: dict[str, list[CninfoAnnouncementRecord]]) -> None:
        self.records_by_query_type = {
            key: list(value) for key, value in records_by_query_type.items()
        }
        self.plans: list[CninfoQueryPlan] = []

    def query_announcements(self, plan: CninfoQueryPlan) -> list[CninfoAnnouncementRecord]:
        self.plans.append(plan)
        key = f"{plan.query_type}:{plan.search_key}"
        return list(self.records_by_query_type.get(key, self.records_by_query_type.get(plan.query_type, [])))


class FakeGovPolicyClient:
    def __init__(
        self,
        *,
        search_html: str = "",
        list_html: str = "",
        detail_pages: dict[str, str] | None = None,
        json_pages: dict[str, str] | None = None,
        fail_search: Exception | None = None,
        fail_detail_urls: set[str] | None = None,
    ) -> None:
        self.search_html = search_html
        self.list_html = list_html
        self.detail_pages = dict(detail_pages or {})
        self.json_pages = dict(json_pages or {})
        self.fail_search = fail_search
        self.fail_detail_urls = set(fail_detail_urls or set())
        self.searches: list[tuple[str, str, int]] = []
        self.lists: list[tuple[str, int]] = []
        self.details: list[str] = []
        self.jsons: list[str] = []

    def fetch_search_page(self, *, query: str, scope: str, page: int):
        self.searches.append((query, scope, page))
        if self.fail_search is not None:
            raise self.fail_search
        return GovPolicyPage(url=f"https://www.gov.cn/search?q={query}&scope={scope}", html=self.search_html)

    def fetch_list_page(self, *, scope: str, page: int):
        self.lists.append((scope, page))
        return GovPolicyPage(url=f"https://www.gov.cn/zhengce/zhengceku/{scope}/index.htm", html=self.list_html)

    def fetch_detail_page(self, url: str):
        self.details.append(url)
        if url in self.fail_detail_urls:
            raise SourceUnavailableError("gov_policy", "detail blocked")
        return GovPolicyPage(url=url, html=self.detail_pages.get(url, ""))

    def fetch_json_page(self, url: str):
        self.jsons.append(url)
        return GovPolicyPage(url=url, html=self.json_pages.get(url, "[]"))


class FakeCebBiddingClient:
    def __init__(
        self,
        *,
        search_html: str = "",
        detail_pages: dict[str, str] | None = None,
        fail_search: Exception | None = None,
        blocked_search: bool = False,
    ) -> None:
        self.search_html = search_html
        self.detail_pages = dict(detail_pages or {})
        self.fail_search = fail_search
        self.blocked_search = blocked_search
        self.searches: list[tuple[str, str, int]] = []
        self.details: list[str] = []

    def fetch_search_page(self, *, query: str, notice_category: str, page: int):
        self.searches.append((query, notice_category, page))
        if self.fail_search is not None:
            raise self.fail_search
        html = "验证码 安全验证" if self.blocked_search else self.search_html
        return BiddingPage(url=f"https://custominfo.cebpubservice.com/search?keyword={query}", html=html)

    def fetch_detail_page(self, url: str):
        self.details.append(url)
        return BiddingPage(url=url, html=self.detail_pages.get(url, ""))


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


def test_policy_search_plan_uses_profile_segments_domains_and_bounds():
    request = RoboticsInsightRequest(
        enterprise_name="石头科技",
        time_range="近90天",
        focus="清洁机器人政府采购",
        context="扫地机器人",
    )
    profile = build_enterprise_profile(request)

    plan = build_policy_search_plan(request=request, profile=profile, max_queries=8, max_pages=2, detail_fetch_limit=3)

    assert len(plan.query_terms) == 8
    assert plan.max_pages == 2
    assert plan.detail_fetch_limit == 3
    assert plan.start_date
    assert "state_council" in plan.source_scopes
    assert any(term.matched_segment == "扫地机器人" for term in plan.query_terms)
    assert any(term.policy_domain for term in plan.query_terms)
    assert any("截断" in item for item in plan.limitations)


def test_policy_search_plan_generic_profile_reports_limitation():
    request = RoboticsInsightRequest(enterprise_name="未映射企业", time_range="本季度")
    profile = build_enterprise_profile(request)

    plan = build_policy_search_plan(request=request, profile=profile, max_queries=4)

    assert "机器人" in " ".join(plan.keywords)
    assert any("通用机器人政策关键词" in item for item in plan.limitations)
    assert any("时间范围" in item for item in plan.limitations)


def test_bidding_search_plan_uses_enterprise_segment_scenario_categories_and_bounds():
    request = RoboticsInsightRequest(
        enterprise_name="石头科技",
        time_range="近60天",
        focus="广东清洁机器人招投标",
        context="扫地机器人 公共清洁",
    )
    profile = build_enterprise_profile(request)

    plan = build_bidding_search_plan(request=request, profile=profile, max_queries=6, max_pages=2, detail_fetch_limit=3)

    assert len(plan.query_terms) == 6
    assert plan.max_pages == 2
    assert plan.detail_fetch_limit == 3
    assert plan.start_date
    assert set(DEFAULT_BIDDING_NOTICE_CATEGORIES).issubset(set(plan.notice_categories))
    assert "广东" in plan.region_hints
    assert any(term.source == "enterprise" and "石头科技" in term.keyword for term in plan.query_terms)
    assert any(term.matched_segment == "扫地机器人" for term in plan.query_terms)
    assert any("截断" in item for item in plan.limitations)


def test_bidding_search_plan_generic_profile_reports_limitation():
    request = RoboticsInsightRequest(enterprise_name="未映射机器人公司", time_range="本季度")
    profile = EnterpriseProfile(name="未映射机器人公司", segments=["机器人行业"], keywords=["机器人"])

    plan = build_bidding_search_plan(request=request, profile=profile, max_queries=4)

    assert any("机器人" in keyword for keyword in plan.keywords)
    assert any("通用机器人采购关键词" in item for item in plan.limitations)
    assert any("时间范围" in item for item in plan.limitations)


def test_gov_policy_candidate_and_detail_parsing_records_metadata_and_attachments():
    list_html = """
    <html><body>
      <ul>
        <li><a href="/zhengce/zhengceku/gwywj/2026-04/01/content_123456.htm">国务院办公厅关于加快机器人应用场景建设的意见</a><span>2026-04-01</span></li>
      </ul>
    </body></html>
    """
    detail_html = """
    <html><head>
      <meta name="PubDate" content="2026-04-01">
      <meta name="ContentId" content="content_123456">
    </head><body>
      <h1>国务院办公厅关于加快机器人应用场景建设的意见</h1>
      <div>发文机关：国务院办公厅 文号：国办发〔2026〕1号</div>
      <div class="pages_content">
        <p>政策鼓励人形机器人、服务机器人在养老、医疗、教育、物流等场景开放应用。</p>
        <p>推动设备更新和智能制造改造。</p>
      </div>
      <a href="./annex.pdf">附件：重点任务清单.pdf</a>
    </body></html>
    """

    candidates = parse_policy_candidates_page(list_html, "https://www.gov.cn/zhengce/zhengceku/gwywj/index.htm", default_scope="state_council")
    detail = parse_policy_detail_page(detail_html, candidates[0].url, candidate=candidates[0])

    assert len(candidates) == 1
    assert candidates[0].source_scope == "state_council"
    assert detail.policy_id == "content_123456"
    assert detail.issuing_agency == "国务院办公厅"
    assert detail.document_number == "国办发〔2026〕1号"
    assert "服务机器人" in detail.content
    assert detail.attachments[0]["fileType"] == "pdf"


def test_gov_policy_adapter_searches_fetches_details_and_degrades_metadata_only():
    policy_url = "https://www.gov.cn/zhengce/zhengceku/gwywj/2026-04/01/content_123456.htm"
    search_html = f'<a href="{policy_url}">国务院办公厅关于加快机器人应用场景建设的意见</a><span>2026-04-01</span>'
    detail_html = """
    <h1>国务院办公厅关于加快机器人应用场景建设的意见</h1>
    <div class="pages_content">政策鼓励服务机器人和清洁机器人应用，推动设备更新。</div>
    """
    client = FakeGovPolicyClient(search_html=search_html, detail_pages={policy_url: detail_html})
    adapter = GovPolicyAdapter(client=client, max_queries=2, detail_fetch_limit=1)

    result = adapter.collect(
        request=RoboticsInsightRequest(enterprise_name="石头科技", context="扫地机器人"),
        profile=EnterpriseProfile(name="石头科技", segments=["扫地机器人"], keywords=["扫地机器人", "服务机器人"]),
    )

    assert client.searches
    assert client.details == [policy_url]
    assert len(result.documents) == 1
    document = result.documents[0]
    assert document.source_type == "gov_policy"
    assert document.relevance_scope == "industry"
    assert document.metadata["sourceScope"] == "state_council"
    assert document.metadata["searchKeyword"]
    assert document.metadata["policySearchPlan"]["keywords"]


def test_gov_policy_adapter_uses_list_fallback_and_reports_detail_failure():
    policy_url = "https://www.gov.cn/zhengce/zhengceku/bmwj/2026-04/02/content_999999.htm"
    list_html = f'<a href="{policy_url}">工业和信息化部关于机器人标准化工作的通知</a><span>2026-04-02</span>'
    client = FakeGovPolicyClient(list_html=list_html, detail_pages={}, fail_detail_urls={policy_url})
    adapter = GovPolicyAdapter(client=client, max_queries=1, detail_fetch_limit=1)

    result = adapter.collect(
        request=RoboticsInsightRequest(enterprise_name="埃斯顿", context="工业机器人"),
        profile=EnterpriseProfile(name="埃斯顿", segments=["工业机器人"], keywords=["工业机器人"]),
    )

    assert client.lists
    assert not result.documents
    assert any("详情页不可用" in item for item in result.limitations)


def test_gov_policy_adapter_handles_redirect_shell_and_json_list_fallback():
    policy_url = "https://www.gov.cn/zhengce/zhengceku/gwywj/2026-04/03/content_json.htm"
    redirect_html = '<script>window.location.href="https://sousuo.www.gov.cn/zcwjk/policyDocumentLibrary?q=&t=zhengcelibrary"</script>'
    list_url = "https://www.gov.cn/zhengce/zhengceku/gwywj/TONGYONGGAILAN.json"
    list_html = '<script>$.ajax({ url: "./TONGYONGGAILAN.json", success: function(resultP){ FY_DATA = resultP; } })</script>'
    json_payload = f'[{{"TITLE":"国务院办公厅关于推进机器人应用的意见","URL":"{policy_url}","DOCRELPUBTIME":"2026-04-03","DOCID":"content_json"}}]'
    detail_html = '<h1>国务院办公厅关于推进机器人应用的意见</h1><div class="pages_content">政策鼓励服务机器人和工业机器人应用。</div>'
    client = FakeGovPolicyClient(
        search_html=redirect_html,
        list_html=list_html,
        json_pages={
            list_url: json_payload,
            "https://www.gov.cn/zhengce/zhengceku/state_council/TONGYONGGAILAN.json": json_payload,
            "https://www.gov.cn/zhengce/zhengceku/department/TONGYONGGAILAN.json": "[]",
        },
        detail_pages={policy_url: detail_html},
    )
    adapter = GovPolicyAdapter(client=client, max_queries=1, detail_fetch_limit=1)

    result = adapter.collect(
        request=RoboticsInsightRequest(enterprise_name="埃斯顿", context="工业机器人"),
        profile=EnterpriseProfile(name="埃斯顿", segments=["工业机器人"], keywords=["工业机器人"]),
    )

    assert client.jsons
    assert any(item.endswith("TONGYONGGAILAN.json") for item in client.jsons)
    assert result.documents
    assert any("跳转壳" in item for item in result.limitations)
    assert result.diagnostics[0].status == "done"
    assert result.diagnostics[0].raw_count == 1


def test_ceb_bidding_candidate_and_detail_parsing_records_metadata_and_attachments():
    list_html = """
    <html><body>
      <a href="/bulletin/2026/04/notice-001.html">广东公共场所清洁机器人采购项目中标结果公告</a>
      <span>2026-04-10</span>
    </body></html>
    """
    detail_html = """
    <html><head><meta name="noticeId" content="notice-001"></head><body>
      <h1>广东公共场所清洁机器人采购项目中标结果公告</h1>
      <div class="article">
        项目名称：广东公共场所清洁机器人采购项目
        项目编号：GD-RB-001
        采购人：广州市城市管理局
        中标人：石头科技
        中标金额：320万元
        发布时间：2026-04-10
        本项目采购清洁机器人和服务机器人，用于公共场所智能清洁。
      </div>
      <a href="./result.pdf">中标结果附件.pdf</a>
    </body></html>
    """

    candidates = parse_bidding_candidates_page(
        list_html,
        "https://custominfo.cebpubservice.com/search",
        notice_category="winning_result",
    )
    detail = parse_bidding_detail_page(detail_html, candidates[0].url, candidate=candidates[0])

    assert len(candidates) == 1
    assert candidates[0].notice_type == "中标结果公告"
    assert detail.notice_id == "notice-001"
    assert detail.project_name == "广东公共场所清洁机器人采购项目"
    assert detail.project_code == "GD-RB-001"
    assert detail.buyer_name == "广州市城市管理局"
    assert detail.winning_bidder == "石头科技"
    assert detail.amount == "320万元"
    assert detail.region == "广东"
    assert detail.attachments[0]["fileType"] == "pdf"


def test_bidding_adapter_searches_details_classifies_direct_and_metadata_only():
    detail_url = "https://custominfo.cebpubservice.com/bulletin/notice-001.html"
    search_html = f'<a href="{detail_url}">广东公共场所清洁机器人采购项目中标结果公告</a><span>2026-04-10</span>'
    detail_html = """
    <h1>广东公共场所清洁机器人采购项目中标结果公告</h1>
    <div id="content">
      项目名称：广东公共场所清洁机器人采购项目
      采购人：广州市城市管理局
      中标人：石头科技
      中标金额：320万元
      本项目采购清洁机器人。
    </div>
    """
    client = FakeCebBiddingClient(search_html=search_html, detail_pages={detail_url: detail_html})
    adapter = BiddingProcurementAdapter(client=client, max_queries=1, detail_fetch_limit=1)

    result = adapter.collect(
        request=RoboticsInsightRequest(enterprise_name="石头科技", context="扫地机器人"),
        profile=EnterpriseProfile(name="石头科技", segments=["扫地机器人"], keywords=["清洁机器人"]),
    )

    assert client.searches
    assert client.details == [detail_url]
    assert len(result.documents) == 1
    document = result.documents[0]
    assert document.source_type == "bidding_procurement"
    assert document.source_name == "中国招标投标公共服务平台"
    assert document.relevance_scope == "enterprise"
    assert document.metadata["directMatchRole"] == "winner"
    assert document.metadata["noticeCategory"]
    assert document.metadata["biddingSearchPlan"]["keywords"]


def test_bidding_adapter_degrades_blocked_and_empty_source():
    adapter = BiddingProcurementAdapter(client=FakeCebBiddingClient(blocked_search=True), max_queries=1)

    result = adapter.collect(
        request=RoboticsInsightRequest(enterprise_name="石头科技", context="扫地机器人"),
        profile=EnterpriseProfile(name="石头科技", segments=["扫地机器人"], keywords=["清洁机器人"]),
    )

    assert not result.documents
    assert any("反爬限制" in item for item in result.limitations)
    assert any("未返回" in item for item in result.limitations)
    assert result.diagnostics[0].status == "blocked"


def test_bidding_parser_rejects_navigation_false_positives_and_detects_encrypted_block():
    nav_html = """
    <a href="/xxgk/index.html">信息公开</a>
    <a href="/notice/index.html">公告公示</a>
    <a href="/bulletin/notice-robot.html">广东清洁机器人采购项目招标公告</a>
    """
    candidates = parse_bidding_candidates_page(nav_html, "http://www.cebpubservice.com/")

    assert [item.title for item in candidates] == ["广东清洁机器人采购项目招标公告"]

    blocked = BiddingProcurementAdapter(
        client=FakeCebBiddingClient(search_html="<script>eval(function(){})</script>ctbpsp.com/cutominfoapi"),
        max_queries=1,
    ).collect(
        request=RoboticsInsightRequest(enterprise_name="石头科技", context="扫地机器人"),
        profile=EnterpriseProfile(name="石头科技", segments=["扫地机器人"], keywords=["清洁机器人"]),
    )

    assert not blocked.documents
    assert blocked.diagnostics[0].status == "blocked"


def test_metadata_only_bidding_notice_is_attributed_and_limited():
    detail_url = "https://custominfo.cebpubservice.com/bulletin/notice-meta.html"
    search_html = f'<a href="{detail_url}">清洁机器人采购项目招标公告</a><span>2026-04-10</span>'
    detail_html = "<h1>清洁机器人采购项目招标公告</h1>"
    client = FakeCebBiddingClient(search_html=search_html, detail_pages={detail_url: detail_html})

    result = analyze_robotics_enterprise_risk_opportunity(
        RoboticsInsightRequest(enterprise_name="石头科技", context="扫地机器人"),
        adapters=[BiddingProcurementAdapter(client=client, max_queries=1, detail_fetch_limit=1)],
    )

    assert result.sources
    assert result.sources[0].metadata["status"] == "metadata_limited"
    assert any("公告正文提取受限" in item for item in result.limitations)


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
    assert "briefMarkdown" not in payload
    assert payload["readerPacket"]["executiveSummary"]["headline"]
    assert payload["readerPacket"]["evidenceReferences"]
    assert payload["readerPacket"]["visualSummaries"]
    assert payload["readerPacket"]["factTableRefs"]
    assert payload["readerPacket"]["chartCandidateRefs"]
    assert payload["readerPacket"]["renderedAssetRefs"]
    assert payload["factTables"]
    assert payload["chartCandidates"]
    assert payload["renderedAssets"]
    opportunity_table = next(item for item in payload["factTables"] if item["tableId"] == "opportunity_themes")
    assert opportunity_table["rows"][0]["traceRefs"]["sourceIds"]
    assert opportunity_table["rows"][0]["traceRefs"]["signalIds"]
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


def test_document_handoff_payload_contains_sections_citations_and_evidence():
    result = analyze_robotics_enterprise_risk_opportunity(
        RoboticsInsightRequest(enterprise_name="石头科技", stock_code="688169"),
        adapters=[
            GovPolicyAdapter(documents=[_policy_doc()]),
            CninfoAnnouncementAdapter(documents=[_announcement_doc()]),
        ],
    )

    handoff = build_document_handoff(result)

    assert handoff["documentType"] == "robotics_risk_opportunity_brief"
    assert handoff["title"] == "石头科技风险与机会洞察简报"
    assert [section["id"] for section in handoff["recommendedSections"]] == [
        "executive_summary",
        "opportunities",
        "risks",
        "visuals",
        "evidence",
        "limitations",
    ]
    assert handoff["opportunitySections"]
    assert handoff["evidenceTable"]
    assert handoff["readerPacket"]["schemaVersion"] == "robotics_reader_packet.v1"
    assert handoff["evidenceReferences"]
    assert handoff["visualSummaries"]
    assert handoff["factTables"]
    assert handoff["chartCandidates"]
    assert handoff["renderedAssets"]
    assert handoff["sectionResources"]["opportunities"]["tableIds"] == ["opportunity_themes"]
    assert handoff["sectionResources"]["opportunities"]["assetIds"]
    assert handoff["recommendedSections"][1]["resourceRefs"]["tableIds"] == ["opportunity_themes"]
    first_theme = handoff["opportunitySections"][0]
    assert handoff["citationMap"]["themes"][first_theme["id"]]["sourceIds"]
    assert handoff["citationMap"]["factTables"]["opportunity_themes"]["sourceIds"]
    assert handoff["citationMap"]["chartCandidates"]["chart_opportunity_theme_strength"]["sourceTableId"] == "opportunity_themes"
    assert "compactMarkdown" not in handoff


def test_document_handoff_handles_empty_sections_and_metadata_limitations():
    empty_result = analyze_robotics_enterprise_risk_opportunity(
        RoboticsInsightRequest(enterprise_name="石头科技", stock_code="688169"),
        adapters=[],
    )
    empty_handoff = build_document_handoff(empty_result)

    assert empty_result.status == "no_evidence"
    assert not empty_result.opportunities
    assert not empty_result.risks
    assert empty_result.fact_tables
    empty_tables = {item["tableId"]: item for item in empty_result.fact_tables}
    assert empty_tables["opportunity_themes"]["rows"][0]["emptyState"] is True
    assert empty_tables["risk_themes"]["rows"][0]["emptyState"] is True
    empty_section_by_id = {section["id"]: section for section in empty_handoff["recommendedSections"]}
    assert empty_section_by_id["opportunities"].get("emptyState") == "未发现高置信度机会信号。"
    assert empty_section_by_id["risks"].get("emptyState") == "未发现高置信度风险信号。"

    metadata_only = SourceDocument(
        id="src_meta_001",
        source_type="bidding_procurement",
        source_name="中国招标投标公共服务平台",
        title="清洁机器人采购项目招标公告",
        content="",
        published_at="2026-04-03",
        metadata={"status": "metadata_limited", "errorMessage": "公告正文提取受限"},
    )
    result = analyze_robotics_enterprise_risk_opportunity(
        RoboticsInsightRequest(enterprise_name="石头科技", stock_code="688169"),
        adapters=[BiddingProcurementAdapter(documents=[metadata_only])],
    )

    handoff = build_document_handoff(result)

    assert handoff["evidenceTable"][0]["metadataOnlyNote"] == "公告正文提取受限"
    assert handoff["evidenceTable"][0]["sourceId"] == "src_meta_001"


def test_rendered_assets_include_png_data_urls_and_traceable_chart_links():
    result = analyze_robotics_enterprise_risk_opportunity(
        RoboticsInsightRequest(enterprise_name="石头科技", stock_code="688169"),
        adapters=[
            GovPolicyAdapter(documents=[_policy_doc()]),
            CninfoAnnouncementAdapter(documents=[_announcement_doc()]),
        ],
    )

    asset = result.rendered_assets[0]

    assert asset["contentType"] == "image/png"
    assert asset["chartId"]
    assert asset["sourceTableId"]
    assert asset["renderPayload"]["dataUrl"].startswith("data:image/png;base64,")


def test_subagent_input_normalizes_upstream_evidence_into_request_context():
    contract = RoboticsRiskSubagentInput.from_dict(
        {
            "enterpriseName": " 石头科技 ",
            "stockCode": "688169",
            "analysisScope": {"timeRange": "近90天", "focus": "扫地机器人"},
            "upstreamEvidence": [{"title": "行业搜索", "summary": "人形机器人产业链扩张"}],
        }
    )

    request = contract.to_request()

    assert request.enterprise_name == "石头科技"
    assert request.stock_code == "688169"
    assert request.time_range == "近90天"
    assert "上游证据：行业搜索 人形机器人产业链扩张" in request.context


def test_robotics_subagent_missing_enterprise_returns_need_input_without_sources():
    adapter = ShouldNotCallAdapter("gov_policy")

    output = run_robotics_risk_subagent({"enterpriseName": " "}, adapters=[adapter]).to_dict()

    assert output["status"] == "need_input"
    assert "缺少目标企业名称" in output["limitations"][0]
    assert adapter.calls == 0
    assert "runId" not in output


def test_robotics_subagent_valid_input_persists_run_and_handoff_without_rag_rows(db_session):
    now = datetime(2026, 4, 19, 12, 0, 0)

    output = run_robotics_risk_subagent(
        {
            "enterpriseName": "石头科技",
            "stockCode": "688169",
            "analysisScope": {"timeRange": "近30天", "dimensions": ["政策", "公告"]},
            "upstreamEvidence": [{"title": "搜索摘要", "summary": "服务机器人需求增长"}],
        },
        db=db_session,
        adapters=[
            GovPolicyAdapter(documents=[_policy_doc()]),
            CninfoAnnouncementAdapter(documents=[_announcement_doc()]),
        ],
        now_factory=lambda: now,
        id_factory=lambda: "run-subagent-001",
    )
    payload = output.to_dict()

    assert payload["status"] == "done"
    assert payload["runId"] == "run-subagent-001"
    assert payload["documentHandoff"]["runId"] == "run-subagent-001"
    assert payload["sourceDiagnostics"]
    assert payload["documentHandoff"]["sourceDiagnostics"]
    assert payload["normalizedInput"]["upstreamEvidence"][0]["title"] == "搜索摘要"
    row = db_session.query(RoboticsInsightRun).filter_by(run_id="run-subagent-001").one()
    assert row.status == "done"
    assert row.request_json["enterprise"]["name"] == "石头科技"
    assert row.result_json["targetCompany"]["stockCode"] == "688169"
    assert row.result_json["sourceDiagnostics"]
    assert row.handoff_json["documentType"] == "robotics_risk_opportunity_brief"
    stored = RoboticsInsightRunRepository(db_session).get_run_payload("run-subagent-001")
    assert stored["documentHandoff"]["title"] == "石头科技风险与机会洞察简报"
    assert stored["sourceDiagnostics"]
    assert RoboticsInsightRunRepository(db_session).get_run_payload("missing-run") is None
    assert db_session.query(RagDocument).count() == 0
    assert db_session.query(RagChunk).count() == 0
    assert db_session.query(RagIndexJob).count() == 0


def test_robotics_subagent_source_controls_disable_selected_sources():
    policy = CountingAdapter(source_type="gov_policy", documents=[_policy_doc()])
    bidding = CountingAdapter(source_type="bidding_procurement", documents=[_bidding_doc()])

    output = run_robotics_risk_subagent(
        {
            "enterpriseName": "石头科技",
            "sourceControls": {"useBidding": False},
        },
        adapters=[policy, bidding],
        id_factory=lambda: "run-source-control",
    ).to_dict()

    assert output["status"] == "done"
    assert policy.calls == 1
    assert bidding.calls == 0
    assert {item["sourceType"] for item in output["sourceReferences"]} == {"gov_policy"}


def test_robotics_subagent_partial_run_persists_degraded_status(db_session):
    output = run_robotics_risk_subagent(
        {"enterpriseName": "石头科技", "stockCode": "688169"},
        db=db_session,
        adapters=[
            GovPolicyAdapter(documents=[_policy_doc()]),
            FakeFailingAdapter(),
        ],
        now_factory=lambda: datetime(2026, 4, 19, 12, 0, 0),
        id_factory=lambda: "run-partial-001",
    ).to_dict()

    assert output["status"] == "partial"
    assert any("captcha required" in item for item in output["limitations"])
    row = db_session.query(RoboticsInsightRun).filter_by(run_id="run-partial-001").one()
    assert row.status == "partial"
    assert any("captcha required" in item for item in row.result_json["limitations"])


def test_reader_writer_can_render_module_brief_from_reader_packet():
    writer = _FakeReaderWriter(
        """
        {
          "sections": [
            {
              "id": "executive_summary",
              "title": "执行摘要",
              "blocks": [
                {
                  "type": "paragraph",
                  "text": "优先跟踪政策与设备更新主线，同时把监管与标准门槛作为主要约束。"
                }
              ]
            },
            {
              "id": "opportunities",
              "title": "机会信号",
              "blocks": [
                {
                  "type": "tables",
                  "items": [
                    {
                      "tableId": "opportunity_themes",
                      "title": "机会主题",
                      "readerSummary": "优先查看结构化表格中的机会主线排序。"
                    }
                  ]
                }
              ]
            },
            {
              "id": "evidence",
              "title": "证据来源",
              "blocks": [
                {
                  "type": "evidence",
                  "items": [
                    {
                      "referenceId": "reader_evidence_1",
                      "title": "关于推动智能制造和机器人应用场景建设的政策",
                      "readerSummary": "该政策用于支撑行业需求扩张判断。"
                    }
                  ]
                }
              ]
            }
          ]
        }
        """
    )

    result = analyze_robotics_enterprise_risk_opportunity(
        RoboticsInsightRequest(enterprise_name="优必选", stock_code="09880"),
        adapters=[GovPolicyAdapter(documents=[_policy_doc()])],
        reader_writer=writer,
    )

    assert writer.calls
    assert "优先跟踪政策与设备更新主线" in result.brief_markdown
    assert "优先查看结构化表格中的机会主线排序" in result.brief_markdown
    assert "关于推动智能制造和机器人应用场景建设的政策" in result.brief_markdown


def test_reader_writer_rejects_unsupported_table_and_uncited_evidence():
    writer = _FakeReaderWriter(
        """
        {
          "sections": [
            {
              "id": "executive_summary",
              "title": "执行摘要",
              "blocks": [
                {
                  "type": "paragraph",
                  "text": "这是凭空编造的结论。"
                }
              ]
            },
            {
              "id": "opportunities",
              "title": "机会信号",
              "blocks": [
                {
                  "type": "tables",
                  "items": [
                    {
                      "tableId": "invented_table",
                      "title": "不存在的表格",
                      "readerSummary": "这里引用了不存在的结构化表格。"
                    }
                  ]
                }
              ]
            },
            {
              "id": "evidence",
              "title": "证据来源",
              "blocks": [
                {
                  "type": "evidence",
                  "items": [
                    {
                      "title": "不存在的来源",
                      "readerSummary": "没有任何引用标识。"
                    }
                  ]
                }
              ]
            }
          ]
        }
        """
    )

    result = analyze_robotics_enterprise_risk_opportunity(
        RoboticsInsightRequest(enterprise_name="优必选", stock_code="09880"),
        adapters=[GovPolicyAdapter(documents=[_policy_doc()])],
        reader_writer=writer,
    )

    assert writer.calls
    assert "这是凭空编造的结论" not in result.brief_markdown
    assert "不存在的表格" not in result.brief_markdown
    assert "结构化表格" in result.brief_markdown
    assert "机会主题" in result.brief_markdown


def test_robotics_subagent_failure_after_run_creation_is_persisted(db_session):
    class BadResolution:
        supported = False
        stock_code = ""
        profile = None
        limitations: list[str] = []

        def to_metadata(self):
            raise RuntimeError("metadata exploded")

    class BadResolver:
        def resolve_company(self, request):
            return BadResolution()

    output = run_robotics_risk_subagent(
        {"enterpriseName": "石头科技"},
        db=db_session,
        adapters=[GovPolicyAdapter(documents=[_policy_doc()])],
        company_resolver=BadResolver(),
        id_factory=lambda: "run-failed-001",
    ).to_dict()

    assert output["status"] == "failed"
    assert "metadata exploded" in output["errorMessage"]
    row = db_session.query(RoboticsInsightRun).filter_by(run_id="run-failed-001").one()
    assert row.status == "failed"
    assert "metadata exploded" in row.error_message


def test_direct_service_still_does_not_require_run_persistence(db_session):
    result = analyze_robotics_enterprise_risk_opportunity(
        RoboticsInsightRequest(enterprise_name="石头科技", stock_code="688169"),
        adapters=[GovPolicyAdapter(documents=[_policy_doc()])],
    )

    assert result.target_company["name"] == "石头科技"
    assert db_session.query(RoboticsInsightRun).count() == 0


def test_boundary_service_does_not_depend_on_main_agent_or_workspace_chat():
    source = inspect.getsource(robotics_service)

    assert "app.agent" not in source
    assert "workspace" not in source.lower()
    assert "langgraph" not in source.lower()
    assert "flask" not in source.lower()


def test_boundary_subagent_does_not_depend_on_main_agent_or_routes():
    source = inspect.getsource(robotics_subagent)

    assert "app.agent" not in source
    assert "workspace" not in source.lower()
    assert "langgraph" not in source.lower()
    assert "flask" not in source.lower()


def _cache_key(source_type: str, request: RoboticsInsightRequest) -> str:
    return build_cache_key(source_type=source_type, request=request, profile=build_enterprise_profile(request))


def test_cache_hits_are_analyzed_without_calling_external_adapters(db_session):
    now = datetime(2026, 4, 19, 12, 0, 0)
    request = RoboticsInsightRequest(enterprise_name="石头科技", stock_code="688169", time_range="近30天")
    repository = RoboticsEvidenceRepository(db_session)
    for source_type, document in [
        ("gov_policy", _policy_doc()),
        ("cninfo_announcement", _announcement_doc()),
        ("bidding_procurement", _bidding_doc()),
    ]:
        repository.upsert_source_document(
            document,
            cache_key=_cache_key(source_type, request),
            fetched_at=now,
            expires_at=now + timedelta(days=1),
        )

    result = analyze_robotics_enterprise_risk_opportunity(
        request,
        adapters=[
            ShouldNotCallAdapter("gov_policy"),
            ShouldNotCallAdapter("cninfo_announcement"),
            ShouldNotCallAdapter("bidding_procurement"),
        ],
        evidence_cache=RoboticsEvidenceCache(db_session, now_factory=lambda: now),
    )

    payload = result.to_dict()
    assert len(payload["sources"]) == 3
    assert payload["events"]
    assert payload["opportunities"]


def test_live_ceb_bidding_cache_persists_metadata_reuses_and_avoids_rag_rows(db_session):
    now = datetime(2026, 4, 19, 12, 0, 0)
    detail_url = "https://custominfo.cebpubservice.com/bulletin/notice-cache.html"
    search_html = f'<a href="{detail_url}">广东公共场所清洁机器人采购项目中标结果公告</a><span>2026-04-10</span>'
    detail_html = """
    <h1>广东公共场所清洁机器人采购项目中标结果公告</h1>
    <div id="content">
      项目名称：广东公共场所清洁机器人采购项目
      项目编号：GD-RB-CACHE
      采购人：广州市城市管理局
      中标人：石头科技
      中标金额：320万元
      本项目采购清洁机器人和服务机器人。
    </div>
    <a href="/files/result.pdf">附件.pdf</a>
    """
    client = FakeCebBiddingClient(search_html=search_html, detail_pages={detail_url: detail_html})
    request = RoboticsInsightRequest(enterprise_name="石头科技", time_range="近30天", context="扫地机器人")
    cache = RoboticsEvidenceCache(db_session, now_factory=lambda: now)

    first = analyze_robotics_enterprise_risk_opportunity(
        request,
        adapters=[BiddingProcurementAdapter(client=client, max_queries=1, detail_fetch_limit=1)],
        evidence_cache=cache,
    )
    second = analyze_robotics_enterprise_risk_opportunity(
        request,
        adapters=[ShouldNotCallAdapter("bidding_procurement")],
        evidence_cache=cache,
    )

    row = db_session.query(RoboticsBiddingDocument).one()
    assert first.sources
    assert second.sources
    assert row.notice_type == "中标结果公告"
    assert row.project_name == "广东公共场所清洁机器人采购项目"
    assert row.project_code == "GD-RB-CACHE"
    assert row.buyer_name == "广州市城市管理局"
    assert row.winning_bidder == "石头科技"
    assert row.amount == "320万元"
    assert row.region == "广东"
    assert row.matched_enterprise_name == "石头科技"
    assert row.metadata_json["sourceChannel"] == "cebpubservice"
    assert row.metadata_json["directMatchRole"] == "winner"
    assert row.metadata_json["attachments"][0]["fileType"] == "pdf"
    assert any(source.relevance_scope == "enterprise" for source in second.sources)
    assert db_session.query(RagDocument).count() == 0
    assert db_session.query(RagChunk).count() == 0
    assert db_session.query(RagIndexJob).count() == 0


def test_bidding_negative_cache_reuses_empty_source_result(db_session):
    now = datetime(2026, 4, 19, 12, 0, 0)
    request = RoboticsInsightRequest(enterprise_name="石头科技", time_range="近30天", context="扫地机器人")
    cache = RoboticsEvidenceCache(
        db_session,
        now_factory=lambda: now,
        policies={"bidding_procurement": SourceFreshnessPolicy(timedelta(days=3), timedelta(hours=1))},
    )

    first = analyze_robotics_enterprise_risk_opportunity(
        request,
        adapters=[BiddingProcurementAdapter(client=FakeCebBiddingClient(search_html="<html><body>暂无数据</body></html>"), max_queries=1)],
        evidence_cache=cache,
    )
    second = analyze_robotics_enterprise_risk_opportunity(
        request,
        adapters=[ShouldNotCallAdapter("bidding_procurement")],
        evidence_cache=cache,
    )

    assert any("未返回" in item for item in first.limitations)
    assert any("未返回" in item for item in second.limitations)
    assert first.source_diagnostics[0].cache_decision == "live_fetch"
    assert second.source_diagnostics[0].cache_decision == "negative_hit"


def test_strategy_version_change_ignores_obsolete_negative_cache(db_session):
    now = datetime(2026, 4, 19, 12, 0, 0)
    request = RoboticsInsightRequest(enterprise_name="石头科技", time_range="近30天")
    repository = RoboticsEvidenceRepository(db_session)
    repository.record_source_state(
        source_type="gov_policy",
        cache_key="legacy-stock-only-empty-cache-key",
        status="empty",
        message="旧策略空结果",
        fetched_at=now,
        expires_at=now + timedelta(hours=1),
    )
    adapter = CountingAdapter(source_type="gov_policy", documents=[_policy_doc()])

    result = analyze_robotics_enterprise_risk_opportunity(
        request,
        adapters=[adapter],
        evidence_cache=RoboticsEvidenceCache(db_session, now_factory=lambda: now),
    )

    assert adapter.calls == 1
    assert result.sources
    assert result.source_diagnostics[0].cache_decision == "live_fetch"


def test_cache_miss_calls_adapter_and_persists_returned_evidence(db_session):
    now = datetime(2026, 4, 19, 12, 0, 0)
    request = RoboticsInsightRequest(enterprise_name="石头科技", time_range="近30天")
    adapter = CountingAdapter(source_type="gov_policy", documents=[_policy_doc()])

    result = analyze_robotics_enterprise_risk_opportunity(
        request,
        adapters=[adapter],
        evidence_cache=RoboticsEvidenceCache(db_session, now_factory=lambda: now),
    )

    assert adapter.calls == 1
    assert result.sources
    assert db_session.query(RoboticsPolicyDocument).count() == 1


def test_live_gov_policy_cache_persists_metadata_and_reuses_without_rag_rows(db_session):
    now = datetime(2026, 4, 19, 12, 0, 0)
    policy_url = "https://www.gov.cn/zhengce/zhengceku/gwywj/2026-04/01/content_123456.htm"
    search_html = f'<a href="{policy_url}">国务院办公厅关于推动服务机器人应用场景开放的意见</a><span>2026-04-01</span>'
    detail_html = """
    <h1>国务院办公厅关于推动服务机器人应用场景开放的意见</h1>
    <div>发文机关：国务院办公厅 文号：国办发〔2026〕2号</div>
    <div class="pages_content">政策鼓励服务机器人、清洁机器人在养老和公共服务场景应用，推动设备更新。</div>
    <a href="/zhengce/file/task.pdf">附件.pdf</a>
    """
    client = FakeGovPolicyClient(search_html=search_html, detail_pages={policy_url: detail_html})
    request = RoboticsInsightRequest(enterprise_name="石头科技", time_range="近30天", context="扫地机器人")
    cache = RoboticsEvidenceCache(db_session, now_factory=lambda: now)

    first = analyze_robotics_enterprise_risk_opportunity(
        request,
        adapters=[GovPolicyAdapter(client=client, max_queries=1, detail_fetch_limit=1)],
        evidence_cache=cache,
    )
    second = analyze_robotics_enterprise_risk_opportunity(
        request,
        adapters=[ShouldNotCallAdapter("gov_policy")],
        evidence_cache=cache,
    )

    row = db_session.query(RoboticsPolicyDocument).one()
    assert first.sources
    assert second.sources
    assert row.policy_id
    assert row.issuing_agency == "国务院办公厅"
    assert row.document_number == "国办发〔2026〕2号"
    assert row.metadata_json["sourceScope"] == "state_council"
    assert row.metadata_json["searchKeyword"]
    assert row.metadata_json["attachments"][0]["fileType"] == "pdf"
    assert any(source.metadata.get("attachmentFullTextParsed") is False for source in second.sources)
    assert db_session.query(RagDocument).count() == 0
    assert db_session.query(RagChunk).count() == 0
    assert db_session.query(RagIndexJob).count() == 0


def test_metadata_only_gov_policy_is_attributed_and_limited():
    policy_url = "https://www.gov.cn/zhengce/zhengceku/gwywj/2026-04/01/content_meta.htm"
    search_html = f'<a href="{policy_url}">国务院办公厅关于机器人标准化工作的意见</a><span>2026-04-01</span>'
    detail_html = "<h1>国务院办公厅关于机器人标准化工作的意见</h1>"
    client = FakeGovPolicyClient(search_html=search_html, detail_pages={policy_url: detail_html})

    result = analyze_robotics_enterprise_risk_opportunity(
        RoboticsInsightRequest(enterprise_name="埃斯顿", context="工业机器人"),
        adapters=[GovPolicyAdapter(client=client, max_queries=1, detail_fetch_limit=1)],
    )

    assert result.sources
    assert result.sources[0].metadata["status"] == "metadata_limited"
    assert any("政策正文提取受限" in item for item in result.limitations)


def test_policy_and_cninfo_evidence_reinforce_same_dimension_signal():
    policy = SourceDocument(
        id="policy-reinforce",
        source_type="gov_policy",
        source_name="国务院政策文件库",
        title="关于扩大机器人政府采购和应用场景开放的意见",
        content="政策鼓励服务机器人政府采购，推动清洁机器人应用场景开放。",
        published_at="2026-04-01",
        authority_score=0.95,
        relevance_scope="industry",
        metadata={"matchedSegments": ["扫地机器人"], "sourceScope": "state_council"},
    )
    announcement = SourceDocument(
        id="ann-reinforce",
        source_type="cninfo_announcement",
        source_name="巨潮资讯网",
        title="石头科技关于重大合同和中标订单的公告",
        content="公司签订重大合同并获得服务机器人订单。",
        published_at="2026-04-02",
        authority_score=0.95,
        relevance_scope="enterprise",
    )

    result = analyze_robotics_enterprise_risk_opportunity(
        RoboticsInsightRequest(enterprise_name="石头科技", context="扫地机器人"),
        adapters=[
            GovPolicyAdapter(documents=[policy]),
            CninfoAnnouncementAdapter(documents=[announcement]),
        ],
    )

    order_signal = next(item for item in result.opportunities if item.category == "订单")
    assert set(order_signal.source_ids) == {"policy-reinforce", "ann-reinforce"}
    assert order_signal.confidence > 0.9
    assert "共同支持" in order_signal.reasoning


def test_bidding_direct_award_market_demand_and_competitor_pressure_reasoning():
    direct_award = SourceDocument(
        id="bid-direct",
        source_type="bidding_procurement",
        source_name="中国招标投标公共服务平台",
        title="清洁机器人采购项目中标结果公告",
        content="项目采购清洁机器人，中标人：石头科技，中标金额：300万元。",
        published_at="2026-04-12",
        authority_score=0.9,
        relevance_scope="enterprise",
        metadata={
            "noticeType": "中标结果公告",
            "projectName": "清洁机器人采购项目",
            "winningBidder": "石头科技",
            "amount": "300万元",
            "directMatchRole": "winner",
            "matchedEnterpriseName": "石头科技",
        },
    )
    market_demand = SourceDocument(
        id="bid-market",
        source_type="bidding_procurement",
        source_name="中国招标投标公共服务平台",
        title="医院服务机器人采购公告",
        content="医院采购服务机器人和配送机器人，用于医疗场景。",
        published_at="2026-04-11",
        authority_score=0.82,
        relevance_scope="market_demand",
        metadata={"noticeType": "招标公告", "inferenceLevel": "market_demand"},
    )
    competitor_award = SourceDocument(
        id="bid-competitor",
        source_type="bidding_procurement",
        source_name="中国招标投标公共服务平台",
        title="物流机器人采购项目中标候选人公示",
        content="本项目采购物流机器人，第一中标候选人：竞争机器人公司。",
        published_at="2026-04-10",
        authority_score=0.82,
        relevance_scope="market_demand",
        metadata={
            "noticeType": "中标候选人公示",
            "winningBidder": "竞争机器人公司",
            "directMatchRole": "competitor",
        },
    )

    result = analyze_robotics_enterprise_risk_opportunity(
        RoboticsInsightRequest(enterprise_name="石头科技", context="扫地机器人"),
        adapters=[BiddingProcurementAdapter(documents=[direct_award, market_demand, competitor_award])],
    )

    assert any(event.event_type == "direct_enterprise_award" for event in result.events)
    assert any(event.event_type == "competitor_award_pressure" for event in result.events)
    assert any(signal.category == "订单机会" and "中标/成交" in signal.reasoning for signal in result.opportunities)
    assert any(signal.category == "竞争压力" for signal in result.risks)


def test_bidding_market_demand_confidence_increases_with_policy_reinforcement():
    policy = SourceDocument(
        id="policy-bid-reinforce",
        source_type="gov_policy",
        source_name="国务院政策文件库",
        title="关于扩大机器人政府采购和应用场景开放的意见",
        content="政策鼓励服务机器人政府采购，推动医疗场景开放。",
        published_at="2026-04-01",
        authority_score=0.95,
        relevance_scope="industry",
        metadata={"matchedSegments": ["服务机器人"]},
    )
    bidding = SourceDocument(
        id="bid-reinforce",
        source_type="bidding_procurement",
        source_name="中国招标投标公共服务平台",
        title="医院服务机器人采购公告",
        content="医院采购服务机器人和配送机器人，用于医疗场景。",
        published_at="2026-04-11",
        authority_score=0.82,
        relevance_scope="market_demand",
        metadata={"noticeType": "招标公告", "matchedSegments": ["服务机器人"]},
    )

    result = analyze_robotics_enterprise_risk_opportunity(
        RoboticsInsightRequest(enterprise_name="未映射机器人公司", context="服务机器人 医疗"),
        adapters=[
            GovPolicyAdapter(documents=[policy]),
            BiddingProcurementAdapter(documents=[bidding]),
        ],
    )

    demand_signal = next(item for item in result.opportunities if item.category in {"市场需求", "订单"})
    assert set(demand_signal.source_ids) & {"policy-bid-reinforce", "bid-reinforce"}
    assert demand_signal.confidence >= 0.75
    assert "验证" in demand_signal.reasoning


def test_stale_partial_cache_refreshes_only_affected_source(db_session):
    now = datetime(2026, 4, 19, 12, 0, 0)
    request = RoboticsInsightRequest(enterprise_name="石头科技", stock_code="688169", time_range="近30天")
    repository = RoboticsEvidenceRepository(db_session)
    repository.upsert_source_document(
        _policy_doc(),
        cache_key=_cache_key("gov_policy", request),
        fetched_at=now,
        expires_at=now + timedelta(days=1),
    )
    repository.upsert_source_document(
        _announcement_doc(),
        cache_key=_cache_key("cninfo_announcement", request),
        fetched_at=now - timedelta(days=10),
        expires_at=now - timedelta(days=1),
    )
    cninfo_adapter = CountingAdapter(source_type="cninfo_announcement", documents=[_announcement_doc()])

    result = analyze_robotics_enterprise_risk_opportunity(
        request,
        adapters=[
            ShouldNotCallAdapter("gov_policy"),
            cninfo_adapter,
        ],
        evidence_cache=RoboticsEvidenceCache(db_session, now_factory=lambda: now),
    )

    assert cninfo_adapter.calls == 1
    assert any("缓存已过期" in item for item in result.limitations)
    assert len(result.sources) == 2


def test_cninfo_pdf_parse_success_and_failure_are_persisted(db_session):
    repository = RoboticsEvidenceRepository(db_session)

    repository.persist_cninfo_pdf_result(
        announcement_id="ann-ok",
        title="石头科技年度报告",
        pdf_url="https://static.cninfo.com.cn/ann-ok.pdf",
        result=PdfTextExtractionResult(
            text="公司研发投入增长并发布新产品。",
            page_count=12,
            extraction_method="native",
            parse_status="parsed",
        ),
    )
    repository.persist_cninfo_pdf_result(
        announcement_id="ann-fail",
        title="石头科技扫描公告",
        pdf_url="https://static.cninfo.com.cn/ann-fail.pdf",
        result=PdfTextExtractionResult(parse_status="failed", parse_error="PDF produced no usable text"),
    )

    ok = db_session.query(RoboticsCninfoAnnouncement).filter_by(announcement_id="ann-ok").one()
    failed = db_session.query(RoboticsCninfoAnnouncement).filter_by(announcement_id="ann-fail").one()
    assert ok.parse_status == "parsed"
    assert ok.content_text == "公司研发投入增长并发布新产品。"
    assert ok.page_count == 12
    assert failed.status == "failed"
    assert failed.parse_error == "PDF produced no usable text"


def test_robotics_pdf_text_extraction_does_not_write_rag_rows(db_session, tmp_path: Path, monkeypatch):
    class FakeLoaded:
        extraction_method = "native"
        ocr_used = False
        ocr_provider = None
        blocks = [type("Block", (), {"text": "公司签订重大合同。", "metadata": {"page": 1}})()]

    class FakePdfLoader:
        def __init__(self, **kwargs):
            pass

        def load(self, *, path: Path, source_name: str):
            return FakeLoaded()

    monkeypatch.setattr("app.rag.fileloaders.pdf_loader.PdfFileLoader", FakePdfLoader)
    sample = tmp_path / "sample.pdf"
    sample.write_bytes(b"%PDF-1.4")

    result = extract_pdf_text(sample, source_name="sample.pdf")
    RoboticsEvidenceRepository(db_session).persist_cninfo_pdf_result(
        announcement_id="ann-rag-boundary",
        title="石头科技重大合同公告",
        pdf_url="https://static.cninfo.com.cn/ann-rag-boundary.pdf",
        result=result,
    )

    assert result.succeeded
    assert db_session.query(RagDocument).count() == 0
    assert db_session.query(RagChunk).count() == 0
    assert db_session.query(RagIndexJob).count() == 0


def test_source_failure_negative_cache_degrades_independently(db_session):
    now = datetime(2026, 4, 19, 12, 0, 0)
    request = RoboticsInsightRequest(enterprise_name="石头科技", time_range="近30天")
    cache = RoboticsEvidenceCache(
        db_session,
        now_factory=lambda: now,
        policies={"gov_policy": SourceFreshnessPolicy(timedelta(days=30), timedelta(hours=2))},
    )

    first = analyze_robotics_enterprise_risk_opportunity(
        request,
        adapters=[CountingAdapter(source_type="gov_policy", fail="network blocked")],
        evidence_cache=cache,
    )
    second = analyze_robotics_enterprise_risk_opportunity(
        request,
        adapters=[ShouldNotCallAdapter("gov_policy")],
        evidence_cache=cache,
    )

    assert any("network blocked" in item for item in first.limitations)
    assert any("network blocked" in item for item in second.limitations)


def test_listed_company_profile_seed_is_idempotent_and_queryable(db_session):
    repository = RoboticsEvidenceRepository(db_session)

    first_count = seed_robotics_listed_company_profiles(repository)
    second_count = seed_robotics_listed_company_profiles(repository)

    assert first_count == second_count
    assert db_session.query(RoboticsListedCompanyProfile).filter_by(stock_code="688169").count() == 1
    profile = repository.get_listed_company_profile_by_stock_code("688169")
    assert profile is not None
    assert profile.security_name == "石头科技"
    assert profile.is_supported == 1


@pytest.mark.parametrize(
    ("enterprise", "stock_code", "expected_code", "expected_match"),
    [
        ("", "688169", "688169", "stock_code"),
        ("北京石头世纪科技股份有限公司", "", "688169", "company_name"),
        ("石头科技", "", "688169", "security_name"),
        ("Roborock", "", "688169", "alias"),
        ("石头世纪科技", "", "688169", "fuzzy"),
    ],
)
def test_listed_company_resolver_matches_stock_name_alias_and_fuzzy(
    db_session,
    enterprise,
    stock_code,
    expected_code,
    expected_match,
):
    repository = RoboticsEvidenceRepository(db_session)
    seed_robotics_listed_company_profiles(repository)

    result = ListedCompanyResolver(repository).resolve(enterprise, stock_code=stock_code)

    assert result.resolved
    assert result.stock_code == expected_code
    assert result.match_type == expected_match
    assert result.supported


def test_listed_company_resolver_reports_ambiguous_unresolved_and_unsupported(db_session):
    repository = RoboticsEvidenceRepository(db_session)
    seed_robotics_listed_company_profiles(repository)
    repository.upsert_listed_company_profile(
        {
            "stock_code": "111111",
            "security_name": "机器人一号",
            "company_name": "机器人一号股份有限公司",
            "aliases": ["机器人"],
            "is_supported": True,
        }
    )
    repository.upsert_listed_company_profile(
        {
            "stock_code": "222222",
            "security_name": "机器人二号",
            "company_name": "机器人二号股份有限公司",
            "aliases": ["机器人"],
            "is_supported": True,
        }
    )
    resolver = ListedCompanyResolver(repository)

    ambiguous = resolver.resolve("机器人")
    unresolved = resolver.resolve("不存在机器人公司")
    unsupported = resolver.resolve("优必选")

    assert ambiguous.match_type == "ambiguous"
    assert ambiguous.limitations
    assert not unresolved.resolved
    assert "未在本地" in unresolved.limitations[0]
    assert unsupported.resolved
    assert not unsupported.supported
    assert "港股" in unsupported.limitations[0]


def test_cninfo_adapter_builds_stock_query_and_normalizes_metadata():
    record = CninfoAnnouncementRecord(
        announcement_id="ann-001",
        title="石头科技关于重大合同和新产品研发的公告",
        announcement_time="2026-04-18",
        sec_code="688169",
        sec_name="石头科技",
        adjunct_url="new/disclosure/detail?x=1",
        pdf_url="https://static.cninfo.com.cn/ann-001.pdf",
    )
    client = FakeCninfoClient(records=[record])
    adapter = CninfoAnnouncementAdapter(client=client, pdf_parse_limit=0)

    result = adapter.collect(
        request=RoboticsInsightRequest(enterprise_name="石头科技", stock_code="688169"),
        profile=EnterpriseProfile(name="石头科技", stock_code="688169", keywords=["机器人"]),
    )

    assert client.plans[0].query_type == "stock_code"
    assert client.plans[0].stock_code == "688169"
    assert len(result.documents) == 1
    document = result.documents[0]
    assert document.metadata["announcementId"] == "ann-001"
    assert document.metadata["secCode"] == "688169"
    assert document.authority_score == 0.95
    assert result.diagnostics[0].status == "done"


def test_cninfo_adapter_uses_name_fallback_and_reports_empty_result():
    client = FakeCninfoClient(records=[])
    adapter = CninfoAnnouncementAdapter(client=client)

    result = adapter.collect(
        request=RoboticsInsightRequest(enterprise_name="未映射机器人公司"),
        profile=EnterpriseProfile(name="未映射机器人公司", keywords=["机器人"]),
    )

    assert client.plans[0].query_type == "name"
    assert any("企业名称搜索" in item for item in result.limitations)
    assert any("未返回" in item for item in result.limitations)
    assert result.diagnostics[0].status == "empty"


def test_cninfo_stock_only_empty_falls_back_to_name_search_and_cleans_markup():
    record = CninfoAnnouncementRecord(
        announcement_id="ann-green",
        title="<em>绿的谐波</em>关于获得客户订单的公告",
        announcement_time="2026-04-18",
        sec_code="688017",
        sec_name="<em>绿的谐波</em>",
        pdf_url="https://static.cninfo.com.cn/ann-green.pdf",
    )
    client = PlanAwareCninfoClient(
        {
            "stock_code": [],
            "name_fallback:绿的谐波": [record],
        }
    )
    adapter = CninfoAnnouncementAdapter(client=client, pdf_parse_limit=0)

    result = adapter.collect(
        request=RoboticsInsightRequest(enterprise_name="绿的谐波", stock_code="688017"),
        profile=EnterpriseProfile(
            name="绿的谐波",
            stock_code="688017",
            metadata={"securityName": "绿的谐波", "companyName": "苏州绿的谐波传动科技股份有限公司"},
        ),
    )

    assert [plan.query_type for plan in client.plans[:2]] == ["stock_code", "name_fallback"]
    assert result.documents
    assert result.documents[0].title == "绿的谐波关于获得客户订单的公告"
    assert result.documents[0].metadata["secName"] == "绿的谐波"
    assert "stock_only" in result.diagnostics[0].query_strategy
    assert "name_fallback" in result.diagnostics[0].query_strategy


def test_cninfo_adapter_downloads_selected_pdf_and_persists_parse_status(db_session, monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"%PDF-1.4"

    def fake_urlopen(*_args, **_kwargs):
        return FakeResponse()

    monkeypatch.setattr("app.robotics_risk.adapters.cninfo.urlopen", fake_urlopen)
    record = CninfoAnnouncementRecord(
        announcement_id="ann-pdf",
        title="石头科技关于重大合同的公告",
        announcement_time="2026-04-18",
        sec_code="688169",
        sec_name="石头科技",
        pdf_url="https://static.cninfo.com.cn/ann-pdf.pdf",
    )
    adapter = CninfoAnnouncementAdapter(
        client=FakeCninfoClient(records=[record]),
        pdf_text_extractor=lambda _path: PdfTextExtractionResult(
            text="公司签订重大合同并发布新产品。",
            page_count=3,
            extraction_method="native",
            parse_status="parsed",
        ),
        pdf_parse_limit=1,
    )
    cache = RoboticsEvidenceCache(db_session, now_factory=lambda: datetime(2026, 4, 19, 12, 0, 0))

    result = analyze_robotics_enterprise_risk_opportunity(
        RoboticsInsightRequest(enterprise_name="石头科技", time_range="近30天"),
        adapters=[adapter],
        evidence_cache=cache,
    )

    row = db_session.query(RoboticsCninfoAnnouncement).filter_by(announcement_id="ann-pdf").one()
    assert row.sec_code == "688169"
    assert row.parse_status == "parsed"
    assert row.content_text == "公司签订重大合同并发布新产品。"
    assert result.events


def test_standalone_workflow_uses_resolved_stock_code_for_cninfo(db_session):
    record = CninfoAnnouncementRecord(
        announcement_id="ann-resolved",
        title="石头科技关于研发投入增长的公告",
        announcement_time="2026-04-18",
        sec_code="688169",
        sec_name="石头科技",
        pdf_url="https://static.cninfo.com.cn/ann-resolved.pdf",
    )
    client = FakeCninfoClient(records=[record])

    result = analyze_robotics_enterprise_risk_opportunity(
        RoboticsInsightRequest(enterprise_name="石头科技", time_range="近30天"),
        adapters=[CninfoAnnouncementAdapter(client=client, pdf_parse_limit=0)],
        evidence_cache=RoboticsEvidenceCache(db_session, now_factory=lambda: datetime(2026, 4, 19, 12, 0, 0)),
    )

    assert client.plans[0].stock_code == "688169"
    assert result.target_company["stockCode"] == "688169"
    assert result.target_company["matchType"] in {"security_name", "alias", "company_name", "fuzzy"}
    assert any(source.metadata.get("queryType") == "stock_code" for source in result.sources)


def test_cninfo_parse_failure_is_cached_without_rag_rows(db_session, monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"%PDF-1.4"

    monkeypatch.setattr("app.robotics_risk.adapters.cninfo.urlopen", lambda *_args, **_kwargs: FakeResponse())
    record = CninfoAnnouncementRecord(
        announcement_id="ann-parse-fail",
        title="石头科技扫描公告",
        announcement_time="2026-04-18",
        sec_code="688169",
        sec_name="石头科技",
        pdf_url="https://static.cninfo.com.cn/ann-parse-fail.pdf",
    )
    adapter = CninfoAnnouncementAdapter(
        client=FakeCninfoClient(records=[record]),
        pdf_text_extractor=lambda _path: PdfTextExtractionResult(parse_status="failed", parse_error="no text"),
        pdf_parse_limit=1,
    )

    analyze_robotics_enterprise_risk_opportunity(
        RoboticsInsightRequest(enterprise_name="石头科技", time_range="近30天"),
        adapters=[adapter],
        evidence_cache=RoboticsEvidenceCache(db_session, now_factory=lambda: datetime(2026, 4, 19, 12, 0, 0)),
    )

    row = db_session.query(RoboticsCninfoAnnouncement).filter_by(announcement_id="ann-parse-fail").one()
    assert row.parse_status == "failed"
    assert row.parse_error == "no text"
    assert db_session.query(RagDocument).count() == 0
    assert db_session.query(RagChunk).count() == 0
    assert db_session.query(RagIndexJob).count() == 0
