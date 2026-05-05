# MyStock 实现计划

> 本文件是静态蓝图,描述"要做什么"和"怎么做"。
> 进度跟踪见 [progress.md](progress.md)。

---

## 阶段划分

| 阶段 | 名称 | 目标 |
|------|------|------|
| P1 | 基础设施 | Docker 环境、数据库、项目骨架 |
| P2 | 数据采集 | A股/港股历史数据接入与持久化 |
| P3 | 技术分析 | 指标计算、背离检测、筹码分析 |
| P4 | 基本面分析 | PE、盈利预测、远期 PE、行业对比 |
| P5 | AI 分析报告 | LangChain 综合报告生成 |
| P6 | 资讯监控 | 定时爬取、去重、情感标注 |
| P7 | 供应链分析 | 年报 AI 提取、供应链图谱 |
| P8 | 前端 | 完整 UI、图表、交互 |
| **P9** | **v2 框架精简(2026-05)** | **6D→4D 精简、目标价主导决策、web_search 增量** |
| **P10** | **全局供应链 + 标签管理(2026-05)** | **跨自选股聚簇视图 + 标签 CRUD** |

---

## P9 — v2 框架精简(2026-05 完成)

### 任务清单

- [x] P9-1 移除详情页 D5 维度卡,业绩兑现并入 D3 护城河
- [x] P9-2 移除 D4 动态赔率独立段,合并到"主决策依据·估值赔率"
- [x] P9-3 报告 prompt 升级:技术面输出 400 字四论点(趋势/动量/量价/相对强度)
- [x] P9-4 报告 context 扩展:新增量比 20d、5/20/60 日累涨、相对沪深 300 强度、主力资金 5/20 日
- [x] P9-5 高盛权重 1.20 → 0.80 迁移并触发全量重算
- [x] P9-6 默认排序改为 v5 综合分(目标价主导)
- [x] P9-7 Tier 加权简化为 D3 + (D1,D2) + D8 + tech,Veto 仅看 D3
- [x] P9-8 Claude `web_search` 研报抓取器,集成 AKShare 主源 + 7 天增量

### 关键文件

```
backend/app/services/ai_analyzer/report_generator.py    # _populate_tech_context, REPORT_PROMPT
backend/app/services/data_fetcher/research_websearch_fetcher.py  # 新增 web_search 抓取
backend/app/tasks/news_tasks.py                          # _fetch_and_save_research 双源融合
backend/alembic/versions/20260512_goldman_weight.py      # 高盛权重迁移
frontend/components/stock/StockDetailView.tsx           # 4D 精简渲染
frontend/components/stock/WatchlistTable.tsx            # 默认排序、表头冻结
```

---

## P10 — 全局供应链 + 标签管理(2026-05 完成)

### 任务清单

- [x] P10-1 后端聚合接口 `GET /supply-chain/global` — 自选股 + 上下游伙伴 + 行业/主题聚簇
- [x] P10-2 聚簇 fallback:industry > theme tag > "未分组"(实际数据中 industry 普遍为空)
- [x] P10-3 前端独立页 `/supply-chain` — ReactFlow 网络图,按聚簇分组,焦点高亮 + 三档过滤
- [x] P10-4 个股详情页移除上下游模块,留指引链接
- [x] P10-5 主页 WatchlistTable 添加"📊 全局供应链图"跳转按钮
- [x] P10-6 标签全局删除接口 `DELETE /tags/{tag_id}` — 解绑 + 删除标签本体
- [x] P10-7 前端"管理标签"模式 + × 删除按钮 + confirm 防误删

### 关键文件

```
backend/app/services/supply_chain_service.py        # get_global_supply_chain 聚簇逻辑
backend/app/api/v1/endpoints/supply_chain.py        # GET /global
backend/app/api/v1/endpoints/tags.py                # DELETE /tags/{id}
backend/app/services/tags_service.py                # delete_tag_globally
frontend/app/supply-chain/page.tsx                  # 新页面入口
frontend/components/supply-chain/GlobalSupplyChainView.tsx  # ReactFlow 实现
frontend/components/dashboard/WatchlistWithTagFilter.tsx    # 标签删除 UI
```

---

