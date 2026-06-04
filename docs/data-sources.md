# Data Sources

This document lists the data sources currently used by MyStock. Public financial data endpoints change often, so ingestion code should keep retries, fallbacks, defensive field parsing, and useful logs.

## Market Data and Universe

| Data | Source | Code entry | Notes |
| --- | --- | --- | --- |
| A-share universe | AKShare | `stock_info_a_code_name` | Full A-share code/name list. |
| Hong Kong universe | AKShare | `stock_hk_spot_em` | HK search and universe sync. |
| A-share profile | AKShare / EastMoney wrapper | `stock_individual_info_em` | Name, industry, sector. |
| A-share daily K-line | AKShare | `stock_zh_a_hist` | Forward-adjusted daily bars. Falls back to yfinance. |
| HK daily K-line | AKShare | `stock_hk_hist` | Forward-adjusted daily bars. Falls back to yfinance. |
| A-share realtime quotes | AKShare | `stock_zh_a_spot_em` | Primary Redis quote cache source. |
| Realtime quote fallback | EastMoney direct API | `82.push2.eastmoney.com/api/qt/clist/get` | Used when AKShare spot fails. |
| Second quote fallback | Sina quote API | `hq.sinajs.cn` | Core quote fields only. |
| K-line and TTM fallback | yfinance | `yf.Ticker(...)` | Used for fallback K-line and preferred TTM metrics. |

## Fundamentals, Flows, and Calendars

| Data | Source | Code entry | Notes |
| --- | --- | --- | --- |
| TTM fundamentals | yfinance first | `Ticker.info` | PE/PB/PS, ROE, margins, growth. |
| Financial indicators | AKShare | `stock_financial_analysis_indicator` | A-share fallback metrics. |
| EastMoney financial indicators | AKShare | `stock_financial_analysis_indicator_em` | Quarterly history, revenue, parent net profit. |
| Northbound capital flow | AKShare | `stock_hsgt_hold_stock_em`, `stock_hsgt_hist_em` | Watchlist-level holdings and flow data. |
| Dragon-tiger list | AKShare | `stock_lhb_detail_em` | Filtered to watchlist stocks after close. |
| Earnings disclosure calendar | AKShare | `stock_yysj_em` | Future earnings release events. |
| Restricted-share release calendar | AKShare | `stock_restricted_release_queue_em` | Future unlock events. |
| Profit forecasts | AKShare / iFinD style THS endpoint | `stock_profit_forecast_ths` | EPS and net profit consensus forecasts. |

## Disclosures and Research

| Data | Source | Code entry | Notes |
| --- | --- | --- | --- |
| Company notices | AKShare | `stock_individual_notice_report` | Earnings reports, annual reports, insider trades, buybacks. |
| SZSE disclosure fast path | CNInfo direct API | `www.cninfo.com.cn/new/hisAnnouncement/query` | Uses `code,orgId` lookup for precise incremental fetches. |
| SZSE org map | CNInfo | `www.cninfo.com.cn/new/data/szse_stock.json` | Cached in Redis as code -> orgId. |
| Disclosure PDFs | CNInfo static assets | `static.cninfo.com.cn` | PDF prefix for CNInfo attachments. |
| Annual report PDF fallback | EastMoney notice API | `np-cnotice-stock.eastmoney.com/api/content/ann` | Resolves PDF URL by announcement `art_code`. |
| Sell-side research metadata | AKShare / EastMoney research center | `stock_research_report_em` | Title, broker, rating, EPS/PE, PDF URL. |
| Research web-search supplement | Anthropic / OpenRouter | `web_search_20250305`, OpenRouter `:online` | Supplements recent reports when AKShare coverage is incomplete. |
| Research PDF text | PDF download + PyMuPDF | `pdf_utils.py` | Extracts text, summary, and explicit target prices. |

## News and Social Feeds

| Data | Source | Code entry | Notes |
| --- | --- | --- | --- |
| Per-stock news | AKShare / EastMoney stock news | `stock_news_em(symbol=code)` | Crawled every few hours for watchlist stocks. |
| Broad stock-news wrapper | AKShare / EastMoney stock news | `stock_news_em(symbol="")` | `CailiansheCrawler` is a legacy filename; it is not a direct CLS endpoint. |
| X.com timeline | Playwright with login cookies | `x-crawler/crawler.py` | Crawls configured handles and pushes to Redis `x_pending_tweets`. |
| X.com ingestion | Redis + Celery | `consume_x_tweets` | Consumes queued tweets every 5 minutes. |
| Wallstreetcn live feed | wallstreetcn API | `api-one.wallstcn.com/apiv1/content/lives` | `WsjCrawler` exists in code, but is not currently wired into the main schedule. |

## Global Industry Metrics

| Data | Source | Code entry | Notes |
| --- | --- | --- | --- |
| 10-Q metadata | SEC EDGAR | `data.sec.gov/submissions/CIK*.json` | Currently covers NVDA, GOOGL, META, MSFT, AMZN. |
| 10-Q filing text | SEC EDGAR Archives | `www.sec.gov/Archives/edgar/data/...` | Extracts data-center, capex, and AI infrastructure passages. |

## Schedule Overview

- Realtime quotes: during market refresh windows, controlled by `QUOTE_UPDATE_INTERVAL_SECONDS`.
- Watchlist core refresh: weekdays after close.
- News sweep: every few hours.
- Disclosures: AKShare every 30 minutes, CNInfo SZSE fast path every 5 minutes.
- X.com queue consumption: every 5 minutes.
- Research reports: morning and after close.
- Northbound flow and dragon-tiger list: daily after close.
- Stock universe: weekly.
- Industry metrics: monthly.
