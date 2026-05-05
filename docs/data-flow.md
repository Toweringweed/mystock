# MyStock 数据流单页图

> 一张图看清"数据从哪来 → 怎么处理 → 给谁看"。Mermaid 渲染，GitHub / VSCode / Claude 都支持。

## 全景：从数据源到用户的完整链路

```mermaid
flowchart LR
    %% ─────────── 数据源层 ───────────
    subgraph SRC["📥 数据源"]
        direction TB
        AK[AKShare<br/>K线/财务/资讯]
        TS[Tushare Pro<br/>盈利预测]
        FT[富途 OpenD<br/>港股实时]
        WSJ[wsj_cn]
        CLS[财联社]
        DISC[disclosure_em<br/>财报公告]
        EM[eastmoney<br/>个股资讯]
    end

    %% ─────────── 采集层 ───────────
    subgraph FETCH["🔄 采集 (Celery Beat)"]
        direction TB
        T_QUOTE["update-quotes<br/>每15s · 交易时段"]
        T_FUND["update-fundamentals<br/>每日 09:00"]
        T_KLINE["backfill_stock_data<br/>事件触发"]
        T_NEWS["crawl-news<br/>每3h"]
        T_DISC["crawl-disclosures<br/>每30m"]
        T_UNI["sync-stock-universe<br/>周日 02:00"]
    end

    %% ─────────── 存储层 ───────────
    subgraph STORE["🗄️ 存储"]
        direction TB
        subgraph PG[(PostgreSQL)]
            direction TB
            PG_M["stocks / aliases / universe"]
            PG_K["stock_daily_kline<br/>stock_technical_indicators<br/>chip_distributions<br/>divergence_signals"]
            PG_F["stock_fundamentals<br/>profit_forecasts"]
            PG_N["industry_news<br/>news_stock_relations"]
            PG_E["⭐ stock_events<br/>⭐ daily_summaries<br/>analysis_reports"]
            PG_S["supply_chains"]
            PG_CFG["app_settings"]
        end
        subgraph RD[(Redis)]
            RD_Q["行情 60s 缓存"]
            RD_KW["关键词词库 1h"]
            RD_QUEUE["事件/资讯<br/>聚合队列"]
        end
    end

    %% ─────────── 处理 / 分析层 ───────────
    subgraph PROC["⚙️ 处理 & 分析"]
        direction TB
        T_CALC["calc-indicators<br/>每日 16:00"]
        T_NEWSPROC["process-pending-news<br/>每5m"]
        T_EVENT["⭐ run-event-detection<br/>每日 16:15"]
        T_SUM["⭐ generate-daily-summaries<br/>每日 16:30 · Haiku"]
        T_RPT["⭐ generate-reports-for-events<br/>每日 16:45 · Sonnet"]
    end

    %% ─────────── 推送 / 交互层 ───────────
    subgraph OUT["📢 输出"]
        direction TB
        T_DISPATCH["⭐ dispatch-event-queue<br/>每整点"]
        T_DAILY["dispatch-daily-summary<br/>每日 08:00"]
        WX[企业微信<br/>群机器人]
        WEB[Next.js 前端<br/>Dashboard / 详情页]
        DESKTOP[桌面 Claude<br/>+ MCP postgres]
    end

    %% ─────────── 数据流 ───────────
    AK --> T_QUOTE & T_FUND & T_KLINE & T_DISC & T_NEWS
    TS --> T_FUND
    FT --> T_QUOTE
    WSJ & CLS & EM --> T_NEWS
    DISC --> T_DISC
    AK -.全量股票池.-> T_UNI

    T_QUOTE --> RD_Q
    T_FUND --> PG_F
    T_KLINE --> PG_K
    T_NEWS --> PG_N
    T_DISC --> PG_N
    T_UNI --> PG_M

    PG_K --> T_CALC --> PG_K
    PG_N --> T_NEWSPROC
    T_NEWSPROC -- "Haiku 打分" --> PG_N
    T_NEWSPROC -- "urgent 立即" --> WX

    PG_K & PG_F & PG_N --> T_EVENT
    T_EVENT --> PG_E
    T_EVENT -- "high 立即" --> WX
    T_EVENT -- "medium 入队" --> RD_QUEUE

    PG_K & PG_F & PG_E --> T_SUM
    T_SUM -- "L1 Haiku 批量" --> PG_E
    T_SUM -- "AI_SIGNAL_FLIP" --> WX

    PG_E --> T_RPT
    T_RPT -- "L2 Sonnet 4.6" --> PG_E

    RD_QUEUE --> T_DISPATCH --> WX
    PG_N --> T_DAILY --> WX

    PG_M & PG_K & PG_F & PG_N & PG_E & PG_S --> WEB
    PG_M & PG_K & PG_F & PG_N & PG_E & PG_S -. "只读 MCP" .-> DESKTOP

    %% ─────────── 样式 ───────────
    classDef source fill:#e3f2fd,stroke:#1976d2
    classDef task fill:#fff3e0,stroke:#f57c00
    classDef store fill:#f3e5f5,stroke:#7b1fa2
    classDef ai fill:#fce4ec,stroke:#c2185b
    classDef out fill:#e8f5e9,stroke:#388e3c

    class AK,TS,FT,WSJ,CLS,DISC,EM source
    class T_QUOTE,T_FUND,T_KLINE,T_NEWS,T_DISC,T_UNI,T_CALC,T_NEWSPROC,T_DISPATCH,T_DAILY task
    class T_EVENT,T_SUM,T_RPT ai
    class WX,WEB,DESKTOP out
```