## P1 — 基础设施

### 任务清单

- [ ] P1-1 `docker-compose.yml`（postgres、redis、backend、frontend、celery-worker、celery-beat）
- [ ] P1-2 `.env.example` 包含所有必要变量
- [ ] P1-3 后端 `pyproject.toml`（uv 项目，Python 3.11）
- [ ] P1-4 FastAPI 应用骨架（`app/main.py`、健康检查接口）
- [ ] P1-5 SQLAlchemy async 连接配置（`app/core/database.py`）
- [ ] P1-6 所有 ORM 模型（`app/models/`）
- [ ] P1-7 Alembic 初始化 + 初始迁移
- [ ] P1-8 Celery 配置（`app/tasks/celery_app.py`）
- [ ] P1-9 后端 `Dockerfile`（uv + 多阶段构建）
- [ ] P1-10 前端 `package.json` + Next.js 骨架 + `Dockerfile`

### 关键文件

```
docker-compose.yml
.env.example
backend/
  pyproject.toml
  app/
    main.py
    core/
      config.py        # 从环境变量读取配置（pydantic-settings）
      database.py      # AsyncEngine + AsyncSession
    models/
      base.py          # DeclarativeBase
      stock.py         # stocks 表
      kline.py         # stock_daily_kline 表
      indicator.py     # stock_technical_indicators 表
      fundamental.py   # stock_fundamentals + profit_forecast 表
      chip.py          # chip_distribution 表
      news.py          # industry_news + news_stock_relation 表
      supply_chain.py  # supply_chain 表
      report.py        # analysis_reports 表
    tasks/
      celery_app.py
  alembic/
    env.py
    versions/
frontend/
  app/
    layout.tsx
    page.tsx
  package.json
```

---

## P2 — 数据采集

### 任务清单

- [ ] P2-1 AKShare fetcher 基类（重试、限速、错误处理）
- [ ] P2-2 A股历史 K 线采集（`ak.stock_zh_a_hist`，3个月回填）
- [ ] P2-3 港股历史 K 线采集（AKShare + yfinance 双源）
- [ ] P2-4 股票基础信息采集（名称、行业、市值）
- [ ] P2-5 实时行情接口（东方财富，延迟15秒）
- [ ] P2-6 批量入库（`INSERT ... ON CONFLICT DO NOTHING`）
- [ ] P2-7 REST API：搜索股票、添加自选股、获取 K 线数据
- [ ] P2-8 Celery 定时任务：交易日每5分钟更新行情

### 技术要点

- AKShare 调用间隔 ≥ 500ms，防封禁
- 港股代码转换：`"00700"` ↔ `"0700.HK"`（在 fetcher 层封装）
- 批量插入使用 `asyncpg` 的 `executemany`
- K 线表唯一约束 `(stock_id, trade_date)` 保证幂等

---

## P3 — 技术分析

### 任务清单

- [ ] P3-1 技术指标计算（`pandas-ta`）：MA5/10/20/60、MACD、RSI、KDJ、布林带、OBV
- [ ] P3-2 指标结果持久化到 `stock_technical_indicators`
- [ ] P3-3 背离检测算法（`scipy.signal.find_peaks`，回看20-60日）
- [ ] P3-4 背离信号入库 `divergence_signals`
- [ ] P3-5 筹码分布计算（GSY 模型，250日回看）
- [ ] P3-6 量价分析：量比、换手率异常检测（>2σ）
- [ ] P3-7 Celery 任务：每日收盘后批量计算指标
- [ ] P3-8 REST API：返回技术指标数据供前端渲染

### 背离检测算法

```python
# 顶背离：价格新高但 MACD/RSI 未新高
# 底背离：价格新低但 MACD/RSI 未新低
from scipy.signal import find_peaks
# 回看窗口 20-60 交易日，置信度 0-1
```

### 筹码分布（GSY 模型）

```python
# 每日按换手率衰减旧筹码，按正态分布叠加新筹码
# 回看 250 交易日，输出每价位持仓比例
# 计算：获利盘比例、平均成本、集中度
```

---

## P4 — 基本面分析

### 任务清单

