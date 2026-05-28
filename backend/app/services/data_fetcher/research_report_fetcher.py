"""券商研报抓取（东财研报中心，免登录）

仅抓元数据：标题 / 机构 / 评级 / 三年 EPS · PE 预测 / PDF 直链。
不下载 PDF 全文（多数券商有访问限制，性价比低）。

数据源：akshare.stock_research_report_em(symbol)
返回 16 列，单只股票通常 50~200 条历史记录。
"""
import asyncio
import contextlib
import logging
import os
from datetime import date, datetime, timedelta
from typing import Any

import akshare as ak
import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

_RATE_LIMIT_DELAY = 0.5


@contextlib.contextmanager
def _no_proxy():
    proxy_keys = ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"]
    saved = {k: os.environ.pop(k, None) for k in proxy_keys}
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        if pd.isna(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _to_date(v: Any) -> date | None:
    if v is None:
        return None
    if isinstance(v, date):
        return v
    try:
        return pd.Timestamp(v).date()
    except Exception:
        return None


def _detect_forecast_year_base(columns: list[str]) -> int | None:
    """从列名 '2026-盈利预测-收益' 之类提取最早的预测起始年"""
    years: list[int] = []
    for col in columns:
        s = str(col)
        if "盈利预测" in s and "-" in s:
            head = s.split("-", 1)[0]
            if head.isdigit() and len(head) == 4:
                years.append(int(head))
    return min(years) if years else None


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def fetch_research_reports(
    code: str, days: int = 30, max_items: int = 30
) -> list[dict]:
    """抓取近 N 天个股研报，按日期 desc 取最多 max_items 条"""
    await asyncio.sleep(_RATE_LIMIT_DELAY)

    def _run() -> list[dict]:
        with _no_proxy():
            df = ak.stock_research_report_em(symbol=code)
        if df is None or df.empty:
            return []
        forecast_base = _detect_forecast_year_base(list(df.columns))
        # 三年预测列名
        y1 = forecast_base
        y2 = forecast_base + 1 if forecast_base else None
        y3 = forecast_base + 2 if forecast_base else None
        eps_cols = {
            1: f"{y1}-盈利预测-收益" if y1 else None,
            2: f"{y2}-盈利预测-收益" if y2 else None,
            3: f"{y3}-盈利预测-收益" if y3 else None,
        }
        pe_cols = {
            1: f"{y1}-盈利预测-市盈率" if y1 else None,
            2: f"{y2}-盈利预测-市盈率" if y2 else None,
            3: f"{y3}-盈利预测-市盈率" if y3 else None,
        }

        cutoff = (datetime.now().date() - timedelta(days=days))
        out: list[dict] = []
        for _, row in df.iterrows():
            d = _to_date(row.get("日期"))
            if d and d < cutoff:
                continue
            item = {
                "stock_code": str(row.get("股票代码") or "").strip() or code,
                "stock_name": str(row.get("股票简称") or "").strip(),
                "title": str(row.get("报告名称") or "").strip(),
                "broker": str(row.get("机构") or "").strip(),
                "rating": str(row.get("东财评级") or "").strip() or None,
                "industry": str(row.get("行业") or "").strip() or None,
                "published_at": d,
                "pdf_url": str(row.get("报告PDF链接") or "").strip() or None,
                "forecast_year_base": forecast_base,
                "eps_y1": _to_float(row.get(eps_cols[1])) if eps_cols[1] else None,
                "eps_y2": _to_float(row.get(eps_cols[2])) if eps_cols[2] else None,
                "eps_y3": _to_float(row.get(eps_cols[3])) if eps_cols[3] else None,
                "pe_y1": _to_float(row.get(pe_cols[1])) if pe_cols[1] else None,
                "pe_y2": _to_float(row.get(pe_cols[2])) if pe_cols[2] else None,
                "pe_y3": _to_float(row.get(pe_cols[3])) if pe_cols[3] else None,
            }
            if not item["title"] or not item["broker"]:
                continue
            out.append(item)

        # 按日期 desc 排序，截断
        out.sort(key=lambda r: r["published_at"] or date.min, reverse=True)
        return out[:max_items]

    try:
        return await asyncio.to_thread(_run)
    except Exception as e:
        logger.error(f"[research][{code}] 研报抓取失败: {e}")
        raise