⭐ = 本轮新增的事件总线 + AI 分级路径

---

## 一日时序（24h 调度甘特）

```mermaid
gantt
    title MyStock 自动调度时序（Asia/Shanghai）
    dateFormat HH:mm
    axisFormat %H:%M

    section 推送
    daily-summary 资讯摘要      :08:00, 1m
    dispatch-event 整点聚合     :crit, 09:00, 1m
    dispatch-event 整点聚合     :crit, 10:00, 1m

    section 数据采集
    update-fundamentals         :09:00, 30m
    update-quotes (每15s)       :active, 09:30, 5h30m
    crawl-news (每3h)           :09:00, 5m
    crawl-news                  :12:00, 5m
    crawl-news                  :15:00, 5m
    crawl-disclosures (每30m)   :09:30, 1m
    crawl-disclosures           :10:00, 1m
    process-pending-news        :09:05, 1m
    process-pending-news        :09:10, 1m
    process-pending-news        :09:15, 1m

    section 计算
    calc-indicators-daily       :16:00, 10m

    section AI 分析（核心链路）
    run-event-detection         :crit, 16:15, 5m
    generate-daily-summaries L1 :crit, 16:30, 5m
    generate-reports L2 Sonnet  :crit, 16:45, 15m
```

---

## 添加自选股的链路（事件驱动）

```mermaid
sequenceDiagram
    autonumber
    participant U as 用户
    participant FE as Next.js 前端
    participant API as FastAPI
    participant DB as PostgreSQL
    participant CW as Celery Worker
    participant AKShare as 数据源
    participant LLM as Claude

    U->>FE: 搜索 + 添加
    FE->>API: POST /stocks (code)
    API->>DB: stocks.is_watchlist=true<br/>data_ready=false
    API-->>FE: 200 OK
    API->>CW: backfill_stock_data.delay()

    rect rgb(255, 243, 224)
        Note over CW: 异步回填（用户不等待）
        CW->>AKShare: 拉 200 天 K 线
        CW->>DB: 写 stock_daily_kline
        CW->>CW: pandas-ta 算指标 / 背离 / 筹码
        CW->>DB: 写 indicators / signals / chips
        CW->>AKShare: 拉财务 + PE
        CW->>DB: 写 stock_fundamentals
        CW->>DB: data_ready=true
    end

    par 并行触发
        CW->>CW: generate_report_task("initial")
        CW->>LLM: Sonnet 4.6 完整报告
        LLM-->>CW: JSON
        CW->>DB: 写 analysis_reports
    and A股触发
        CW->>CW: extract_supply_chain_task
        CW->>AKShare: 下载年报 PDF
        CW->>LLM: Sonnet 提取上下游
        LLM-->>CW: 结构化清单
        CW->>DB: 写 supply_chains
    end

    Note over FE,DB: 后续 SWR 轮询 → 数据逐步解锁
```