- [ ] P4-1 PE-TTM 采集（`ak.stock_a_lg_indicator()`）
- [ ] P4-2 历史财务数据采集（营收、净利润、EPS、ROE）
- [ ] P4-3 机构盈利预测采集（Tushare Pro `forecast` 接口）
- [ ] P4-4 远期 PE 计算（当前价 / 预测 EPS）
- [ ] P4-5 行业 PE 中位数计算（行业成分股统计）
- [ ] P4-6 PE 历史百分位计算（PE Band）
- [ ] P4-7 Celery 任务：每日更新基本面数据
- [ ] P4-8 REST API：返回基本面指标和盈利预测

---

## P5 — AI 分析报告

### 任务清单

- [ ] P5-1 LangChain 链配置（支持 OpenAI / Claude 双后端）
- [ ] P5-2 数据聚合器（收集技术面 + 基本面 + 资讯 + 供应链）
- [ ] P5-3 分析提示词模板（结构化输出：结论、信号、风险、支撑压力位）
- [ ] P5-4 报告入库 `analysis_reports`（JSONB 存完整报告）
- [ ] P5-5 Celery 任务：每日盘后自动生成（每只自选股）
- [ ] P5-6 事件触发重新生成（重大资讯出现时）
- [ ] P5-7 REST API：获取最新报告、历史报告列表

### 报告结构

```
一句话结论（买入/观望/回避 + 核心理由）
技术面分析（150字，1-2个核心信号）
基本面分析（150字，估值判断）
近期催化剂与风险
支撑位 / 压力位
免责声明
```

---

## P6 — 资讯监控

### 任务清单

- [ ] P6-1 资讯爬虫基类（异步、去重、错误重试）
- [ ] P6-2 华尔街见闻爬虫（逆向 API 接口）
- [ ] P6-3 财联社电报爬虫（AKShare 封装）
- [ ] P6-4 x.com 爬虫（Playwright 模拟，或 Twitter API v2）
- [ ] P6-5 雪球讨论爬虫
- [ ] P6-6 SHA256 去重（`content_hash` 唯一索引）
- [ ] P6-7 AI 处理：摘要（100字）+ 情感标注 + 股票相关度评分
- [ ] P6-8 资讯-股票关联写入 `news_stock_relation`
- [ ] P6-9 Celery Beat：每3小时触发
- [ ] P6-10 REST API：自选股相关资讯 Feed

---

## P7 — 供应链分析

### 任务清单

- [ ] P7-1 年报 PDF 下载（巨潮资讯 API）
- [ ] P7-2 PDF 文本提取（PyMuPDF）
- [ ] P7-3 AI 提取供应链（GPT-4o，结构化 JSON 输出）
- [ ] P7-4 供应链数据入库 `supply_chain`
- [ ] P7-5 上市公司节点自动关联 `stocks` 表
- [ ] P7-6 REST API：返回供应链树形数据
- [ ] P7-7 供应链图谱前端（React Flow）

---

## P8 — 前端

### 任务清单

- [ ] P8-1 自选股 Dashboard（列表、涨跌幅、AI 信号灯）
- [ ] P8-2 添加/删除自选股（搜索 + 确认）
- [ ] P8-3 股票详情页框架（Tab 导航）
- [ ] P8-4 K 线图（TradingView Lightweight Charts，支持多时间周期）
- [ ] P8-5 技术指标副图（MACD、RSI、KDJ、成交量）
- [ ] P8-6 背离标注（K 线图上箭头标记）
- [ ] P8-7 筹码分布图（ECharts 水平条形图）
- [ ] P8-8 基本面面板（PE Band、营收/利润趋势、远期PE）
- [ ] P8-9 AI 分析报告展示（Markdown 渲染）
- [ ] P8-10 供应链图谱（React Flow 交互节点）
- [ ] P8-11 资讯 Feed（时间线，情感颜色标注）
- [ ] P8-12 响应式布局适配

---

## 依赖关系

```
P1（基础设施）
  └─► P2（数据采集）
        └─► P3（技术分析）
        └─► P4（基本面分析）
              └─► P5（AI 报告）◄── P6（资讯监控）
                                ◄── P7（供应链）
P8（前端）依赖 P2/P3/P4/P5/P6/P7 的 API
```
