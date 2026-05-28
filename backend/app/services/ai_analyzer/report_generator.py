"""AI 综合分析报告生成器"""
import json
import logging
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.analysis import AnalysisReport
from app.models.stock import Stock
from sqlalchemy import select

logger = logging.getLogger(__name__)

REPORT_PROMPT = """你是一位资深A股/港股投资分析师，请基于以下数据对 {name}（{code}）进行综合分析。

注意：以下三个字段会直接展示在自选股表格和详情页顶部，必须言简意赅、可独立阅读：
  · industry_inflection（行业需求拐点）
  · external_disruption（外部颠覆力量）
  · action_suggestion（AI 操作建议）

【基本面】
- PE-TTM: {pe_ttm}
- PB: {pb}
- ROE: {roe}%
- 2026年预测净利润: {net_profit_2026}亿，远期PE: {forward_pe_2026}x
- 2027年预测净利润: {net_profit_2027}亿，远期PE: {forward_pe_2027}x

【技术面 - 最近交易日(基础指标)】
- 收盘价: {close_price} (距 30 日高 {dist_30d_high}% / 距 30 日低 {dist_30d_low}%)
- MA 排列: {ma_status} (MA5={ma5} / MA20={ma20} / MA60={ma60})
- MACD: {macd_status} (DIFF={macd_diff} / DEA={macd_signal_val} / 柱={macd_hist})
- RSI(14): {rsi_14} ({rsi_status})
- KDJ: K={kdj_k} D={kdj_d} J={kdj_j} ({kdj_status})
- 布林带: {bb_status}
- 背离信号: {divergence}
- 筹码: 获利盘 {profit_ratio}% / 平均成本 {avg_cost} 元 / 集中度 {chip_concentration}%

【技术面 - 量价 / 动量 / 趋势(扩展指标)】
- 近 20 日平均量比: {avg_volume_ratio_20d} (>1.5 显著放量 / <0.7 缩量整理)
- 近 20 日换手率均值: {avg_turnover_20d}%
- 60 日累计涨跌幅: {return_60d}% ({return_60d_label})
- 20 日累计涨跌幅: {return_20d}%
- 5 日累计涨跌幅: {return_5d}%
- 60 日相对沪深300强度: {relative_strength_60d} ({relative_strength_label})
- 主力资金近5日净流入: {fund_flow_5d}亿
- 主力资金近20日净流入: {fund_flow_20d}亿
- 北向资金近5日净流入: {north_flow_5d}亿

【近 7 天事件】
{events_summary}

【近期相关资讯（最近7日，最多5条）】
{news_summary}

请输出以下 JSON 格式（不要有多余文字）。其中 technical_analysis 字段必须为分论点结构,400 字左右,给出明确多空判断+证据+应对:
{{
  "conclusion": "一句话结论（20字以内）",
  "overall_signal": "bullish|bearish|neutral",
  "technical_score": 7,
  "fundamental_score": 6,
  "industry_inflection": "行业需求拐点（≤45字，给方向+核心证据，如'AI算力扩产周期向上，CSP capex Q1+38%'）",
  "external_disruption": "外部颠覆力量（≤45字，无则写'暂无显著颠覆力量'，如'光模块CPO技术替代加速，2027年起冲击'）",
  "action_suggestion": "可执行操作建议（≤70字，含价位/仓位/触发条件，如'160元以下加仓至5%仓位，跌破MA60止损'）",
  "technical_analysis": "技术面综合分析,字符串字段,400 字左右。必须包含四个分论点(可在字符串内用 ① ② ③ ④ 序号开头分隔,无需真实换行):①【趋势·均线】MA 排列、价格相对均线偏离度、关键支撑压力位 ②【动量·MACD/RSI/KDJ】柱形态、金死叉、超买超卖、钝化 ③【量价·量比/换手/资金流向】近20日量能特征、量价配合、主力/北向资金动向 ④【相对强度·60日】60日累计涨幅、相对沪深300 强弱、是否跑赢市场。最后一句给明确多空判断,如'综合: 看多/看空/震荡, 触发条件 XXX'",
  "fundamental_analysis": "基本面分析（150字以内）",
  "catalysts": ["催化剂1", "催化剂2"],
  "risks": ["风险1", "风险2"],
  "support_level": 12.50,
  "resistance_level": 15.80,
  "suggestion": "综合操作建议（150字以内）"
}}"""


