from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 应用
    environment: str = "development"
    secret_key: str = "change-this-in-production"
    log_level: str = "INFO"

    # 数据库
    database_url: str = "postgresql+asyncpg://mystock:mystock123@localhost:5432/mystock_db"

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # AI 路由 — 主入口选择(deepseek / openrouter / openai / anthropic),空 = 自动 fallback
    llm_provider_primary: str = ""

    # DeepSeek 直连(OpenAI 兼容接口,价格最低,用户主用)
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    # 默认/快速模型(L1 摘要打分)
    deepseek_model: str = "deepseek-chat"
    # 深度模型(L2 事件深度分析,会输出 reasoning_content + content)
    deepseek_deep_model: str = "deepseek-reasoner"

    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.anthropic.com"
    # 深度报告模型（L2，事件触发，建议 Sonnet 4.6）
    anthropic_model: str = "claude-sonnet-4-6"
    # 摘要/打分模型（L1，每日批量 + 资讯打分）
    anthropic_haiku_model: str = "claude-haiku-4-5-20251001"
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "deepseek/deepseek-chat"

    # 数据源
    tushare_token: str = ""
    futu_host: str = "127.0.0.1"
    futu_port: int = 11111
    twitter_bearer_token: str = ""

    # 通知（资讯流水线分级推送）
    wechat_work_webhook_url: str = ""
    notify_urgent_enabled: str = "true"
    notify_important_enabled: str = "true"
    notify_daily_summary_enabled: str = "true"

    # 调度配置
    report_generation_hour: int = 16
    report_generation_minute: int = 30
    news_crawl_interval_hours: int = 3
    quote_update_interval_seconds: int = 15

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


settings = Settings()
