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

    # AI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: str = ""
    # 深度报告模型（L2，事件触发，建议 Sonnet 4.6）
    anthropic_model: str = "claude-sonnet-4-6"
    # 摘要/打分模型（L1，每日批量 + 资讯打分）
    anthropic_haiku_model: str = "claude-haiku-4-5-20251001"
    openrouter_api_key: str = ""
    openrouter_model: str = "google/gemini-2.5-flash"

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
