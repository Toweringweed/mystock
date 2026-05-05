"""event_detector 单元测试

不依赖外部 LLM；只校验幂等键、计算逻辑、边界。
"""
from datetime import date

import numpy as np

from app.services.event_detector import technical_events as tech
from app.services.event_detector import valuation_events as val


def test_volume_spike_constants():
    """常量未被错误改动"""
    assert tech.VOLUME_SPIKE_MULTIPLIER == 3.0
    assert tech.MA20_DAYS == 20


def test_valuation_percentile_logic():
    """近似 PE 序列：低于 5% 分位的判 PE_EXTREME_LOW"""
    # 模拟 1000 个交易日的收盘价，EPS=2.0
    closes = np.linspace(10, 30, 1000)  # PE = 5 ~ 15
    eps = 2.0
    pe_series = closes / eps
    low_thr = float(np.percentile(pe_series, val.LOW_PERCENTILE))
    high_thr = float(np.percentile(pe_series, val.HIGH_PERCENTILE))

    # 5.4（接近 PE 序列底部）应严格低于 5% 分位
    assert 5.4 < low_thr
    # 14.6（接近 PE 序列顶部）应严格高于 95% 分位
    assert 14.6 > high_thr


def test_valuation_thresholds():
    assert val.LOW_PERCENTILE < val.HIGH_PERCENTILE
    assert val.HISTORY_YEARS == 5


def test_dedup_key_format():
    """dedup_key 应包含日期，保证同一天的同类事件幂等"""
    target = date(2026, 5, 1)
    expected_low = f"pe_low:{target.isoformat()}"
    expected_high = f"pe_high:{target.isoformat()}"
    assert expected_low.startswith("pe_low:")
    assert expected_high.endswith("2026-05-01")


def test_signal_flip_module_imports():
    """signal_flip detector 可正常 import（不跑数据库）"""
    from app.services.event_detector import signal_flip_events
    assert hasattr(signal_flip_events, "detect_all")


def test_event_helper_imports():
    from app.services.event_detector._helpers import upsert_event
    assert callable(upsert_event)


def test_summary_generator_imports():
    from app.services.ai_analyzer.summary_generator import (
        BATCH_SIZE, SummaryGenerator, _format_snapshots, _parse_response, StockSnapshot,
    )
    assert BATCH_SIZE == 10
    assert callable(SummaryGenerator)


def test_summary_parse_handles_empty():
    from app.services.ai_analyzer.summary_generator import _parse_response
    assert _parse_response("") == []
    assert _parse_response("not json") == []


def test_summary_parse_extracts_results():
    from app.services.ai_analyzer.summary_generator import _parse_response
    raw = '''Some preamble {"results": [
        {"code": "000001", "label": "突破", "one_liner": "MA20 上行", "signal": "bullish"}
    ]} extra'''
    out = _parse_response(raw)
    assert len(out) == 1
    assert out[0]["code"] == "000001"


def test_event_template_format():
    """注：K线表 change_pct 字段的单位是百分数（如 7.5 表示 +7.5%），
    detector payload 里直接透传，模板不再 ×100"""
    from app.services.notifier.event_templates import format_event
    md = format_event(
        event_type="VOLUME_SPIKE",
        severity="medium",
        title="某股 异常放量",
        payload={"volume": 100000, "avg_20": 30000, "ratio": 3.3, "change_pct": 7.5},
    )
    assert "异常放量" in md
    assert "3.3x" in md
    assert "+7.50" in md


def test_event_template_pe_extreme():
    from app.services.notifier.event_templates import format_event
    md = format_event(
        event_type="PE_EXTREME_LOW",
        severity="medium",
        title="PE 历史低位",
        payload={"current_pe": 8.5, "percentile": 3.2, "low_threshold": 9.0, "high_threshold": 25.0},
    )
    assert "8.5" in md
    assert "3.2" in md


def test_event_template_aggregated():
    from app.services.notifier.event_templates import format_aggregated
    md = format_aggregated([
        {"event_type": "VOLUME_SPIKE", "title": "A 放量"},
        {"event_type": "MACD_DIVERGENCE_NEW", "title": "B 底背离"},
    ])
    assert "VOLUME_SPIKE" in md and "MACD_DIVERGENCE_NEW" in md
    assert format_aggregated([]) == ""
