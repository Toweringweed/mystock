"""P1 指标补全单元测试（资金 / 日历 / 减持 / 行业景气）"""
from datetime import date

from app.services.event_detector import insider_events
from app.services.notifier.event_templates import format_event


# ────────── insider severity 分级 ──────────

def test_insider_severity_high_for_large_reduce():
    assert insider_events._classify_severity("reduce", 5.5) == "high"
    assert insider_events._classify_severity("reduce", 5.0) == "high"


def test_insider_severity_medium_for_small_reduce():
    assert insider_events._classify_severity("reduce", 1.5) == "medium"
    assert insider_events._classify_severity("reduce", 1.0) == "medium"


def test_insider_severity_low_for_tiny_reduce():
    assert insider_events._classify_severity("reduce", 0.5) == "low"


def test_insider_severity_for_increase():
    assert insider_events._classify_severity("increase", 1.5) == "medium"
    assert insider_events._classify_severity("increase", 0.5) == "low"


def test_insider_severity_with_none():
    assert insider_events._classify_severity("reduce", None) == "low"


# ────────── event_templates: 新增 INSIDER_TRADE / CALENDAR ──────────

def test_format_insider_trade_template():
    md = format_event(
        event_type="INSIDER_TRADE",
        severity="high",
        title="XX 减持 6%",
        payload={
            "trade_type": "reduce",
            "holder_name": "张三",
            "pct_of_total": 6.0,
            "shares": 1234567,
            "price_low": 10.0,
            "price_high": 12.0,
        },
    )
    assert "减持" in md
    assert "张三" in md
    assert "6.00%" in md


def test_format_calendar_reminder_template():
    md = format_event(
        event_type="CALENDAR_REMINDER",
        severity="medium",
        title="[T-7天] 财报披露：贵州茅台",
        payload={
            "calendar_event_type": "earnings_release",
            "event_date": "2026-05-08",
            "lead_days": 7,
        },
    )
    assert "T-7" in md or "T-7天" in md
    assert "earnings_release" in md
    assert "2026-05-08" in md


# ────────── insider_extractor parser ──────────

def test_insider_extractor_parse_extracts_results():
    from app.services.ai_analyzer.insider_extractor import _parse
    raw = '''Some text {"results": [
        {"idx": 100, "is_insider": true, "trade_type": "reduce",
         "holder_name": "张三", "shares": 1000000, "pct_of_total": 1.5,
         "price_low": 10.0, "price_high": 11.0}
    ]} extra'''
    out = _parse(raw)
    assert len(out) == 1
    assert out[0]["trade_type"] == "reduce"
    assert out[0]["pct_of_total"] == 1.5


def test_insider_extractor_parse_empty():
    from app.services.ai_analyzer.insider_extractor import _parse
    assert _parse("") == []
    assert _parse("not json") == []


# ────────── industry_report_fetcher CIK map ──────────

def test_industry_cik_map_complete():
    from app.services.data_fetcher.industry_report_fetcher import CIK_MAP
    for ticker in ["NVDA", "GOOGL", "META", "MSFT", "AMZN"]:
        assert ticker in CIK_MAP, f"{ticker} missing"
        assert len(CIK_MAP[ticker]) == 10  # 0-padded 10 digits
        assert CIK_MAP[ticker].isdigit()


# ────────── calendar detector LEAD_TIMES ──────────

def test_calendar_lead_times_config():
    from app.services.event_detector.calendar_events import LEAD_TIMES
    assert (7, "medium") in LEAD_TIMES
    assert (1, "high") in LEAD_TIMES


# ────────── 模型字段存在性 ──────────

def test_model_fields_present():
    from app.models.kline import StockDailyKline
    from app.models.fundamental import StockFundamental
    assert "volume_ratio" in StockDailyKline.__table__.c
    assert "ps" in StockFundamental.__table__.c


def test_new_models_importable():
    from app.models import (
        StockCapitalFlow, StockLhb, InsiderTrade,
        CalendarEvent, IndustryMetric,
    )
    assert StockCapitalFlow.__tablename__ == "stock_capital_flows"
    assert StockLhb.__tablename__ == "stock_lhb"
    assert InsiderTrade.__tablename__ == "insider_trades"
    assert CalendarEvent.__tablename__ == "calendar_events"
    assert IndustryMetric.__tablename__ == "industry_metrics"
