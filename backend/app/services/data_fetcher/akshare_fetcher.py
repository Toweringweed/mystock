"""AKShare 数据采集器 — A股/港股历史行情、实时行情、基础信息"""
import asyncio
import contextlib
import logging
import os
from datetime import date, datetime, timedelta
from typing import Any

import akshare as ak
import pandas as pd
import requests
import yfinance as yf
from tenacity import retry, stop_after_attempt, wait_exponential


@contextlib.contextmanager
def _no_proxy():
    """
    临时清除代理。

    AKShare 的东财/巨潮等国内数据源在当前 Docker 环境里直连可用，
    但通过宿主机代理会出现 RemoteDisconnected，导致任务静默拿不到数据。
    """
    proxy_keys = ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"]
    saved = {k: os.environ.pop(k, None) for k in proxy_keys}
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v

logger = logging.getLogger(__name__)

# AKShare 调用间隔（秒），避免触发限频
_RATE_LIMIT_DELAY = 0.5


def _to_date(d: Any) -> date | None:
    if d is None:
        return None
    if isinstance(d, date):
        return d
    return pd.Timestamp(d).date()


def _to_float(v: Any) -> float | None:
    """安全转 float;空值/NaN/无法转换返回 None"""
    if v is None:
        return None
    try:
        f = float(v)
        if pd.isna(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


class AKShareFetcher:
    """AKShare 数据采集器，所有方法均在线程池中执行（AKShare 是同步库）"""

    # ──────────────────────────────────────────────
    # 股票搜索与基础信息
    # ──────────────────────────────────────────────

    async def search_stocks(self, keyword: str) -> list[dict]:
        """搜索 A股 + 港股，返回匹配列表"""
        results: list[dict] = []

        # A股搜索
        try:
            a_results = await asyncio.to_thread(self._search_a_stock, keyword)
            results.extend(a_results)
        except Exception as e:
            logger.warning(f"A股搜索失败: {e}")

        await asyncio.sleep(_RATE_LIMIT_DELAY)

        # 港股搜索
        try:
            hk_results = await asyncio.to_thread(self._search_hk_stock, keyword)
            results.extend(hk_results)
        except Exception as e:
            logger.warning(f"港股搜索失败: {e}")

        return results

    def _search_a_stock(self, keyword: str) -> list[dict]:
        with _no_proxy():
            df = ak.stock_info_a_code_name()
        # 按代码或名称匹配
        mask = df["code"].str.contains(keyword, na=False) | df["name"].str.contains(
            keyword, na=False
        )
        matched = df[mask].head(10)
        return [
            {"code": row["code"], "name": row["name"], "market": "A", "industry": None}
            for _, row in matched.iterrows()
        ]

    def _search_hk_stock(self, keyword: str) -> list[dict]:
        with _no_proxy():
            df = ak.stock_hk_spot_em()
        mask = df["代码"].str.contains(keyword, na=False) | df["名称"].str.contains(
            keyword, na=False
        )
        matched = df[mask].head(10)
        return [
            {
                "code": row["代码"].zfill(5),  # 统一补齐5位
                "name": row["名称"],
                "market": "HK",
                "industry": None,
            }
            for _, row in matched.iterrows()
        ]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def fetch_stock_info(self, code: str, market: str) -> dict | None:
        """获取单只股票基础信息（名称、行业、板块）"""
        try:
            if market == "A":
                return await asyncio.to_thread(self._fetch_a_stock_info, code)
            else:
                return await asyncio.to_thread(self._fetch_hk_stock_info, code)
        except Exception as e:
            logger.error(f"[{code}] 获取基础信息失败: {e}")
            return None

    def _fetch_a_stock_info(self, code: str) -> dict:
        with _no_proxy():
            df = ak.stock_individual_info_em(symbol=code)
        info = dict(zip(df["item"], df["value"]))
        return {
            "name": info.get("股票简称", ""),
            "industry": info.get("行业", None),
            "sector": info.get("板块", None),
        }

    def _fetch_hk_stock_info(self, code: str) -> dict:
        with _no_proxy():
            df = ak.stock_hk_spot_em()
        row = df[df["代码"] == code.lstrip("0").zfill(5)]
        if row.empty:
            return {"name": code, "industry": None, "sector": None}
        return {
            "name": row.iloc[0]["名称"],
            "industry": None,
            "sector": None,
        }

    # ──────────────────────────────────────────────
    # 历史 K 线
    # ──────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def fetch_daily_kline(
        self, code: str, market: str = "A", days: int = 90
    ) -> list[dict]:
        """获取日线 K 线（前复权），返回标准化列表"""
        end_date = date.today()
        start_date = end_date - timedelta(days=days + 60)  # 多取60天用于指标计算

        try:
            if market == "A":
                data = await asyncio.to_thread(
                    self._fetch_a_kline, code, start_date, end_date
                )
            else:
                data = await asyncio.to_thread(
                    self._fetch_hk_kline, code, start_date, end_date
                )
            await asyncio.sleep(_RATE_LIMIT_DELAY)
            return data
        except Exception as e:
            logger.error(f"[{code}] 获取K线失败: {e}")
            raise

    def _a_code_to_yf(self, code: str) -> str:
        """将 A 股代码转换为 yfinance 格式（600519 → 600519.SS，000001 → 000001.SZ）"""
        if code.startswith(("6", "9")):
            return f"{code}.SS"
        return f"{code}.SZ"

    def _a_code_to_em_secucode(self, code: str) -> str:
        """将 A 股代码转换为东方财富 F10 接口格式（300750 → 300750.SZ）"""
        if code.startswith(("6", "9")):
            return f"{code}.SH"
        return f"{code}.SZ"

    def _fetch_a_kline(self, code: str, start: date, end: date) -> list[dict]:
        try:
            with _no_proxy():
                df = ak.stock_zh_a_hist(
                    symbol=code,
                    period="daily",
                    start_date=start.strftime("%Y%m%d"),
                    end_date=end.strftime("%Y%m%d"),
                    adjust="qfq",  # 前复权
                )
            if df.empty:
                raise ValueError("AKShare returned empty dataframe")
            df = df.rename(
                columns={
                    "日期": "trade_date",
                    "开盘": "open",
                    "最高": "high",
                    "最低": "low",
                    "收盘": "close",
                    "成交量": "volume",
                    "成交额": "amount",
                    "换手率": "turnover",
                    "涨跌幅": "change_pct",
                }
            )
            df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
            cols = ["trade_date", "open", "high", "low", "close", "volume", "amount", "turnover", "change_pct"]
            return df[cols].to_dict("records")
        except Exception as e:
            logger.warning(f"[{code}] AKShare K线失败，降级到 yfinance: {e}")
            return self._fetch_kline_yfinance(self._a_code_to_yf(code), start, end)

    def _fetch_hk_kline(self, code: str, start: date, end: date) -> list[dict]:
        try:
            # AKShare 港股历史数据
            with _no_proxy():
                df = ak.stock_hk_hist(
                    symbol=code,
                    period="daily",
                    start_date=start.strftime("%Y%m%d"),
                    end_date=end.strftime("%Y%m%d"),
                    adjust="qfq",
                )
            if df.empty:
                raise ValueError("AKShare returned empty dataframe")
            df = df.rename(
                columns={
                    "日期": "trade_date",
                    "开盘": "open",
                    "最高": "high",
                    "最低": "low",
                    "收盘": "close",
                    "成交量": "volume",
                    "成交额": "amount",
                    "换手率": "turnover",
                    "涨跌幅": "change_pct",
                }
            )
            df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
            cols = ["trade_date", "open", "high", "low", "close", "volume", "amount", "turnover", "change_pct"]
            available = [c for c in cols if c in df.columns]
            return df[available].to_dict("records")
        except Exception as e:
            logger.warning(f"[{code}] AKShare HK K线失败，降级到 yfinance: {e}")
            # HK code: "00700" → "0700.HK"
            yf_code = f"{code.lstrip('0') or '0'}.HK"
            return self._fetch_kline_yfinance(yf_code, start, end)

    def _fetch_kline_yfinance(self, yf_ticker: str, start: date, end: date) -> list[dict]:
        """使用 yfinance 获取 K 线数据（AKShare 失败时的备用方案）"""
        ticker = yf.Ticker(yf_ticker)
        df = ticker.history(start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"), auto_adjust=True)
        if df.empty:
            return []
        # yfinance multi-index columns → flatten
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] for col in df.columns]
        df = df.reset_index()
        df = df.rename(columns={
            "Date": "trade_date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        })
        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
        # yfinance doesn't provide amount/turnover/change_pct
        df["amount"] = None
        df["turnover"] = None
        df["change_pct"] = df["close"].pct_change() * 100
        cols = ["trade_date", "open", "high", "low", "close", "volume", "amount", "turnover", "change_pct"]
        available = [c for c in cols if c in df.columns]
        logger.info(f"[{yf_ticker}] yfinance 获取 {len(df)} 条K线数据")
        return df[available].to_dict("records")

    # ──────────────────────────────────────────────
    # 实时行情
    # ──────────────────────────────────────────────

    async def fetch_realtime_quotes(self, codes: list[str]) -> list[dict]:
        """批量获取实时行情（A股）"""
        try:
            data = await asyncio.to_thread(self._fetch_realtime_batch, codes)
            return data
        except Exception as e:
            logger.error(f"实时行情获取失败: {e}")
            return []

    def _fetch_realtime_batch(self, codes: list[str]) -> list[dict]:
        try:
            with _no_proxy():
                df = ak.stock_zh_a_spot_em()
        except Exception as exc:
            logger.warning(f"AKShare 实时行情失败，改用东方财富直连: {exc}")
            try:
                rows = self._fetch_realtime_batch_eastmoney(codes)
                if rows:
                    return rows
            except Exception as em_exc:
                logger.warning(f"东方财富直连实时行情失败，改用新浪行情: {em_exc}")
            return self._fetch_realtime_batch_sina(codes)

        df = df[df["代码"].isin(codes)]
        result = []
        for _, row in df.iterrows():
            result.append({
                "code": row["代码"],
                "name": row["名称"],
                "price": float(row.get("最新价", 0) or 0),
                "change_pct": float(row.get("涨跌幅", 0) or 0),
                "volume": int(row.get("成交量", 0) or 0),
                "amount": float(row.get("成交额", 0) or 0),
                "turnover": float(row.get("换手率", 0) or 0),
                "pe_ttm": float(row.get("市盈率-动态", 0) or 0) or None,
                "updated_at": datetime.now().isoformat(),
            })
        return result

    def _fetch_realtime_batch_eastmoney(self, codes: list[str]) -> list[dict]:
        """东方财富实时行情兜底。

        AKShare 的 spot 包装层在 Docker 内偶发 RemoteDisconnected。这里直接调用
        同一个 EastMoney endpoint，避免首页实时价因为单个包装层失败而长期为空。
        """
        url = "https://82.push2.eastmoney.com/api/qt/clist/get"
        base_params = {
            "po": 1,
            "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2,
            "invt": 2,
            "fid": "f12",
            "fs": "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23,m:0 t:81 s:2048",
            "fields": "f2,f3,f5,f6,f8,f9,f12,f14",
        }
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            ),
            "Referer": "https://quote.eastmoney.com/",
        }
        wanted = set(codes)

        def _num(value, default=0.0):
            if value in (None, "-", ""):
                return default
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        result = []
        found: set[str] = set()
        page_size = 200
        for page in range(1, 40):
            params = {**base_params, "pn": page, "pz": page_size}
            with _no_proxy():
                resp = requests.get(url, params=params, headers=headers, timeout=15)
                resp.raise_for_status()
            data = resp.json().get("data") or {}
            rows = data.get("diff") or []
            if not rows:
                break
            for row in rows:
                code = str(row.get("f12") or "")
                if code not in wanted or code in found:
                    continue
                found.add(code)
                result.append({
                    "code": code,
                    "name": row.get("f14") or code,
                    "price": _num(row.get("f2")),
                    "change_pct": _num(row.get("f3")),
                    "volume": int(_num(row.get("f5"))),
                    "amount": _num(row.get("f6")),
                    "turnover": _num(row.get("f8")),
                    "pe_ttm": _num(row.get("f9"), None),
                    "updated_at": datetime.now().isoformat(),
                })
            if found >= wanted:
                break
        return result

    def _fetch_realtime_batch_sina(self, codes: list[str]) -> list[dict]:
        """新浪行情兜底，只提供首页实时价需要的核心字段。"""
        symbols = []
        code_by_symbol = {}
        for code in codes:
            prefix = "sh" if code.startswith(("6", "9")) else "sz"
            symbol = f"{prefix}{code}"
            symbols.append(symbol)
            code_by_symbol[symbol] = code
        if not symbols:
            return []

        url = f"https://hq.sinajs.cn/list={','.join(symbols)}"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            ),
            "Referer": "https://finance.sina.com.cn",
        }
        with _no_proxy():
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()

        text = resp.content.decode("gb18030", errors="ignore")
        result = []
        for line in text.splitlines():
            if '="' not in line:
                continue
            symbol = line.split("hq_str_", 1)[-1].split("=", 1)[0]
            code = code_by_symbol.get(symbol)
            if not code:
                continue
            payload = line.split('="', 1)[-1].rstrip('";')
            fields = payload.split(",")
            if len(fields) < 10 or not fields[0]:
                continue
            try:
                open_price = float(fields[1] or 0)
                prev_close = float(fields[2] or 0)
                price = float(fields[3] or 0)
                high = float(fields[4] or 0)
                low = float(fields[5] or 0)
                volume = int(float(fields[8] or 0))
                amount = float(fields[9] or 0)
                trade_date = pd.to_datetime(fields[30]).date() if len(fields) > 30 and fields[30] else None
            except ValueError:
                continue
            change_pct = ((price - prev_close) / prev_close * 100) if prev_close else 0.0
            result.append({
                "code": code,
                "name": fields[0],
                "price": price,
                "change_pct": change_pct,
                "volume": volume,
                "amount": amount,
                "turnover": 0.0,
                "pe_ttm": None,
                "open": open_price,
                "high": high,
                "low": low,
                "trade_date": trade_date.isoformat() if trade_date else None,
                "updated_at": datetime.now().isoformat(),
            })
        return result

    # ──────────────────────────────────────────────
    # 基本面数据
    # ──────────────────────────────────────────────

    # 比率/累计型字段:yfinance 是 TTM,AKShare stock_financial_analysis_indicator
    # 给的是"年初到当前季度累计",数值口径不同(Q1 累计 ROE ≈ 全年 ROE / 4)。
    # 这些字段不能让 AKShare 覆盖 yfinance 的 TTM 值。
    _TTM_RATIO_FIELDS = {
        "roe", "gross_margin", "net_margin",
        "revenue_yoy", "profit_yoy",
    }

    async def fetch_fundamental(self, code: str, market: str = "A") -> dict:
        """获取基本面指标(PE / PB / PS / ROE / margins / yoy 增速)

        合并策略:
          - PE / PB / PS / 增速 / 营收 / 净利:yfinance 优先(TTM 真值)
          - ROE / 毛利率 / 净利率(TTM 比率):**只用 yfinance**,AKShare 是季度
            累计口径,会污染数据
          - 资产负债率 / 财务结构:yfinance 没有时用 AKShare 兜底
        """
        yf_ticker = self._a_code_to_yf(code) if market == "A" else f"{code.lstrip('0') or '0'}.HK"
        result: dict = {}

        # yfinance 优先(TTM 估值 + TTM 比率)
        try:
            yf_data = await asyncio.to_thread(self._fetch_fundamental_yfinance, yf_ticker)
            result.update(yf_data)
        except Exception as e:
            logger.warning(f"[{code}] yfinance 基本面获取失败: {e}")

        if market == "A":
            try:
                ak_data = await asyncio.to_thread(self._fetch_a_fundamental_akshare, code)
                for k, v in ak_data.items():
                    if v is None:
                        continue
                    # TTM 比率字段:yfinance 已给则跳过 AKShare(口径不同)
                    if k in self._TTM_RATIO_FIELDS and result.get(k) is not None:
                        continue
                    result[k] = v
            except Exception as e:
                logger.warning(f"[{code}] AKShare 财务指标获取失败: {e}")

        return result

    async def fetch_quarterly_fundamentals(
        self, code: str, start_year: str = "2023", market: str = "A"
    ) -> list[dict]:
        """抓取个股**所有报告期**的财务分析指标(季度+年度,含半年报/三季报/年报)。

        返回 list of dict, 每条对应一个报告期。字段:
          period_end (date): 报告期末日期
          period_label (str): "2026Q1" / "2025H1" / "2025A" 等
          revenue_yi / net_profit_yi / net_profit_deducted_yi / roe / gross_margin
          / net_margin / debt_ratio / revenue_yoy / profit_yoy

        AKShare `stock_financial_analysis_indicator` 默认返回每个报告期一行,典型粒度 = 季度。
        """
        if market != "A":
            logger.info(f"[{code}] 暂跳过非 A 股季度财务抓取: market={market}")
            return []

        def _period_label(period_end: date) -> str:
            month, day = period_end.month, period_end.day
            year = period_end.year
            if month == 3 and day == 31:
                return f"{year}Q1"
            if month == 6 and day == 30:
                return f"{year}H1"
            if month == 9 and day == 30:
                return f"{year}Q3"
            if month == 12 and day == 31:
                return f"{year}A"
            return period_end.isoformat()

        def _row_float(row, *cols: str, scale: float = 1.0) -> float | None:
            for col in cols:
                if col not in row:
                    continue
                v = row.get(col)
                try:
                    if v is not None and not pd.isna(v):
                        return float(v) / scale
                except (ValueError, TypeError):
                    continue
            return None

        def _parse_period_end(value) -> date | None:
            try:
                return pd.to_datetime(value).date()
            except (ValueError, TypeError):
                return None

        start_year_int = int(start_year)
        by_period: dict[date, dict] = {}

        try:
            with _no_proxy():
                df = await asyncio.to_thread(
                    ak.stock_financial_analysis_indicator, symbol=code, start_year=start_year
                )
        except Exception as e:
            logger.warning(f"[{code}] AKShare 新浪财务指标获取失败: {e}")
            df = None

        if df is not None and not df.empty:
            for _, row in df.iterrows():
                # 日期字段名可能是 "日期" 或 "报告期"
                period_end = _parse_period_end(row.get("日期") or row.get("报告期"))
                if not period_end or period_end.year < start_year_int:
                    continue

                by_period[period_end] = {
                    "period_end": period_end,
                    "period_label": _period_label(period_end),
                    "eps": _row_float(row, "摊薄每股收益(元)", "加权每股收益(元)"),
                    "net_profit_deducted_yi": _row_float(
                        row, "扣除非经常性损益后的净利润(元)", scale=1e8
                    ),
                    "roe": _row_float(row, "净资产收益率(%)"),
                    "roe_weighted": _row_float(row, "加权净资产收益率(%)"),
                    "gross_margin": _row_float(row, "销售毛利率(%)"),
                    "net_margin": _row_float(row, "销售净利率(%)"),
                    "debt_ratio": _row_float(row, "资产负债率(%)"),
                    "revenue_yoy": _row_float(row, "主营业务收入增长率(%)"),
                    "profit_yoy": _row_float(row, "净利润增长率(%)"),
                    "current_ratio": _row_float(row, "流动比率"),
                    "quick_ratio": _row_float(row, "速动比率"),
                    "cash_flow_to_profit": _row_float(row, "经营现金净流量与净利润的比率(%)"),
                }

        # 东方财富 F10 主指标含营收/归母净利/扣非净利金额；原新浪指标通常没有营收。
        try:
            with _no_proxy():
                em_df = await asyncio.to_thread(
                    ak.stock_financial_analysis_indicator_em,
                    symbol=self._a_code_to_em_secucode(code),
                    indicator="按报告期",
                )
        except Exception as e:
            logger.warning(f"[{code}] AKShare 东方财富财务指标获取失败: {e}")
            em_df = None

        if em_df is not None and not em_df.empty:
            for _, row in em_df.iterrows():
                period_end = _parse_period_end(row.get("REPORT_DATE"))
                if not period_end or period_end.year < start_year_int:
                    continue
                item = by_period.setdefault(period_end, {
                    "period_end": period_end,
                    "period_label": _period_label(period_end),
                })
                enrich = {
                    "revenue_yi": _row_float(row, "TOTALOPERATEREVE", scale=1e8),
                    "net_profit_yi": _row_float(row, "PARENTNETPROFIT", scale=1e8),
                    "net_profit_deducted_yi": _row_float(
                        row, "KCFJCXSYJLR", "DEDU_PARENT_PROFIT", scale=1e8
                    ),
                    "eps": _row_float(row, "EPSJB", "EPSXS"),
                    "roe": _row_float(row, "ROEJQ"),
                    "roe_weighted": _row_float(row, "ROEJQ"),
                    "gross_margin": _row_float(row, "XSMLL", "GROSS_PROFIT_RATIO"),
                    "net_margin": _row_float(row, "XSJLL", "NET_PROFIT_RATIO"),
                    "debt_ratio": _row_float(row, "ZCFZL"),
                    "revenue_yoy": _row_float(row, "TOTALOPERATEREVETZ"),
                    "profit_yoy": _row_float(row, "PARENTNETPROFITTZ"),
                    "profit_qoq": _row_float(row, "NETPROFITRPHBZC", "DJD_DPNP_QOQ"),
                    "current_ratio": _row_float(row, "LD"),
                    "quick_ratio": _row_float(row, "SD"),
                    "cash_flow_to_profit": _row_float(row, "NCO_NETPROFIT"),
                    "roic": _row_float(row, "ROIC"),
                    "fcf_yi": _row_float(row, "FCFF_BACK", scale=1e8),
                }
                for key, value in enrich.items():
                    if value is not None:
                        item[key] = value

        out = list(by_period.values())
        if not out:
            return []

        for item in out:
            item.setdefault("revenue_yi", None)
            item.setdefault("net_profit_yi", None)
            item.setdefault("net_profit_deducted_yi", None)
            item.setdefault("eps", None)
            item.setdefault("roe", None)
            item.setdefault("roe_weighted", None)
            item.setdefault("gross_margin", None)
            item.setdefault("net_margin", None)
            item.setdefault("debt_ratio", None)
            item.setdefault("revenue_yoy", None)
            item.setdefault("profit_yoy", None)
            item.setdefault("profit_qoq", None)
            item.setdefault("current_ratio", None)
            item.setdefault("quick_ratio", None)
            item.setdefault("cash_flow_to_profit", None)
            item.setdefault("roic", None)
            item.setdefault("fcf_yi", None)

        # 按时间升序(最早 → 最新)
        out.sort(key=lambda x: x["period_end"])
        return out

    def _fetch_a_fundamental_akshare(self, code: str) -> dict:
        with _no_proxy():
            df = ak.stock_financial_analysis_indicator(symbol=code, start_year="2023")
        if df is None or df.empty:
            return {}
        latest = df.iloc[-1]
        def _f(col, scale=1.0):
            v = latest.get(col)
            try:
                return float(v) / scale if v is not None and not pd.isna(v) else None
            except Exception:
                return None
        return {
            "pe_ttm": None,  # 财务分析指标不含 PE，由实时行情补充
            "pb": None,
            "roe": _f("净资产收益率(%)"),
            "gross_margin": _f("销售毛利率(%)"),
            "net_margin": _f("销售净利率(%)"),
            "debt_ratio": _f("资产负债率(%)"),
            "revenue_yoy": _f("主营业务收入增长率(%)"),
            "profit_yoy": _f("净利润增长率(%)"),
        }

    def _fetch_fundamental_yfinance(self, yf_ticker: str) -> dict:
        t = yf.Ticker(yf_ticker)
        info = t.info

        def _pct(v):
            return round(v * 100, 2) if v is not None else None

        # net_profit / revenue in yuan (netIncomeToCommon is in currency units)
        net_income = info.get("netIncomeToCommon")
        revenue = float(info["totalRevenue"]) if info.get("totalRevenue") else None
        market_cap = info.get("marketCap")
        # PS-TTM 优先用 yfinance 提供的 priceToSalesTrailing12Months；fallback 用 market_cap / revenue
        ps = info.get("priceToSalesTrailing12Months")
        if ps is None and market_cap and revenue and revenue > 0:
            ps = market_cap / revenue
        return {
            "pe_ttm": info.get("trailingPE"),
            "pb": info.get("priceToBook"),
            "ps": float(ps) if ps is not None else None,
            "roe": _pct(info.get("returnOnEquity")),
            "gross_margin": _pct(info.get("grossMargins")),
            "net_margin": _pct(info.get("profitMargins")),
            "debt_ratio": info.get("debtToEquity"),
            "revenue_yoy": _pct(info.get("revenueGrowth")),
            "profit_yoy": _pct(info.get("earningsGrowth")),
            "net_profit": float(net_income) if net_income is not None else None,
            "revenue": revenue,
            "eps": float(info["trailingEps"]) if info.get("trailingEps") else None,
        }

    # ──────────────────────────────────────────────
    # P1 扩展：资金流向 / 龙虎榜 / 日历 / 减持公告
    # ──────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    async def fetch_capital_flows(self, code: str, days: int = 30) -> list[dict]:
        """北上资金日度（个股持股 + 推算净流入）"""
        await asyncio.sleep(_RATE_LIMIT_DELAY)
        return await asyncio.to_thread(self._fetch_capital_flows_sync, code, days)

    def _fetch_capital_flows_sync(self, code: str, days: int) -> list[dict]:
        with _no_proxy():
            try:
                # AKShare 提供 stock_hsgt_hold_stock_em：北上累计持股（按日期、个股）
                df = ak.stock_hsgt_hold_stock_em(market="北向", indicator="今日排行")
                # 这个接口是当日横截面，按日期序列要用 stock_hsgt_hist_em
                df_hist = ak.stock_hsgt_hist_em(symbol=code)
            except Exception as e:
                logger.warning(f"[{code}] 北上资金抓取失败: {e}")
                return []
        if df_hist is None or df_hist.empty:
            return []
        df_hist = df_hist.tail(days).copy()
        # 字段名因 akshare 版本不同，取存在的列
        col_map = {
            "日期": "trade_date",
            "当日成交净买额": "net_inflow",  # 单位：万元
            "持股市值": "shareholding_value",  # 单位：万元
            "占流通股比": "shareholding_ratio",
            "持股数量": "shareholding_volume",
        }
        for k in list(col_map.keys()):
            if k not in df_hist.columns:
                col_map.pop(k)
        df_hist = df_hist.rename(columns=col_map)

        results: list[dict] = []
        for _, row in df_hist.iterrows():
            d = _to_date(row.get("trade_date"))
            if not d:
                continue
            # net_inflow 万元 → 元
            net = row.get("net_inflow")
            try:
                net_yuan = float(net) * 10000 if net is not None and not pd.isna(net) else None
            except Exception:
                net_yuan = None
            try:
                ratio = float(row.get("shareholding_ratio")) if row.get("shareholding_ratio") is not None else None
            except Exception:
                ratio = None
            try:
                vol = int(row.get("shareholding_volume")) if row.get("shareholding_volume") is not None else None
            except Exception:
                vol = None
            results.append({
                "trade_date": d,
                "net_inflow": net_yuan,
                "shareholding_ratio": ratio,
                "shareholding_volume": vol,
            })
        return results

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    async def fetch_lhb(self, trade_date: date) -> list[dict]:
        """当日龙虎榜全表（含买卖席位）"""
        await asyncio.sleep(_RATE_LIMIT_DELAY)
        return await asyncio.to_thread(self._fetch_lhb_sync, trade_date)

    def _fetch_lhb_sync(self, trade_date: date) -> list[dict]:
        date_str = trade_date.strftime("%Y%m%d")
        with _no_proxy():
            try:
                df = ak.stock_lhb_detail_em(start_date=date_str, end_date=date_str)
            except Exception as e:
                logger.warning(f"[lhb] 龙虎榜抓取失败 {date_str}: {e}")
                return []
        if df is None or df.empty:
            return []
        out: list[dict] = []
        for _, row in df.iterrows():
            code = str(row.get("代码", "")).strip()
            if not code:
                continue
            buy = row.get("龙虎榜买入额", 0) or 0
            sell = row.get("龙虎榜卖出额", 0) or 0
            try:
                buy_f = float(buy)
                sell_f = float(sell)
            except Exception:
                buy_f = sell_f = 0.0
            out.append({
                "code": code,
                "trade_date": trade_date,
                "reason": str(row.get("上榜原因", "") or ""),
                "buy_amount": buy_f,
                "sell_amount": sell_f,
                "net_amount": buy_f - sell_f,
                "change_pct": float(row.get("涨跌幅", 0) or 0),
            })
        return out

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    async def fetch_disclosure_calendar(self, days_ahead: int = 90) -> list[dict]:
        """业绩预告/财报披露日历（未来 N 天）"""
        await asyncio.sleep(_RATE_LIMIT_DELAY)
        return await asyncio.to_thread(self._fetch_disclosure_calendar_sync, days_ahead)

    def _fetch_disclosure_calendar_sync(self, days_ahead: int) -> list[dict]:
        # AKShare 业绩预告: stock_yjyg_em(date="20260331") 按报告期；披露时间表用 stock_yysj_em
        today = date.today()
        end = today + timedelta(days=days_ahead)
        with _no_proxy():
            try:
                # 取本季度财报披露时间表（季报/年报）
                df = ak.stock_yysj_em(symbol="沪深京", date=today.strftime("%Y%m%d")[:6] + "30")
            except Exception as e:
                logger.warning(f"[calendar] 披露日历抓取失败: {e}")
                return []
        if df is None or df.empty:
            return []
        out: list[dict] = []
        for _, row in df.iterrows():
            code = str(row.get("股票代码", "") or row.get("代码", "")).strip().zfill(6)
            d = _to_date(row.get("最新披露日期") or row.get("披露日期"))
            if not code or not d:
                continue
            if d < today or d > end:
                continue
            out.append({
                "code": code,
                "name": str(row.get("股票简称", "") or row.get("名称", "")),
                "event_date": d,
                "title": f"{row.get('股票简称', '')} 财报披露",
                "source": "akshare:stock_yysj_em",
            })
        return out

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    async def fetch_restricted_release(self, days_ahead: int = 90) -> list[dict]:
        """限售股解禁日历（未来 N 天）"""
        await asyncio.sleep(_RATE_LIMIT_DELAY)
        return await asyncio.to_thread(self._fetch_restricted_release_sync, days_ahead)

    def _fetch_restricted_release_sync(self, days_ahead: int) -> list[dict]:
        today = date.today()
        end = today + timedelta(days=days_ahead)
        with _no_proxy():
            try:
                df = ak.stock_restricted_release_queue_em()
            except Exception as e:
                logger.warning(f"[calendar] 解禁日历抓取失败: {e}")
                return []
        if df is None or df.empty:
            return []
        out: list[dict] = []
        for _, row in df.iterrows():
            code = str(row.get("股票代码", "") or "").strip().zfill(6)
            d = _to_date(row.get("解禁时间") or row.get("解禁日期"))
            if not code or not d:
                continue
            if d < today or d > end:
                continue
            try:
                shares = float(row.get("解禁数量", 0) or 0)
                value = float(row.get("解禁市值", 0) or 0)
            except Exception:
                shares = value = 0.0
            out.append({
                "code": code,
                "name": str(row.get("股票简称", "") or ""),
                "event_date": d,
                "title": f"{row.get('股票简称', '')} 解禁 {shares:,.0f} 股",
                "payload": {
                    "shares": shares,
                    "market_value": value,
                    "ratio": row.get("占总股本比例") or row.get("占流通股比例"),
                },
                "source": "akshare:stock_restricted_release_queue_em",
            })
        return out

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    async def fetch_profit_forecasts(self, code: str) -> list[dict]:
        """从同花顺 i问财获取一致预期(机构覆盖数+最小/均值/最大 EPS 与净利润)

        返回每个未来年份一条记录:
            {forecast_year, eps_min/avg/max, net_profit_min/avg/max(元),
             analyst_count, source='ths'}

        相比 LLM 估算的优势:
          - 真实机构覆盖数(可信度信号)
          - 最小/最大区间(可计算保守/乐观档)
          - 数据时效与公开盘可见性高度同步
        """
        await asyncio.sleep(_RATE_LIMIT_DELAY)
        return await asyncio.to_thread(self._fetch_profit_forecasts_sync, code)

    def _fetch_profit_forecasts_sync(self, code: str) -> list[dict]:
        with _no_proxy():
            try:
                df_eps = ak.stock_profit_forecast_ths(symbol=code, indicator="预测年报每股收益")
            except Exception as e:
                logger.warning(f"[{code}] 同花顺 EPS 预期获取失败: {e}")
                df_eps = None
            try:
                df_np = ak.stock_profit_forecast_ths(symbol=code, indicator="预测年报净利润")
            except Exception as e:
                logger.warning(f"[{code}] 同花顺净利润预期获取失败: {e}")
                df_np = None

        if (df_eps is None or df_eps.empty) and (df_np is None or df_np.empty):
            return []

        # 用年度作 key 合并两表
        rows: dict[int, dict] = {}

        def _ingest(df, prefix: str):
            if df is None or df.empty or "年度" not in df.columns:
                return
            for _, r in df.iterrows():
                try:
                    year = int(r["年度"])
                except (TypeError, ValueError):
                    continue
                row = rows.setdefault(year, {"forecast_year": year})
                row["analyst_count"] = int(r["预测机构数"]) if "预测机构数" in df.columns else None
                row[f"{prefix}_min"] = _to_float(r.get("最小值"))
                row[f"{prefix}_avg"] = _to_float(r.get("均值"))
                row[f"{prefix}_max"] = _to_float(r.get("最大值"))

        _ingest(df_eps, "eps")
        _ingest(df_np, "net_profit")

        out = []
        for year in sorted(rows.keys()):
            r = rows[year]
            # 净利润是亿元,转 元
            for k in ("net_profit_min", "net_profit_avg", "net_profit_max"):
                if k in r and r[k] is not None:
                    r[k] = r[k] * 1e8
            r["source"] = "ths"
            out.append(r)
        return out

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    async def fetch_insider_announcements(self, code: str, limit: int = 30) -> list[dict]:
        """抓取个股减持/增持公告标题（关键词过滤）"""
        await asyncio.sleep(_RATE_LIMIT_DELAY)
        return await asyncio.to_thread(self._fetch_insider_announcements_sync, code, limit)

    def _fetch_insider_announcements_sync(self, code: str, limit: int) -> list[dict]:
        keywords = ["减持", "增持", "回购", "持股变动", "权益变动"]
        with _no_proxy():
            try:
                df = ak.stock_individual_notice_report(security=code, symbol="全部")
            except Exception as e:
                logger.warning(f"[{code}] 减持公告抓取失败: {e}")
                return []
        if df is None or df.empty:
            return []
        mask = df["公告标题"].str.contains("|".join(keywords), na=False)
        df = df[mask].head(limit)
        out: list[dict] = []
        for _, row in df.iterrows():
            d = _to_date(row.get("公告日期"))
            if not d:
                continue
            out.append({
                "ann_date": d,
                "title": str(row.get("公告标题", "") or "").strip(),
                "url": str(row.get("网址", "") or ""),
            })
        return out


# 模块级单例，供搜索接口使用
async def search_stocks(keyword: str) -> list[dict]:
    fetcher = AKShareFetcher()
    return await fetcher.search_stocks(keyword)
