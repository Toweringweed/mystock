# MyStock 数据字典（桌面 Claude / MCP 用）

> 这份文档供桌面版 Claude 在通过 PostgreSQL MCP 查询 MyStock 数据库时使用。
> 描述各表用途、关键字段、单位约定、常用查询模式。

## 安全提示

- **不要 SELECT `app_settings` 表**：里面是 API Key 等敏感配置。即使是只读账号，也避免把它们带入对话上下文。
- 所有数据是**只读**的（角色 `mystock_readonly`）；写操作（INSERT/UPDATE/DELETE）会被数据库直接拒绝。

## 单位与格式约定

| 项 | 约定 |
|----|------|
| 股票代码 | A 股 6 位（`000001`），港股带前导 0 5 位（`00700`） |
| 价格、EPS、成本 | 单位：元，`Numeric` 精确小数（避免 float 误差） |
| 涨跌幅、收益率 | 小数（如 `0.0532` 表示 +5.32%），**不是百分比** |
| 营收、净利润 | 单位：**元**（不是亿），数值范围非常大 |
| 百分位 | 0~1 浮点（如 `0.85` 表示位于 85% 分位） |
| 时间字段 | 全部带时区（`DateTime(timezone=True)`），UTC 存储 |
| 交易日期 | `Date` 类型，仅日期 |

## 表清单

### 核心：股票

#### `stocks` — 股票主表
- `id` (PK), `code`, `name`, `market`(A/HK), `industry`, `sector`
- `is_watchlist` 是否为自选股（**绝大多数查询应过滤此字段为 true**）
- `data_ready` 数据是否已就绪（新加股票回填中时为 false）

#### `stock_aliases` — 股票别名（用于资讯实体匹配）
- `stock_id` (FK), `alias`, `alias_type`（short_name/manual/...）, `weight`

#### `stock_universe` — 全量股票池（搜索用，不一定是自选股）

### 行情与指标

#### `stock_daily_kline` — 日 K 线
- `(stock_id, trade_date)` 唯一
- `open / high / low / close / volume / amount / turnover_rate / pct_chg`

#### `stock_technical_indicators` — 技术指标（每日一行）
- `ma5 / ma10 / ma20 / ma60`
- `macd / macd_signal / macd_hist`（MACD 三线）
- `rsi_6 / rsi_14 / rsi_24`
- `kdj_k / kdj_d / kdj_j`
- `boll_upper / boll_middle / boll_lower`
- `obv`
- `chip_profit_ratio`（获利盘比例 0~1）, `chip_avg_cost`（平均成本）

#### `divergence_signals` — 背离信号
- `signal_type`：`MACD_BULL` / `MACD_BEAR` / `RSI_BULL` / `RSI_BEAR`
- `confidence` 0~1，`is_confirmed` 事后是否被验证

#### `chip_distributions` — 筹码分布快照
- `price_ranges` (JSONB): `[{price_low, price_high, chip_pct}]`
- `profit_ratio / avg_cost / concentration`

### 基本面

#### `stock_fundamentals` — 财务数据
- `(stock_id, period, period_type)` 唯一，`period_type` ∈ `quarterly/annual/ttm`
- `pe_ttm / pb / roe / revenue / net_profit / eps`
- `revenue_yoy / profit_yoy`（同比增速，小数）
- `gross_margin / net_margin / debt_ratio / current_ratio`

#### `profit_forecasts` — 机构盈利预测
- `(stock_id, forecast_year, source)` 唯一
- `eps_forecast / net_profit_forecast / revenue_forecast`（单位：元）
- `forward_pe`（远期 PE）

### AI 分析

#### `daily_summaries` — L1 摘要（每日 Haiku 批量生成）
- `(stock_id, summary_date)` 唯一
- `label`（5 字标签，如"技术回调"）
- `one_liner`（一句话结论，≤200 字）
- `signal` ∈ `bullish/bearish/neutral`
- `label_changed` 与昨日相比是否变化
- `payload` 原始 LLM 输出（JSONB）

