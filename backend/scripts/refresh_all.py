"""
全量数据刷新脚本：
1. 最新 K 线数据
2. 技术指标
3. 基本面数据
4. 筹码分布
5. AI 分析报告
6. LLM 净利润预测（若无 manual 则生成）

用法：
    uv run python scripts/refresh_all.py
"""
import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("refresh")


async def main():
    from app.core.database import AsyncSessionLocal
    from app.services.stock_service import get_all_watchlist_codes
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        codes_result = await db.execute(
            __import__("sqlalchemy", fromlist=["select"]).select(
                __import__("app.models.stock", fromlist=["Stock"]).Stock.code,
                __import__("app.models.stock", fromlist=["Stock"]).Stock.market,
                __import__("app.models.stock", fromlist=["Stock"]).Stock.name,
            ).where(
                __import__("app.models.stock", fromlist=["Stock"]).Stock.is_watchlist == True
            )
        )
        stocks = codes_result.all()

    if not stocks:
        logger.warning("自选股为空，退出")
        return

    logger.info(f"共 {len(stocks)} 只自选股: {[s.code for s in stocks]}")

    for stock in stocks:
        code, market, name = stock.code, stock.market, stock.name
        logger.info(f"\n{'='*50}\n处理 {name}（{code}）\n{'='*50}")

        async with AsyncSessionLocal() as db:

            # ─── 1. 更新 K 线 ──────────────────────────────────
            logger.info(f"[{code}] 1/6 更新 K 线...")
            try:
                from app.services.data_fetcher.akshare_fetcher import AKShareFetcher
                from app.services.kline_service import save_klines
                fetcher = AKShareFetcher()
                klines = await fetcher.fetch_daily_kline(code, market=market, days=365)
                saved = await save_klines(db, code, klines)
                await db.commit()
                logger.info(f"[{code}] K 线写入 {saved} 条")
            except Exception as e:
                logger.error(f"[{code}] K 线更新失败: {e}")
            await asyncio.sleep(0.5)

            # ─── 2. 计算技术指标 ───────────────────────────────
            logger.info(f"[{code}] 2/6 计算技术指标...")
            try:
                from app.services.analysis.technical_analyzer import TechnicalAnalyzer
                analyzer = TechnicalAnalyzer()
                saved = await analyzer.calc_and_save(db, code)
                await db.commit()
                logger.info(f"[{code}] 技术指标写入 {saved} 条")
            except Exception as e:
                logger.error(f"[{code}] 技术指标计算失败: {e}")
            await asyncio.sleep(0.5)

            # ─── 3. 更新基本面数据 ─────────────────────────────
            logger.info(f"[{code}] 3/6 更新基本面数据...")
            try:
                from app.services.fundamental_service import save_fundamental
                fundamental = await fetcher.fetch_fundamental(code, market=market)
                if fundamental:
                    await save_fundamental(db, code, fundamental)
                    await db.commit()
                    logger.info(f"[{code}] 基本面写入完成")
                else:
                    logger.warning(f"[{code}] 未获取到基本面数据")
            except Exception as e:
                logger.error(f"[{code}] 基本面更新失败: {e}")
            await asyncio.sleep(0.5)

            # ─── 4. 计算筹码分布 ───────────────────────────────
            logger.info(f"[{code}] 4/6 计算筹码分布...")
            try:
                from app.services.chip_service import calc_and_save_chip
                chip = await calc_and_save_chip(db, code)
                await db.commit()
                if chip:
                    logger.info(f"[{code}] 筹码计算完成，获利盘: {chip.profit_ratio:.1%}")
                else:
                    logger.warning(f"[{code}] 筹码计算失败（K 线不足？）")
            except Exception as e:
                logger.error(f"[{code}] 筹码计算失败: {e}")
            await asyncio.sleep(0.5)

            # ─── 5. 生成 AI 报告 ───────────────────────────────
            logger.info(f"[{code}] 5/6 生成 AI 分析报告...")
            try:
                from app.services.ai_analyzer.report_generator import ReportGenerator
                generator = ReportGenerator()
                report = await generator.generate(db, code, "daily")
                await db.commit()
                logger.info(f"[{code}] AI 报告生成完成: {report.overall_signal} | {report.conclusion}")
            except Exception as e:
                logger.error(f"[{code}] AI 报告生成失败: {e}")
            await asyncio.sleep(1.0)

            # ─── 6. LLM 净利润预测 ─────────────────────────────
            logger.info(f"[{code}] 6/6 LLM 净利润预测...")
            try:
                from sqlalchemy import select as sa_select
                from app.models.fundamental import ProfitForecast
                from app.models.stock import Stock
                r = await db.execute(sa_select(Stock.id).where(Stock.code == code))
                stock_id = r.scalar_one_or_none()
                # 只有在没有任何预测时才用 LLM 生成
                existing = await db.execute(
                    sa_select(ProfitForecast).where(
                        ProfitForecast.stock_id == stock_id,
                        ProfitForecast.forecast_year.in_([2026, 2027]),
                    )
                )
                existing_list = list(existing.scalars().all())
                if len(existing_list) < 2:
                    from app.services.ai_analyzer.forecast_generator import generate_llm_forecast
                    result = await generate_llm_forecast(db, code)
                    await db.commit()
                    logger.info(f"[{code}] LLM 预测: 2026={result.get('forecast_2026')}亿 2027={result.get('forecast_2027')}亿")
                    logger.info(f"[{code}] 理由: {result.get('reasoning', '')}")
                else:
                    logger.info(f"[{code}] 已有 {len(existing_list)} 条预测，跳过 LLM 生成")
            except Exception as e:
                logger.error(f"[{code}] LLM 预测失败: {e}")

        logger.info(f"[{code}] ✓ 全部完成")
        await asyncio.sleep(1.0)

    logger.info("\n✅ 所有股票数据刷新完毕")


if __name__ == "__main__":
    asyncio.run(main())
