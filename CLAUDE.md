# MyStock — 股票分析应用

## 项目文档

- [spec.md](spec.md) — 产品说明书（功能需求、交互设计、数据规格）
- [plan.md](plan.md) — 实现蓝图（阶段划分、任务清单、技术要点）
- [progress.md](progress.md) — 开发进度追踪（当前状态、决策记录）

## 项目概述

A股/港股自选股分析平台，提供技术分析、基本面分析、行业资讯监控和供应链分析。

## 技术栈

- **后端**: Python 3.11 + FastAPI + Celery + SQLAlchemy 2.0
- **前端**: Next.js 14 (App Router) + TypeScript + TailwindCSS
- **数据库**: PostgreSQL 15 + Redis 7
- **包管理**: uv（Python）、pnpm（Node.js）
- **容器化**: Docker + Docker Compose
- **AI 分析**: LangChain + OpenAI / Anthropic Claude API

## 目录结构

```
mystock/
├── backend/
│   ├── app/
│   │   ├── api/           # FastAPI 路由（按资源分文件）
│   │   ├── core/          # 配置、安全、依赖注入
│   │   ├── models/        # SQLAlchemy ORM 模型
│   │   ├── schemas/       # Pydantic v2 schemas
│   │   ├── services/
│   │   │   ├── data_fetcher/   # AKShare/yfinance 数据采集
│   │   │   ├── analysis/       # 技术分析、基本面分析引擎
│   │   │   ├── news_crawler/   # 资讯爬虫（华尔街见闻、x.com）
│   │   │   └── ai_analyzer/    # LangChain 分析报告生成
│   │   └── tasks/         # Celery 定时任务
│   ├── alembic/           # 数据库迁移
│   ├── tests/
│   ├── pyproject.toml     # uv 项目配置
│   └── Dockerfile
├── frontend/
│   ├── app/
│   │   ├── page.tsx              # 主页:WatchlistTable + 标签筛选
│   │   ├── stocks/[code]/        # 个股详情(4D 维度卡 + 技术形态)
│   │   ├── supply-chain/         # 全局供应链网络图(ReactFlow)
│   │   ├── research/             # 券商研报库
│   │   ├── earnings/             # 财报预期差追踪
│   │   ├── backtest/             # 因子回测
│   │   └── settings/
│   ├── components/
│   │   ├── charts/               # TradingView K 线 / ECharts 筹码图
│   │   ├── stock/                # 个股相关组件(WatchlistTable / StockDetailView 等)
│   │   ├── supply-chain/         # GlobalSupplyChainView(ReactFlow 聚簇)
│   │   ├── dashboard/            # WatchlistWithTagFilter(含标签删除)
│   │   └── news/
│   ├── lib/                      # API 调用封装、工具函数
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml
├── docker-compose.override.yml  # 本地开发覆盖配置（gitignore）
├── .env.example
└── CLAUDE.md
```

## 常用命令

### 环境启动

```bash
# 首次启动（构建镜像）
docker compose up --build

# 日常启动
docker compose up -d

# 查看日志
docker compose logs -f backend
docker compose logs -f celery-worker

# 停止
docker compose down
```

### 后端开发（uv）

```bash
# 进入后端目录
cd backend

# 安装依赖（uv 自动创建 .venv）
uv sync

# 添加依赖
uv add akshare pandas-ta
uv add --dev pytest pytest-asyncio

# 运行本地开发服务器（不用 Docker）
uv run fastapi dev app/main.py

# 运行测试
uv run pytest

# 运行单个测试文件
uv run pytest tests/test_analysis.py -v

# 数据库迁移
uv run alembic revision --autogenerate -m "描述"
uv run alembic upgrade head

# 在容器内执行迁移
docker compose exec backend uv run alembic upgrade head
```

### 前端开发

```bash
cd frontend

# 安装依赖
pnpm install

# 本地开发
pnpm dev

# 构建
pnpm build

# 类型检查
pnpm type-check
```