---

## 资讯流水线（process-pending-news 内部）

```mermaid
flowchart TD
    START["新资讯入库<br/>processed_at = NULL"] --> DEDUP{SimHash<br/>近24h相似度<br/>≤3?}
    DEDUP -- "是" --> SKIP["标记 processed<br/>不推送"]
    DEDUP -- "否" --> ENTITY["实体匹配<br/>关键词 → stock_id"]

    ENTITY --> RULE["规则打分<br/>公告类型×0.4<br/>+源权威×0.2<br/>+时敏×0.2<br/>+数字×0.2"]

    RULE -- "score < 0.3" --> DROP["丢弃<br/>不进 LLM<br/>~过滤 90% 噪音"]
    RULE -- "score ≥ 0.3" --> LLM_BATCH["批 8 条进 LLM<br/>Claude Haiku"]

    LLM_BATCH --> LLM_OUT["LLM 输出<br/>direction / strength<br/>sentiment / summary<br/>per-stock relevance"]

    LLM_OUT --> SCORE["综合分<br/>= rule×0.4 + (llm/5)×0.6"]
    SCORE --> CLASSIFY{紧急级判定}

    CLASSIFY -- "urgent<br/>≥0.8 或紧急词" --> WX1["立即推送企业微信"]
    CLASSIFY -- "important<br/>0.5~0.8" --> Q["Redis SortedSet<br/>整点聚合"]
    CLASSIFY -- "info<br/><0.5" --> ST["仅入库<br/>每日 8:00 摘要"]

    classDef drop fill:#ffebee,stroke:#c62828
    classDef pass fill:#e8f5e9,stroke:#388e3c
    classDef wait fill:#fff3e0,stroke:#f57c00

    class DROP,SKIP drop
    class WX1 pass
    class Q,ST wait
```

---

## 事件总线（5 类异常 → 推送路由）

```mermaid
flowchart LR
    subgraph DETECT["🔍 detector"]
        T1["MACD_DIVERGENCE_NEW<br/>当日新增背离"]
        T2["VOLUME_SPIKE<br/>量比>3"]
        V1["PE_EXTREME_LOW<br/>PE<5%分位"]
        V2["PE_EXTREME_HIGH<br/>PE>95%分位"]
        N1["URGENT_NEWS<br/>命中 urgency=urgent"]
        S1["AI_SIGNAL_FLIP<br/>信号方向翻转"]
    end

    EV[(stock_events 表<br/>幂等键<br/>stock_id+type+dedup_key)]

    T1 & T2 & V1 & V2 & N1 & S1 --> EV

    EV --> SEV{severity}
    SEV -- "high" --> IMM["立即<br/>dispatch_event"]
    SEV -- "medium" --> REDIS[(Redis SortedSet<br/>事件队列)]
    SEV -- "low" --> NOOP["仅入库"]

    REDIS --> HOURLY["整点聚合<br/>最多30条/次"]

    IMM --> WX[企业微信<br/>群机器人]
    HOURLY --> WX

    EV -. "L2 触发条件" .-> RPT["generate-reports-for-events<br/>16:45 · Sonnet 4.6"]
    EV -. "近 7 天上下文" .-> SUM["generate-daily-summaries<br/>16:30 · Haiku"]
    EV -. "近 7 天上下文" .-> RPT

    classDef high fill:#ffebee,stroke:#c62828
    classDef med fill:#fff3e0,stroke:#f57c00
    classDef low fill:#f3e5f5,stroke:#7b1fa2

    class N1,S1,IMM high
    class T1,T2,V1,V2,REDIS,HOURLY med
    class NOOP low
```