#### `analysis_reports` — L2 深度报告（Sonnet，事件触发）
- `report_date`, `report_type` ∈ `daily/event_driven/initial`
- `conclusion`（一句话）, `overall_signal`
- `technical_score / fundamental_score`（1~10）
- `full_report` (JSONB)：完整结构化报告，字段如 `technical_analysis / fundamental_analysis / catalysts / risks / support_level / resistance_level / suggestion`
- `model_used` 实际使用的模型名

#### `stock_events` — 事件流水
- `event_type`：`MACD_DIVERGENCE_NEW / VOLUME_SPIKE / PE_EXTREME_LOW / PE_EXTREME_HIGH / URGENT_NEWS / AI_SIGNAL_FLIP`
- `severity` ∈ `low/medium/high`
- `dedup_key` + `(stock_id, event_type)` 唯一（保证幂等）
- `triggered_at`（事件触发时间）, `notified_at`（推送时间，NULL=未推送）
- `payload`：事件具体数据（如背离信号 ID、PE 分位数等）

### 资讯

#### `industry_news` — 资讯主表
- `title / content / summary / source`
- `published_at` 发布时间（来源时间）, `crawled_at` 抓取时间
- `simhash` 64 位指纹（跨源去重）
- `direction` ∈ `bullish/bearish/neutral`（LLM 判定）
- `urgency` ∈ `urgent/important/info`
- `importance_score` 综合分 0~1
- `sentiment` ∈ `positive/negative/neutral`
- `processed_at` 流水线处理时间（NULL=待处理）

#### `news_stock_relations` — 资讯-股票关联
- `(news_id, stock_id)` 唯一，`relevance` 0~1

### 资金流向

#### `stock_capital_flows` — 北上资金日度
- `(stock_id, trade_date)` 唯一
- `net_inflow`：当日净流入（元；正=流入，负=流出）
- `shareholding_ratio`：持股占流通比 %
- `shareholding_volume`：累计持股数（股）

#### `stock_lhb` — 龙虎榜
- `(stock_id, trade_date)` 唯一
- `reason / buy_amount / sell_amount / net_amount / change_pct`
- `top_buyers / top_sellers`：JSONB 席位列表

#### `insider_trades` — 减持/增持（LLM 从公告抽取）
- `(stock_id, ann_date, trade_type, holder_name)` 唯一
- `trade_type` ∈ {reduce, increase}
- `shares / amount / pct_of_total / pct_before / pct_after`
- `price_low / price_high`：交易价格区间
- `source_news_id`：FK 到 industry_news

### 日历

#### `calendar_events` — 财报日 / 解禁日 / 自定义
- `(stock_id, event_type, event_date)` 唯一
- `event_type` ∈ {earnings_release, restricted_release, custom, macro, industry_conference}
- `payload` (JSONB)：解禁含 shares / market_value / ratio
- `stock_id` 可空（全市场事件）

### 行业景气

#### `industry_metrics` — 半导体/AI/算力 关键指标
- `(metric_name, period, source)` 唯一
- `metric_name`：如 `nvda_datacenter_revenue / googl_capex_actual / msft_capex_guidance_full_year`
- `period`：YYYYQn 或 YYYY-MM
- `value` + `unit` (`USD_billion / pct / count`)
- `source` ∈ {10-Q, earnings_call, press_release}
- `extracted_quote`：LLM 提取的原文摘录

### 业务分部(SOTP 估值)

#### `business_segments` — 分部营收/利润拆解
- `(stock_id, report_period, segment_name)` 唯一
- `category` ∈ {`core`, `legacy`, `growth`, `option`} — **决定该分部应享受的 PE 锚**
- `revenue` (元) / `revenue_pct` (%) / `profit` / `profit_pct`
- `gross_margin` / `growth_yoy`
- `description` — 1-2 句业务说明
- `extracted_from` — 来源 PDF
- 来源:LLM 从年报"分部信息/经营情况分析/营业收入构成"章节提取