### Celery 任务

```bash
# 手动触发定时任务（调试用）
docker compose exec celery-worker uv run celery -A app.tasks.celery_app call app.tasks.news_tasks.crawl_industry_news

# 查看任务队列状态
docker compose exec celery-worker uv run celery -A app.tasks.celery_app inspect active
```

### 数据库操作

```bash
# 连接 PostgreSQL
docker compose exec postgres psql -U mystock -d mystock_db

# 备份数据库
docker compose exec postgres pg_dump -U mystock mystock_db > backup.sql

# Redis CLI
docker compose exec redis redis-cli
```

### Claude Skill 评分回写

`stock-analysis` skill 在分析完成后调用后端写入 6D 子维度评分(D1/D2/D3/D5/D8/技术):

- **API base URL**:`http://localhost:8010`(默认,docker compose 宿主机端口映射)
- **端点**:`POST /api/v1/analysis/{code}/claude-score`
- 远程访问需通过 ngrok / Cloudflare Tunnel 暴露后,在本文件覆盖此 URL
- 写入后,首页 `WatchlistTable` 综合分自动用 Claude 最新评分;若该股未被 Claude 评过,fallback 到本地 D3 公式
- 注:虽然详情页 D5 维度卡已删除(并入 D3),但 `claude_performance_score` 仍由 skill 输出并存储,用作 D3 护城河可持续性的 evidence 信号(WatchlistTable ⑤ 列、ReportPanel)

### 应用页面布局

| 路由 | 入口 | 功能 |
|------|------|------|
| `/` | 主页 | 自选股 WatchlistTable(默认按 v5 综合分排序) + 标签筛选 + 资讯 Feed |
| `/stocks/[code]` | 表格点击 | 个股详情(K 线 + 4D 维度卡 + 主决策依据 + 技术形态) |
| `/supply-chain` | 主页"📊 全局供应链图"按钮 | 全部自选股聚簇网络图(theme tag 分组,ReactFlow) |
| `/research` | 顶部"研报" | 券商研报库(支持 AKShare + Claude web_search) |
| `/earnings` | 顶部"财报" | 财报预期差追踪 |
| `/backtest` | 顶部"回测" | 因子回测 |
| `/settings` | 顶部"设置" | API key / 模型 / 手动任务 |

## 编码规范

### Python

- 使用 **Pydantic v2** 进行数据校验（不用 v1 语法）
- 所有数据库操作使用 **async SQLAlchemy**（`AsyncSession`）
- API 路由返回类型必须有 Pydantic schema 注解
- 服务层（services/）不直接依赖 FastAPI，保持可测试性
- 股票代码统一格式：A股 `"000001"`，港股 `"00700"`（不含市场后缀）
- 数值计算使用 `Decimal` 而非 `float`（金融精度要求）

### 前端

- 组件使用 **函数式组件 + TypeScript**，不用 class 组件
- 数据请求统一通过 `lib/api/` 目录下的封装函数，不在组件内直接 fetch
- K 线图使用 **TradingView Lightweight Charts**
- 筹码分布、PE Band 等图表使用 **ECharts**（via echarts-for-react）
- A股涨红跌绿：涨色 `#ef5350`，跌色 `#26a69a`

### 数据库

- 所有表必须有 `created_at` / `updated_at` 字段
- 历史 K 线表 `stock_daily_kline` 的联合唯一约束：`(stock_id, trade_date)`
- 枚举值使用 PostgreSQL `ENUM` 类型或 `VARCHAR` + 应用层校验
- 迁移文件一旦提交不得修改，只能新增

## 环境变量

参考 `.env.example`，本地开发复制为 `.env`：

```bash
cp .env.example .env
```

关键变量：

