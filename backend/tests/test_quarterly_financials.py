from datetime import date

import pandas as pd
import pytest

from app.api.v1.endpoints.analysis import _period_label_to_year_quarter
from app.services.data_fetcher.akshare_fetcher import AKShareFetcher


@pytest.mark.asyncio
async def test_fetch_quarterly_fundamentals_merges_em_amount_fields(monkeypatch):
    def fake_sina_indicator(symbol: str, start_year: str):
        assert symbol == "300750"
        return pd.DataFrame([
            {
                "日期": "2025-03-31",
                "净资产收益率(%)": 5.1,
                "加权净资产收益率(%)": 5.3,
                "销售毛利率(%)": None,
                "销售净利率(%)": 18.1,
                "资产负债率(%)": 61.2,
                "主营业务收入增长率(%)": 9.2,
                "净利润增长率(%)": 35.0,
                "流动比率": 1.6,
                "速动比率": 1.3,
                "扣除非经常性损益后的净利润(元)": 100_000_000,
            },
            {
                "日期": "2025-06-30",
                "净资产收益率(%)": 10.3,
                "加权净资产收益率(%)": 11.1,
                "销售毛利率(%)": None,
                "销售净利率(%)": 18.3,
                "资产负债率(%)": 61.0,
                "主营业务收入增长率(%)": 10.2,
                "净利润增长率(%)": 36.0,
                "流动比率": 1.7,
                "速动比率": 1.4,
                "扣除非经常性损益后的净利润(元)": 200_000_000,
            },
        ])

    def fake_em_indicator(symbol: str, indicator: str):
        assert symbol == "300750.SZ"
        assert indicator == "按报告期"
        return pd.DataFrame([
            {
                "REPORT_DATE": "2025-03-31 00:00:00",
                "TOTALOPERATEREVE": 1_000_000_000,
                "PARENTNETPROFIT": 150_000_000,
                "KCFJCXSYJLR": 120_000_000,
                "EPSJB": 1.2,
                "XSMLL": 24.5,
                "ROEJQ": 5.4,
            },
            {
                "REPORT_DATE": "2025-06-30 00:00:00",
                "TOTALOPERATEREVE": 2_300_000_000,
                "PARENTNETPROFIT": 300_000_000,
                "KCFJCXSYJLR": 260_000_000,
                "EPSJB": 2.4,
                "XSMLL": 25.5,
                "ROEJQ": 10.4,
            },
        ])

    monkeypatch.setattr(
        "app.services.data_fetcher.akshare_fetcher.ak.stock_financial_analysis_indicator",
        fake_sina_indicator,
    )
    monkeypatch.setattr(
        "app.services.data_fetcher.akshare_fetcher.ak.stock_financial_analysis_indicator_em",
        fake_em_indicator,
    )

    rows = await AKShareFetcher().fetch_quarterly_fundamentals("300750", start_year="2025")

    assert [r["period_label"] for r in rows] == ["2025Q1", "2025H1"]
    assert rows[0]["period_end"] == date(2025, 3, 31)
    assert rows[0]["revenue_yi"] == 10
    assert rows[0]["net_profit_yi"] == 1.5
    assert rows[0]["net_profit_deducted_yi"] == 1.2
    assert rows[0]["gross_margin"] == 24.5
    assert rows[1]["revenue_yi"] == 23
    assert rows[1]["net_profit_yi"] == 3
    assert rows[1]["net_profit_deducted_yi"] == 2.6


def test_period_label_to_year_quarter_handles_half_and_annual_reports():
    assert _period_label_to_year_quarter("2026Q1") == (2026, 1)
    assert _period_label_to_year_quarter("2025H1") == (2025, 2)
    assert _period_label_to_year_quarter("2025Q3") == (2025, 3)
    assert _period_label_to_year_quarter("2025A") == (2025, 4)
    assert _period_label_to_year_quarter("2025-05-31") is None