**SOTP 拆解规则**:
- `core` (主业,占比 > 30%):周期股 PE 8-12,价值股 PE 12-18
- `legacy` (海外并表):欧洲工业股 PE 12-15,港股蓝筹 PE 8-12
- `growth` (已落地新业务):AI 算力链 PE 20-25,国产替代 PE 25-35
- `option` (未量产/期权):**不计入 SOTP 加权**,仅讨论附加溢价
- 合理 PE = Σ(各 core/legacy/growth PE × 利润占比);profit_pct 缺失时降级用 revenue_pct
- 判定:实际 PE / SOTP 合理 PE > 1.3 → **故事溢价显著**

### 估值视图

#### `v_stock_peg` (VIEW)
- `peg_ttm = pe_ttm / profit_yoy`
- `peg_forward = (next year forward_pe) / profit_yoy`
- `forward_pe_next`：下一年远期 PE

### 供应链

#### `supply_chains` — 供应链关系
- `relation_type` ∈ `upstream / downstream / competitor`
- `company_name / company_code`（如是上市公司，code 非空）
- `percentage`（占比 %）, `importance` ∈ `high/medium/low`

## 常用查询示例

### 1. 我自选股里 PE-TTM 最低的 5 只 + 最近 AI 报告

```sql
SELECT
  s.code, s.name,
  f.pe_ttm,
  r.conclusion, r.overall_signal, r.report_date
FROM stocks s
LEFT JOIN LATERAL (
  SELECT pe_ttm FROM stock_fundamentals
  WHERE stock_id = s.id AND period_type = 'ttm'
  ORDER BY updated_at DESC LIMIT 1
) f ON true
LEFT JOIN LATERAL (
  SELECT conclusion, overall_signal, report_date FROM analysis_reports
  WHERE stock_id = s.id ORDER BY report_date DESC LIMIT 1
) r ON true
WHERE s.is_watchlist = true AND f.pe_ttm IS NOT NULL
ORDER BY f.pe_ttm ASC
LIMIT 5;
```

### 2. 今天触发的所有事件（按 severity 倒序）

```sql
SELECT s.code, s.name, e.event_type, e.severity, e.title, e.payload
FROM stock_events e
JOIN stocks s ON s.id = e.stock_id
WHERE e.triggered_at::date = CURRENT_DATE
ORDER BY
  CASE e.severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
  e.triggered_at DESC;
```

### 3. 近 30 天 AI 信号方向变化次数最多的股票

```sql
SELECT s.code, s.name, COUNT(*) AS flip_count
FROM daily_summaries d
JOIN stocks s ON s.id = d.stock_id
WHERE d.summary_date >= CURRENT_DATE - INTERVAL '30 days'
  AND d.label_changed = true
GROUP BY s.code, s.name
ORDER BY flip_count DESC
LIMIT 10;
```

### 4. 当前出现 MACD 底背离 + PE 处于近 5 年 30% 分位以下的股票

```sql
WITH recent_div AS (
  SELECT DISTINCT stock_id FROM divergence_signals
  WHERE signal_type = 'MACD_BULL'
    AND detected_date >= CURRENT_DATE - INTERVAL '7 days'
),
pe_history AS (
  SELECT stock_id, pe_ttm,
    PERCENT_RANK() OVER (PARTITION BY stock_id ORDER BY pe_ttm) AS pct
  FROM stock_fundamentals
  WHERE period_type = 'ttm' AND pe_ttm IS NOT NULL
    AND updated_at >= CURRENT_DATE - INTERVAL '5 years'
)
SELECT s.code, s.name, ph.pe_ttm, ROUND((ph.pct * 100)::numeric, 1) AS pe_percentile
FROM stocks s
JOIN recent_div d ON d.stock_id = s.id
JOIN pe_history ph ON ph.stock_id = s.id
WHERE s.is_watchlist = true AND ph.pct < 0.3
ORDER BY ph.pct ASC;
```

### 5. 单只股票最近 7 天的事件 + 资讯 + AI 报告（综合视图）