def _clip(text: str | None, max_len: int) -> str | None:
    """安全截断字符串到指定长度，None 透传"""
    if text is None:
        return None
    s = str(text).strip()
    if not s:
        return None
    return s[:max_len]


class ReportGenerator:
    async def generate(
        self, db: AsyncSession, code: str, report_type: str = "daily"
    ) -> AnalysisReport:
        # 1. 收集数据
        context = await self._collect_context(db, code)

        # 2. 调用 AI
        raw, model_used = await self._call_llm(context, db=db)
        report_data = self._parse(raw)

        # 3. 写入数据库（stock_id 已在 _collect_context 中查过）
        stock_id = context.get("_stock_id")

        report = AnalysisReport(
            stock_id=stock_id,
            report_date=date.today(),
            report_type=report_type,
            conclusion=report_data.get("conclusion"),
            overall_signal=report_data.get("overall_signal", "neutral"),
            technical_score=report_data.get("technical_score"),
            fundamental_score=report_data.get("fundamental_score"),
            industry_inflection=_clip(report_data.get("industry_inflection"), 160),
            external_disruption=_clip(report_data.get("external_disruption"), 160),
            # action_suggestion 优先取新字段，fallback 到旧 suggestion，保证向后兼容
            action_suggestion=_clip(
                report_data.get("action_suggestion") or report_data.get("suggestion"),
                240,
            ),
            full_report=report_data,
            model_used=model_used,
        )
        db.add(report)
        await db.flush()
        return report

    async def _populate_tech_context(
        self, db: AsyncSession, code: str, stock_id: int | None, ctx: dict
    ) -> None:
        """聚合技术面上下文 — 基础(MA/MACD/RSI/KDJ/布林) + 扩展(量比/动量/相对强度/资金流向)"""
        from datetime import date as _date, timedelta as _td
        from sqlalchemy import select as _select
        from app.models.kline import StockDailyKline, StockTechnicalIndicator
        from app.services.kline_service import get_indicators

        # ── 基础指标(沿用旧逻辑,但更细化) ───────────────────────
        indicators = await get_indicators(db, code, days=80)  # 拿 80 天用于 60d 动量
        if not indicators:
            raise RuntimeError("无技术指标数据")

        latest = indicators[-1]
        # 兼容: indicators 是 dict list(get_indicators 返回 IndicatorRead.model_dump())
        def _g(d, k, default=None):
            return d.get(k) if isinstance(d, dict) else getattr(d, k, default)

        rsi14 = float(_g(latest, "rsi_14") or 0)
        ctx["rsi_14"] = round(rsi14, 2)
        ctx["rsi_status"] = (
            "超卖区" if rsi14 < 30 else
            "超买区" if rsi14 > 70 else
            "多头偏强" if rsi14 > 55 else
            "空头偏弱" if rsi14 < 45 else "中性区"
        )

        hist = float(_g(latest, "macd_hist") or 0)
        diff = float(_g(latest, "macd") or 0)
        sig = float(_g(latest, "macd_signal") or 0)
        ctx["macd_diff"] = round(diff, 4)
        ctx["macd_signal_val"] = round(sig, 4)
        ctx["macd_hist"] = round(hist, 4)
        ctx["macd_status"] = (
            "DIFF>DEA 金叉区域(红柱)" if hist > 0 else
            "DIFF<DEA 死叉区域(绿柱)" if hist < 0 else "零轴附近"
        )

        ma5 = float(_g(latest, "ma5") or 0)
        ma20 = float(_g(latest, "ma20") or 0)
        ma60 = float(_g(latest, "ma60") or 0)
        ctx["ma5"] = round(ma5, 2) if ma5 else "N/A"
        ctx["ma20"] = round(ma20, 2) if ma20 else "N/A"
        ctx["ma60"] = round(ma60, 2) if ma60 else "N/A"
        ctx["ma_status"] = (
            "多头排列(MA5>MA20>MA60)" if ma5 > ma20 > ma60 > 0 else
            "空头排列(MA5<MA20<MA60)" if 0 < ma5 < ma20 < ma60 else
            "短期偏多,中期震荡" if ma5 > ma20 else
            "短期偏空,关注支撑" if 0 < ma5 < ma20 else "震荡排列"
        )

        # KDJ
        k_v = float(_g(latest, "kdj_k") or 50)
        d_v = float(_g(latest, "kdj_d") or 50)
        j_v = float(_g(latest, "kdj_j") or 50)
        ctx["kdj_k"] = round(k_v, 1)
        ctx["kdj_d"] = round(d_v, 1)
        ctx["kdj_j"] = round(j_v, 1)
        ctx["kdj_status"] = (
            "高位钝化" if k_v > 80 and d_v > 80 else
            "低位超卖" if k_v < 20 and d_v < 20 else
            "K>D 多头格局" if k_v > d_v else "K<D 空头格局"
        )

        # 布林带
        bb_u = float(_g(latest, "bb_upper") or 0)
        bb_m = float(_g(latest, "bb_middle") or 0)
        bb_l = float(_g(latest, "bb_lower") or 0)
        if bb_u and bb_l and bb_m:
            band_w = (bb_u - bb_l) / bb_m * 100
            ctx["bb_status"] = f"上轨{bb_u:.2f}/中轨{bb_m:.2f}/下轨{bb_l:.2f}, 带宽{band_w:.1f}%"
        else:
            ctx["bb_status"] = "N/A"

        # 筹码
        if _g(latest, "chip_profit_ratio") is not None:
            ctx["profit_ratio"] = round(float(_g(latest, "chip_profit_ratio")) * 100, 1)
        if _g(latest, "chip_avg_cost") is not None:
            ctx["avg_cost"] = round(float(_g(latest, "chip_avg_cost")), 2)
        if _g(latest, "chip_concentration") is not None:
            ctx["chip_concentration"] = round(float(_g(latest, "chip_concentration")), 1)

        # ── 量价 / 动量(近 60 日 K 线) ───────────────────────────
        if stock_id is None:
            return

        since = _date.today() - _td(days=120)  # 120 日历日 ≈ 80+ 交易日,足够 60d 动量
        kline_res = await db.execute(
            _select(StockDailyKline)
            .where(StockDailyKline.stock_id == stock_id)
            .where(StockDailyKline.trade_date >= since)
            .order_by(StockDailyKline.trade_date)
        )
        klines = list(kline_res.scalars().all())

        if klines:
            closes = [float(k.close) for k in klines if k.close is not None]
            highs = [float(k.high) for k in klines if k.high is not None]
            lows = [float(k.low) for k in klines if k.low is not None]
            ctx["close_price"] = round(closes[-1], 2) if closes else "N/A"

            # 近 30 日相对位置
            if len(klines) >= 30:
                last30 = klines[-30:]
                hi30 = max(float(k.high) for k in last30 if k.high is not None)
                lo30 = min(float(k.low) for k in last30 if k.low is not None)
                cur = closes[-1]
                if hi30 > 0:
                    ctx["dist_30d_high"] = round((cur - hi30) / hi30 * 100, 2)
                if lo30 > 0:
                    ctx["dist_30d_low"] = round((cur - lo30) / lo30 * 100, 2)

            # 累计涨跌幅
            def _ret(n: int) -> float | None:
                if len(closes) <= n:
                    return None
                base = closes[-(n + 1)]
                return round((closes[-1] / base - 1) * 100, 2) if base > 0 else None

            ctx["return_5d"] = _ret(5) if _ret(5) is not None else "N/A"
            ctx["return_20d"] = _ret(20) if _ret(20) is not None else "N/A"
            r60 = _ret(60)
            ctx["return_60d"] = r60 if r60 is not None else "N/A"
            if r60 is not None:
                ctx["return_60d_label"] = (
                    "60日强势上涨" if r60 > 20 else
                    "60日温和上行" if r60 > 5 else
                    "60日震荡" if r60 > -5 else
                    "60日弱势下行" if r60 > -20 else "60日大幅下跌"
                )
            else:
                ctx["return_60d_label"] = "数据不足"

            # 近 20 日量比 / 换手率均值
            if len(klines) >= 20:
                last20 = klines[-20:]
                vrs = [float(k.volume_ratio) for k in last20 if k.volume_ratio is not None]
                if vrs:
                    ctx["avg_volume_ratio_20d"] = round(sum(vrs) / len(vrs), 2)
                tos = [float(k.turnover) for k in last20 if k.turnover is not None]
                if tos:
                    ctx["avg_turnover_20d"] = round(sum(tos) / len(tos), 2)

        # ── 60 日相对强度(对比 沪深300:000300) ───────────────────
        ctx.setdefault("relative_strength_60d", "N/A")
        ctx.setdefault("relative_strength_label", "数据不足")
        try:
            idx_res = await db.execute(_select(Stock.id).where(Stock.code == "000300"))
            idx_id = idx_res.scalar_one_or_none()
            if idx_id is not None:
                idx_kline_res = await db.execute(
                    _select(StockDailyKline.close)
                    .where(StockDailyKline.stock_id == idx_id)
                    .where(StockDailyKline.trade_date >= since)
                    .order_by(StockDailyKline.trade_date)
                )
                idx_closes = [float(c) for (c,) in idx_kline_res.all() if c is not None]
                if (
                    len(idx_closes) > 60
                    and isinstance(ctx.get("return_60d"), (int, float))
                ):
                    idx_ret = (idx_closes[-1] / idx_closes[-61] - 1) * 100
                    rs_diff = round(ctx["return_60d"] - idx_ret, 2)
                    ctx["relative_strength_60d"] = f"{rs_diff:+.2f}%"
                    ctx["relative_strength_label"] = (
                        "显著跑赢市场" if rs_diff > 10 else
                        "略跑赢市场" if rs_diff > 2 else
                        "与市场同步" if rs_diff > -2 else
                        "略跑输市场" if rs_diff > -10 else "显著跑输市场"
                    )
        except Exception as e:
            logger.debug(f"[{code}] 相对强度计算跳过: {e}")

        # ── 主力资金流向(akshare on-the-fly,失败则 N/A) ──────────
        ctx.setdefault("fund_flow_5d", "N/A")
        ctx.setdefault("fund_flow_20d", "N/A")
        ctx.setdefault("north_flow_5d", "N/A")
        try:
            import asyncio as _asyncio
            import akshare as _ak
            import pandas as _pd

            def _fetch_fund_flow():
                # market: A股 sh / sz / bj 自动判断
                if code.startswith(("6", "9")):
                    market = "sh"
                elif code.startswith(("0", "3")):
                    market = "sz"
                elif code.startswith("8"):
                    market = "bj"
                else:
                    return None
                df = _ak.stock_individual_fund_flow(stock=code, market=market)
                if df is None or df.empty:
                    return None
                return df

            df = await _asyncio.wait_for(
                _asyncio.to_thread(_fetch_fund_flow), timeout=8.0
            )
            if df is not None and not df.empty:
                # 列名: '日期' '主力净流入-净额'
                main_col = next(
                    (c for c in df.columns if "主力净流入" in str(c) and "净额" in str(c)),
                    None,
                )
                if main_col:
                    df = df.sort_values("日期")
                    sums5 = df[main_col].tail(5).sum() / 1e8
                    sums20 = df[main_col].tail(20).sum() / 1e8
                    ctx["fund_flow_5d"] = round(float(sums5), 2)
                    ctx["fund_flow_20d"] = round(float(sums20), 2)
        except Exception as e:
            logger.debug(f"[{code}] 资金流向获取跳过: {e}")

    async def _collect_context(self, db: AsyncSession, code: str) -> dict:
        from app.services.fundamental_service import get_fundamental
        from app.services.kline_service import get_indicators
        from app.services.news_service import get_stock_news

        ctx: dict = {"code": code, "name": code, "_stock_id": None}

        # 股票名称 + ID（一次查询，后续事件查询和报告写入复用）
        stock_row = await db.execute(
            select(Stock.id, Stock.name).where(Stock.code == code)
        )
        stock_record = stock_row.one_or_none()
        stock_id: int | None = None
        if stock_record:
            stock_id, name = stock_record
            ctx["name"] = name
            ctx["_stock_id"] = stock_id

        # 基本面（2026/2027 预测）
        try:
            fundamental = await get_fundamental(db, code)
            ctx["pe_ttm"] = fundamental.pe_ttm or "N/A"
            ctx["pb"] = fundamental.pb or "N/A"
            ctx["roe"] = fundamental.roe or "N/A"
            forecasts = {f.forecast_year: f for f in fundamental.forecasts}
            f2026 = forecasts.get(2026)
            f2027 = forecasts.get(2027)
            ctx["net_profit_2026"] = round(f2026.net_profit_forecast / 1e8, 2) if f2026 and f2026.net_profit_forecast else "N/A"
            ctx["forward_pe_2026"] = f2026.forward_pe or "N/A" if f2026 else "N/A"
            ctx["net_profit_2027"] = round(f2027.net_profit_forecast / 1e8, 2) if f2027 and f2027.net_profit_forecast else "N/A"
            ctx["forward_pe_2027"] = f2027.forward_pe or "N/A" if f2027 else "N/A"
        except Exception as e:
            logger.warning(f"[{code}] 基本面数据获取失败: {e}")
            ctx.update({"pe_ttm": "N/A", "pb": "N/A", "roe": "N/A",
                        "net_profit_2026": "N/A", "forward_pe_2026": "N/A",
                        "net_profit_2027": "N/A", "forward_pe_2027": "N/A"})

        # 技术面 — 基础指标 + 扩展指标(2026-05 增强:量比/动量/相对强度/资金流向)
        try:
            await self._populate_tech_context(db, code, stock_id, ctx)
        except Exception as e:
            logger.warning(f"[{code}] 技术指标聚合失败: {e}")
            # 兜底所有可能用到的字段,防止 prompt format 报 KeyError
            for k in [
                "rsi_14", "rsi_status", "macd_status", "ma_status",
                "ma5", "ma20", "ma60", "macd_diff", "macd_signal_val", "macd_hist",
                "kdj_k", "kdj_d", "kdj_j", "kdj_status", "bb_status",
                "close_price", "dist_30d_high", "dist_30d_low",
                "chip_concentration",
                "avg_volume_ratio_20d", "avg_turnover_20d",
                "return_5d", "return_20d", "return_60d", "return_60d_label",
                "relative_strength_60d", "relative_strength_label",
                "fund_flow_5d", "fund_flow_20d", "north_flow_5d",
            ]:
                ctx.setdefault(k, "N/A")

        ctx.setdefault("divergence", "无明显背离信号")
        ctx.setdefault("profit_ratio", "N/A")
        ctx.setdefault("avg_cost", "N/A")

        # 资讯摘要
        try:
            news = await get_stock_news(db, code, limit=5)
            ctx["news_summary"] = "\n".join(
                f"- [{n.source}] {n.title}" for n in news
            ) or "近期无相关资讯"
        except Exception as e:
            logger.warning(f"[{code}] 资讯获取失败: {e}")
            ctx["news_summary"] = "近期无相关资讯"

        # 近 7 天事件
        ctx["events_summary"] = "近 7 天无事件"
        if stock_id is not None:
            try:
                from datetime import datetime, timedelta, timezone
                from app.models.event import StockEvent
                cutoff = datetime.now(tz=timezone.utc) - timedelta(days=7)
                event_rows = await db.execute(
                    select(StockEvent)
                    .where(StockEvent.stock_id == stock_id)
                    .where(StockEvent.triggered_at >= cutoff)
                    .order_by(StockEvent.triggered_at.desc())
                    .limit(10)
                )
                events = list(event_rows.scalars().all())
                if events:
                    ctx["events_summary"] = "\n".join(
                        f"- [{e.event_type}/{e.severity}] {e.title}" for e in events
                    )
            except Exception as e:
                logger.warning(f"[{code}] 事件获取失败: {e}")

        return ctx

    async def _call_llm(self, context: dict, db=None) -> tuple[str, str]:
        """调用 LLM，读 DB 配置优先，逐个 provider 尝试（失败时 fallback）。
        返回 (raw_text, model_used)"""
        prompt = REPORT_PROMPT.format(**context)

        async def _get(key: str) -> str:
            if db is not None:
                try:
                    from app.services.settings_service import get_effective_value
                    return await get_effective_value(db, key)
                except Exception:
                    pass
            return str(getattr(settings, key, "") or "")

        # ── DeepSeek(OpenAI-compatible) ───────────────────────────────
        try:
            ds_key = await _get("deepseek_api_key")
            ds_model = await _get("deepseek_model") or settings.deepseek_model
            ds_base_url = await _get("deepseek_base_url") or settings.deepseek_base_url
            if ds_key:
                from openai import AsyncOpenAI
                client = AsyncOpenAI(api_key=ds_key, base_url=ds_base_url)
                kwargs = {
                    "model": ds_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 3000,
                }
                if "reasoner" not in ds_model and "thinking" not in ds_model:
                    kwargs["temperature"] = 0.3
                resp = await client.chat.completions.create(**kwargs)
                return resp.choices[0].message.content or "", ds_model
        except Exception as e:
            logger.warning(f"[{context.get('code')}] DeepSeek 报告生成失败，尝试下一个: {e}")

        # ── OpenRouter ────────────────────────────────────────────────
        try:
            or_key = await _get("openrouter_api_key")
            or_model = await _get("openrouter_model") or settings.openrouter_model
            if or_key:
                from openai import AsyncOpenAI
                client = AsyncOpenAI(api_key=or_key, base_url="https://openrouter.ai/api/v1")
                resp = await client.chat.completions.create(
                    model=or_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=3000,
                )
                return resp.choices[0].message.content or "", or_model
        except Exception as e:
            logger.warning(f"[{context.get('code')}] OpenRouter 报告生成失败，尝试下一个: {e}")

        # ── OpenAI ────────────────────────────────────────────────────
        try:
            oai_key = await _get("openai_api_key")
            oai_model = await _get("openai_model") or settings.openai_model
            if oai_key:
                from openai import AsyncOpenAI
                client = AsyncOpenAI(api_key=oai_key)
                resp = await client.chat.completions.create(
                    model=oai_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=3000,
                )
                return resp.choices[0].message.content or "", oai_model
        except Exception as e:
            logger.warning(f"[{context.get('code')}] OpenAI 报告生成失败，尝试下一个: {e}")

        # ── Anthropic ─────────────────────────────────────────────────
        try:
            ant_key = await _get("anthropic_api_key")
            ant_model = await _get("anthropic_model") or settings.anthropic_model
            if ant_key:
                import anthropic
                client = anthropic.AsyncAnthropic(api_key=ant_key)
                resp = await client.messages.create(
                    model=ant_model,
                    max_tokens=3000,
                    messages=[{"role": "user", "content": prompt}],
                )
                return resp.content[0].text, ant_model
        except Exception as e:
            logger.error(f"[{context.get('code')}] Anthropic 报告生成失败: {e}")

        logger.error(f"[{context.get('code')}] 所有 LLM provider 均失败，报告无法生成")
        return "", "unknown"

    def _parse(self, raw: str) -> dict:
        if not raw:
            return {"conclusion": "数据不足，暂无分析", "overall_signal": "neutral"}
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start < 0 or end <= start:
            return {"conclusion": raw[:100], "overall_signal": "neutral"}
        chunk = raw[start:end]

        # 1) 严格模式
        try:
            return json.loads(chunk)
        except Exception as e1:
            logger.debug(f"[parse] strict json failed: {e1}; trying non-strict")

        # 2) 容错模式:LLM 常常在 string value 里输出未转义的换行/控制字符
        try:
            return json.loads(chunk, strict=False)
        except Exception as e2:
            logger.debug(f"[parse] non-strict json failed: {e2}; trying repair")

        # 3) 修复模式:把 string value 里的裸换行/制表符替换为转义形式
        repaired = []
        in_string = False
        prev = ""
        for ch in chunk:
            if ch == '"' and prev != "\\":
                in_string = not in_string
                repaired.append(ch)
            elif in_string and ch == "\n":
                repaired.append("\\n")
            elif in_string and ch == "\r":
                repaired.append("\\r")
            elif in_string and ch == "\t":
                repaired.append("\\t")
            else:
                repaired.append(ch)
            prev = ch
        try:
            return json.loads("".join(repaired), strict=False)
        except Exception as e3:
            logger.warning(f"[parse] all json modes failed: {e3}; raw preview: {raw[:300]}")
            return {"conclusion": raw[:100], "overall_signal": "neutral"}
