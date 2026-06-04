"""技术指标计算引擎（pandas-ta）"""
import logging

import pandas as pd
import pandas_ta as ta
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class TechnicalAnalyzer:
    """基于 pandas-ta 计算技术指标，写入数据库"""

    async def calc_and_save(self, db: AsyncSession, code: str) -> int:
        from app.services.chip_service import calc_and_save_chip
        from app.services.divergence_service import calc_and_save_divergence
        from app.services.kline_service import get_kline_dataframe, save_indicators

        df = await get_kline_dataframe(db, code, days=300)
        if df.empty or len(df) < 30:
            logger.warning(f"[{code}] K线数据不足，跳过指标计算")
            return 0

        indicators = self._calculate(df)
        saved = await save_indicators(db, code, indicators)

        # 同步计算筹码和背离（不影响指标写入）
        try:
            await calc_and_save_chip(db, code)
        except Exception as e:
            logger.warning(f"[{code}] 筹码计算跳过: {e}")
        try:
            await calc_and_save_divergence(db, code)
        except Exception as e:
            logger.warning(f"[{code}] 背离计算跳过: {e}")

        return saved

    def _calculate(self, df: pd.DataFrame) -> list[dict]:
        """计算所有技术指标，返回标准化列表"""
        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        # 移动平均
        ma5 = ta.sma(close, length=5)
        ma10 = ta.sma(close, length=10)
        ma20 = ta.sma(close, length=20)
        ma60 = ta.sma(close, length=60)

        # MACD (12, 26, 9)
        macd_df = ta.macd(close, fast=12, slow=26, signal=9)

        # RSI
        rsi6 = ta.rsi(close, length=6)
        rsi14 = ta.rsi(close, length=14)
        rsi24 = ta.rsi(close, length=24)

        # KDJ (9, 3, 3) — pandas-ta 用 stoch 近似
        stoch = ta.stoch(high, low, close, k=9, d=3, smooth_k=3)

        # 布林带 (20, 2)
        bbands = ta.bbands(close, length=20, std=2)

        # OBV
        obv = ta.obv(close, volume)

        results = []
        for idx, trade_date in enumerate(df.index.date):
            def _v(series, i):
                if series is None or i >= len(series):
                    return None
                val = series.iloc[i]
                return None if pd.isna(val) else float(val)

            # MACD 列名
            macd_val = macd_signal = macd_hist = None
            if macd_df is not None:
                cols = macd_df.columns.tolist()
                macd_col = next((c for c in cols if c.startswith("MACD_")), None)
                sig_col = next((c for c in cols if c.startswith("MACDs_")), None)
                hist_col = next((c for c in cols if c.startswith("MACDh_")), None)
                if macd_col:
                    v = macd_df[macd_col].iloc[idx]
                    macd_val = None if pd.isna(v) else float(v)
                if sig_col:
                    v = macd_df[sig_col].iloc[idx]
                    macd_signal = None if pd.isna(v) else float(v)
                if hist_col:
                    v = macd_df[hist_col].iloc[idx]
                    macd_hist = None if pd.isna(v) else float(v)

            # KDJ
            kdj_k = kdj_d = kdj_j = None
            if stoch is not None and len(stoch.columns) >= 2:
                k_col, d_col = stoch.columns[0], stoch.columns[1]
                kv = stoch[k_col].iloc[idx]
                dv = stoch[d_col].iloc[idx]
                kdj_k = None if pd.isna(kv) else float(kv)
                kdj_d = None if pd.isna(dv) else float(dv)
                if kdj_k is not None and kdj_d is not None:
                    kdj_j = 3 * kdj_k - 2 * kdj_d

            # 布林带
            bb_upper = bb_middle = bb_lower = None
            if bbands is not None:
                for col in bbands.columns:
                    v = bbands[col].iloc[idx]
                    fv = None if pd.isna(v) else float(v)
                    if "BBU" in col:
                        bb_upper = fv
                    elif "BBM" in col:
                        bb_middle = fv
                    elif "BBL" in col:
                        bb_lower = fv

            results.append({
                "trade_date": trade_date,
                "ma5": _v(ma5, idx),
                "ma10": _v(ma10, idx),
                "ma20": _v(ma20, idx),
                "ma60": _v(ma60, idx),
                "macd": macd_val,
                "macd_signal": macd_signal,
                "macd_hist": macd_hist,
                "rsi_6": _v(rsi6, idx),
                "rsi_14": _v(rsi14, idx),
                "rsi_24": _v(rsi24, idx),
                "kdj_k": kdj_k,
                "kdj_d": kdj_d,
                "kdj_j": kdj_j,
                "bb_upper": bb_upper,
                "bb_middle": bb_middle,
                "bb_lower": bb_lower,
                "obv": int(_v(obv, idx) or 0) or None,
            })

        return results