```sql
-- 替换 :code 为目标股票代码，例如 '600519'
WITH s AS (SELECT id FROM stocks WHERE code = :code)
SELECT 'event'  AS kind, e.event_type AS type, e.title, e.triggered_at AS ts
  FROM stock_events e WHERE e.stock_id = (SELECT id FROM s)
    AND e.triggered_at >= now() - INTERVAL '7 days'
UNION ALL
SELECT 'news'   AS kind, n.urgency, n.title, n.published_at AS ts
  FROM industry_news n
  JOIN news_stock_relations r ON r.news_id = n.id
  WHERE r.stock_id = (SELECT id FROM s)
    AND n.published_at >= now() - INTERVAL '7 days'
UNION ALL
SELECT 'report' AS kind, ar.report_type, ar.conclusion, ar.generated_at AS ts
  FROM analysis_reports ar WHERE ar.stock_id = (SELECT id FROM s)
    AND ar.generated_at >= now() - INTERVAL '7 days'
ORDER BY ts DESC;
```

### 6. 近 5 日北上资金净流入排名前 10 的自选股

```sql
SELECT
  s.code, s.name,
  ROUND(SUM(cf.net_inflow)::numeric / 1e8, 2) AS net_inflow_5d_yi,
  ROUND(AVG(cf.shareholding_ratio)::numeric, 3) AS avg_shareholding_pct
FROM stocks s
JOIN stock_capital_flows cf ON cf.stock_id = s.id
WHERE s.is_watchlist = true
  AND cf.trade_date >= CURRENT_DATE - INTERVAL '5 days'
GROUP BY s.code, s.name
ORDER BY net_inflow_5d_yi DESC
LIMIT 10;
```

### 7. 未来 14 天有解禁/财报披露的自选股

```sql
SELECT s.code, s.name, ce.event_type, ce.event_date, ce.title,
       ce.payload->>'market_value' AS market_value
FROM calendar_events ce
JOIN stocks s ON s.id = ce.stock_id
WHERE s.is_watchlist = true
  AND ce.event_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '14 days'
ORDER BY ce.event_date ASC;
```

### 8. 对比 NVDA 与 4 大 CSP 最近一期 capex / 数据中心收入

```sql
SELECT metric_name, period, value, unit, extracted_quote
FROM industry_metrics
WHERE metric_name LIKE '%capex%' OR metric_name LIKE '%datacenter_revenue%'
ORDER BY period DESC, metric_name
LIMIT 20;
```

### 9. PEG 估值排行（自选股）

```sql
SELECT s.code, s.name,
  ROUND(v.pe_ttm::numeric, 2) AS pe_ttm,
  ROUND(v.profit_yoy::numeric, 2) AS profit_yoy_pct,
  ROUND(v.peg_ttm::numeric, 3) AS peg_ttm,
  ROUND(v.peg_forward::numeric, 3) AS peg_forward
FROM stocks s
JOIN v_stock_peg v ON v.stock_id = s.id
WHERE s.is_watchlist = true AND v.peg_ttm IS NOT NULL
ORDER BY v.peg_ttm ASC
LIMIT 20;
```

### 10. 供应链上下游公司中也是自选股的，最近有什么事件

```sql
SELECT
  s_target.code AS target_code, s_target.name AS target_name,
  sc.relation_type, s_related.code AS related_code, s_related.name AS related_name,
  e.event_type, e.title, e.triggered_at
FROM supply_chains sc
JOIN stocks s_target  ON s_target.id  = sc.stock_id
JOIN stocks s_related ON s_related.code = sc.company_code
JOIN stock_events e   ON e.stock_id = s_related.id
WHERE s_target.is_watchlist = true
  AND e.triggered_at >= now() - INTERVAL '3 days'
ORDER BY e.triggered_at DESC;
```

## 桌面 Claude 使用习惯

- 报告 JSONB 字段（`analysis_reports.full_report` / `daily_summaries.payload` / `stock_events.payload`）用 `->>` 取文本、`->` 取 JSON。例：`full_report->>'suggestion'`
- A 股代码 `000001` 平安银行 vs `601318` 中国平安——区分清楚
- 涉及估值时，提醒用户："PE 分位是基于本地 K 线 × 最新 EPS-TTM 反推的近似值，精确比较请用季度切换 EPS"
- 时间筛选优先用 `triggered_at::date = CURRENT_DATE` 而非 `BETWEEN`（更易读）
