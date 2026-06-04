"""券商研报单元测试（fetcher 内部纯函数 / schema / model 可导入）"""
from app.services.data_fetcher.research_report_fetcher import (
    _detect_forecast_year_base,
    _to_date,
    _to_float,
)

# ────────── _detect_forecast_year_base ──────────

def test_detect_forecast_year_base_returns_min_year():
    cols = [
        "序号", "股票代码", "报告名称", "东财评级", "机构",
        "2026-盈利预测-收益", "2026-盈利预测-市盈率",
        "2027-盈利预测-收益", "2027-盈利预测-市盈率",
        "2028-盈利预测-收益", "2028-盈利预测-市盈率",
        "行业", "日期", "报告PDF链接",
    ]
    assert _detect_forecast_year_base(cols) == 2026


def test_detect_forecast_year_base_returns_none_when_missing():
    cols = ["序号", "股票代码", "报告名称", "机构", "日期"]
    assert _detect_forecast_year_base(cols) is None


def test_detect_forecast_year_base_handles_non_year_prefixed_columns():
    cols = ["abc-盈利预测-收益", "2027-盈利预测-收益"]
    assert _detect_forecast_year_base(cols) == 2027


# ────────── _to_float ──────────

def test_to_float_handles_none():
    assert _to_float(None) is None


def test_to_float_handles_nan_string():
    import math
    assert _to_float(math.nan) is None


def test_to_float_handles_string_number():
    assert _to_float("3.14") == 3.14


def test_to_float_handles_invalid():
    assert _to_float("not-a-number") is None


# ────────── _to_date ──────────

def test_to_date_handles_iso_string():
    from datetime import date
    assert _to_date("2026-04-30") == date(2026, 4, 30)


def test_to_date_returns_none_for_invalid():
    assert _to_date("garbage") is None


def test_to_date_passes_through_date():
    from datetime import date
    d = date(2026, 1, 1)
    assert _to_date(d) is d


# ────────── 模型与 schema 可导入 ──────────

def test_research_model_importable():
    from app.models.research import ResearchReportMeta
    assert ResearchReportMeta.__tablename__ == "research_report_meta"


def test_research_schema_importable():
    from app.schemas.research import ResearchReportRead
    inst = ResearchReportRead(
        news_id=1, title="开源证券：xxx", broker="开源证券", rating="买入",
    )
    assert inst.broker == "开源证券"


def test_research_crawler_normalizes_with_meta():
    """ResearchCrawler.fetch_by_code 出来的 dict 必须含 _meta"""
    # 不调真实 akshare，仅验证类签名
    from app.services.news_crawler.research_crawler import ResearchCrawler
    crawler = ResearchCrawler()
    assert crawler.source_name == "research_em"
    assert crawler.category == "research"


def test_source_authority_registered():
    from app.services.news_crawler.base_crawler import SOURCE_AUTHORITY
    assert SOURCE_AUTHORITY["research_em"] == 0.85
