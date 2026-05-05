# 导入所有模型，确保 Alembic 能发现所有表
from app.models.stock import Stock
from app.models.kline import StockDailyKline, StockTechnicalIndicator
from app.models.fundamental import StockFundamental, ProfitForecast
from app.models.analysis import DivergenceSignal, ChipDistribution, AnalysisReport
from app.models.news import IndustryNews, NewsStockRelation
from app.models.supply_chain import SupplyChain
from app.models.stock_meta import StockNote
from app.models.app_setting import AppSetting
from app.models.stock_universe import StockUniverse
from app.models.stock_alias import StockAlias
from app.models.event import StockEvent
from app.models.daily_summary import DailySummary
from app.models.capital_flow import StockCapitalFlow
from app.models.lhb import StockLhb
from app.models.insider_trade import InsiderTrade
from app.models.calendar_event import CalendarEvent
from app.models.industry_metric import IndustryMetric
from app.models.business_segment import BusinessSegment
from app.models.tag import Tag, StockTag
from app.models.research import ResearchReportMeta
from app.models.analyst_report import AnalystReport
from app.models.earnings_surprise import EarningsSurprise
from app.models.estimate_revision import EstimateRevision
from app.models.backtest_infra import (
    StockDailyFactor, IndustryDailyIndex, QuarterlyFinancialsHistory,
    InstitutionMetadata, BacktestSnapshot,
)
from app.models.target_price_realtime import StockTargetPriceRealtime

__all__ = [
    "Stock",
    "StockDailyKline",
    "StockTechnicalIndicator",
    "StockFundamental",
    "ProfitForecast",
    "DivergenceSignal",
    "ChipDistribution",
    "AnalysisReport",
    "IndustryNews",
    "NewsStockRelation",
    "SupplyChain",
    "StockNote",
    "AppSetting",
    "StockUniverse",
    "StockAlias",
    "StockEvent",
    "DailySummary",
    "StockCapitalFlow",
    "StockLhb",
    "InsiderTrade",
    "CalendarEvent",
    "IndustryMetric",
    "BusinessSegment",
    "Tag",
    "StockTag",
    "ResearchReportMeta",
    "AnalystReport",
    "EarningsSurprise",
    "EstimateRevision",
    "StockDailyFactor",
    "IndustryDailyIndex",
    "QuarterlyFinancialsHistory",
    "InstitutionMetadata",
    "BacktestSnapshot",
    "StockTargetPriceRealtime",
]