| 变量 | 说明 |
|------|------|
| `DATABASE_URL` | PostgreSQL 连接串 |
| `REDIS_URL` | Redis 连接串 |
| `OPENAI_API_KEY` | OpenAI API Key（AI 分析） |
| `ANTHROPIC_API_KEY` | Claude API Key（备选） |
| `TUSHARE_TOKEN` | Tushare Pro Token |
| `FUTU_HOST` / `FUTU_PORT` | 富途 OpenD 地址（港股实时数据） |

## 数据源说明

| 数据 | 主源 | 补充源 / 备注 |
|------|------|---------------|
| A股历史行情 | AKShare `ak.stock_zh_a_hist()` | — |
| 港股历史行情 | AKShare | yfinance(代码 `"0700.HK"`) |
| 实时行情 | AKShare 东方财富接口 | 延迟约 15 秒 |
| 技术指标(MA/MACD/RSI/KDJ/BB/OBV) | pandas-ta 本地计算 | 持久化 `stock_technical_indicators` |
| 量比/资金流向 | AKShare `stock_individual_fund_flow` | 主力资金 5/20 日净流入,on-the-fly |
| 财务/PE-TTM/ROE | AKShare `ak.stock_a_lg_indicator()` | — |
| 机构盈利预测 | Tushare Pro `forecast` | 三年 EPS / PE 预测 |
| 券商研报 | AKShare `stock_research_report_em` | **Claude web_search 增量补 7 天** (2026-05 新增) |
| 财报披露 | 巨潮资讯 / AKShare | — |
| 行业资讯 | 华尔街见闻 API + AKShare news | 每 3 小时轮询 |
| 供应链 | Claude AI 抽取年报 | 人工校正优先级高于 AI |
| 沪深 300 基准 | AKShare 指数行情 | 60 日相对强度计算 |

**轮询频率**(`backend/app/tasks/celery_app.py` Beat):
- 实时行情: 交易日每 5 分钟
- 资讯爬取: 每 3 小时(同时跑 AKShare + Claude web_search)
- 研报爬取: 每日 09:15 / 16:30
- PDF 摘要处理: 每 5 分钟一批

## 架构决策

- Celery worker 和 beat 分开部署(`docker-compose.yml` 中独立服务)
- 技术指标计算结果持久化到 `stock_technical_indicators` 表,避免每次重算
- 背离信号检测在每日收盘后批量运行,不做实时计算
- AI 分析报告每日盘后生成一次,缓存 24 小时;事件触发(重大资讯)可按需重新生成
- 供应链数据首次通过 AI 提取年报,后续人工校正优先于 AI 重新提取
- **目标价加权**: 取近 30 天研报,按 `institution_metadata.weight_factor` 加权
  - 外资顶投(摩根士丹利/JPM/UBS/Citi/美银) 1.20,**高盛 0.80**(2026-05 下调,AI 板块系统性偏乐观)
  - 国内顶投(中信/中金/华泰) 1.00,中等 0.90~0.95,小券商 0.80
- **6D 框架精简版** (2026-05): 详情页只展示 4 个维度卡 + 技术形态
  - D1 行业拐点+叙事 / D2 外部颠覆 / D3 护城河(并入 D5 业绩兑现+财报预期差) / D8 治理 / 📊 技术形态
  - D4 动态赔率 → 主决策依据·估值赔率(目标价上行空间)
  - D5 业绩兑现节奏 → 已并入 D3,数据流(`claude_performance_score`)仍保留,作为 D3 evidence + 自选股表 ⑤ 列展示

## 注意事项

- AKShare 接口有频率限制，批量操作需加 `asyncio.sleep(0.5)` 间隔
- `pandas-ta` 替代 TA-Lib（避免编译依赖问题），两者 API 不同，不要混用
- 港股代码在不同数据源格式不同：AKShare 用 `"00700"`，yfinance 用 `"0700.HK"`，在 fetcher 层统一转换
- `.env` 和 `docker-compose.override.yml` 已加入 `.gitignore`，不提交到版本控制
- 数据库迁移必须在提交 PR 前运行并测试回滚（`alembic downgrade -1`）