---

## AI 分层与成本分布

```mermaid
flowchart TB
    subgraph AI["🤖 AI 内容生成"]
        direction TB
        L0["L0 资讯打分<br/>Haiku · 批 8 条<br/>每 5 分钟"]
        L1["L1 每日摘要<br/>Haiku · 批 10 只<br/>每日 16:30 · 5 次调用"]
        L2["L2 深度报告<br/>Sonnet 4.6<br/>每日 16:45 · 5-15 只"]
        L3["L3 交互分析<br/>桌面 Claude + MCP<br/>用户主动"]
    end

    subgraph COST["💰 月成本（50 只股估算）"]
        C0["≈ $5-15"]
        C1["≈ $1"]
        C2["≈ $10-30"]
        C3["$0<br/>用户已订阅"]
    end

    L0 --> C0
    L1 --> C1
    L2 --> C2
    L3 --> C3

    subgraph WRITE["写入"]
        N["industry_news"]
        DS["daily_summaries"]
        AR["analysis_reports"]
        OBS["不写入<br/>对话 → 用户"]
    end

    L0 --> N
    L1 --> DS
    L2 --> AR
    L3 --> OBS

    classDef tier0 fill:#e1f5fe,stroke:#0288d1
    classDef tier1 fill:#e8f5e9,stroke:#388e3c
    classDef tier2 fill:#fff3e0,stroke:#f57c00
    classDef tier3 fill:#f3e5f5,stroke:#7b1fa2

    class L0,C0 tier0
    class L1,C1 tier1
    class L2,C2 tier2
    class L3,C3 tier3
```

---

## 双轨协同（自动监控线 ⟷ 交互分析线）

```mermaid
flowchart LR
    subgraph AUTO["🔁 自动监控线（Celery）"]
        A1[采集] --> A2[计算] --> A3[事件检测] --> A4[L1 摘要] --> A5[L2 报告]
        A5 -.> WX[企业微信告警]
    end

    subgraph DB[(PostgreSQL)]
        DB1[全部数据表]
    end

    subgraph INTERACT["💬 交互分析线（桌面）"]
        U[用户]
        DC[桌面 Claude]
        U <--> DC
    end

    AUTO --> DB
    DB <-. "只读 MCP" .-> DC

    WX --> U

    Note["典型流程：<br/>1) 16:30 推送收到 SIGNAL_FLIP<br/>2) 用户问桌面 Claude 'X 为什么翻转？'<br/>3) Claude 跑 5 个 SQL 整理出解释<br/>4) 用户做决策（系统不下单）"]

    classDef auto fill:#fff3e0,stroke:#f57c00
    classDef db fill:#f3e5f5,stroke:#7b1fa2
    classDef inter fill:#e3f2fd,stroke:#1976d2

    class A1,A2,A3,A4,A5,WX auto
    class DB,DB1 db
    class U,DC inter
```

---

## 字段引用速查

| 关键判断 | 涉及字段 | 来源表 |
|---------|---------|--------|
| 自选股过滤 | `stocks.is_watchlist = true` | stocks |
| 数据就绪 | `stocks.data_ready = true` | stocks |
| 资讯重要性 | `industry_news.importance_score` ∈ [0, 1] | industry_news |
| 资讯紧急级 | `industry_news.urgency` ∈ {urgent, important, info} | industry_news |
| 当日事件 | `stock_events.triggered_at::date = current_date` | stock_events |
| 事件未推送 | `stock_events.notified_at IS NULL` | stock_events |
| 当日 AI 信号 | `daily_summaries.signal` ∈ {bullish, bearish, neutral} | daily_summaries |
| 信号变化 | `daily_summaries.label_changed = true` | daily_summaries |
| 深度报告类型 | `analysis_reports.report_type` ∈ {daily, event_driven, initial} | analysis_reports |

详见 [mcp-data-dictionary.md](mcp-data-dictionary.md)。
