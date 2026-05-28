"""动态配置服务：DB 覆盖 .env，立即生效"""
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.app_setting import AppSetting

logger = logging.getLogger(__name__)

# 可配置项元数据
SETTING_DEFS: list[dict] = [
    # ── AI 模型 ────────────────────────────────────────────────────────
    {"key": "deepseek_api_key",    "description": "DeepSeek API Key（优先级最高）", "is_secret": True,  "group": "ai"},
    {"key": "deepseek_model",      "description": "DeepSeek 模型名称",              "is_secret": False, "group": "ai"},
    {"key": "deepseek_base_url",   "description": "DeepSeek API Base URL",          "is_secret": False, "group": "ai"},
    {"key": "openrouter_api_key",  "description": "OpenRouter API Key",             "is_secret": True,  "group": "ai"},
    {"key": "openrouter_model",    "description": "OpenRouter 模型名称",              "is_secret": False, "group": "ai"},
    {"key": "openai_api_key",      "description": "OpenAI API Key",                   "is_secret": True,  "group": "ai"},
    {"key": "openai_model",        "description": "OpenAI 模型名称",                  "is_secret": False, "group": "ai"},
    {"key": "anthropic_api_key",   "description": "Anthropic Claude API Key",         "is_secret": True,  "group": "ai"},
    {"key": "anthropic_model",     "description": "Claude 模型名称（用于完整报告）",   "is_secret": False, "group": "ai"},
    {"key": "anthropic_haiku_model", "description": "Claude Haiku 模型名称（用于资讯打分，便宜且快）", "is_secret": False, "group": "ai"},
    # ── 数据源 ─────────────────────────────────────────────────────────
    {"key": "tushare_token",       "description": "Tushare Pro Token",                "is_secret": True,  "group": "data"},
    {"key": "futu_host",           "description": "富途 OpenD 地址",                   "is_secret": False, "group": "data"},
    {"key": "futu_port",           "description": "富途 OpenD 端口",                   "is_secret": False, "group": "data"},
    # ── 通知 ─────────────────────────────────────────────────────────
    {"key": "wechat_work_webhook_url", "description": "企业微信群机器人 Webhook URL", "is_secret": True,  "group": "notifications"},
    {"key": "notify_urgent_enabled",   "description": "启用紧急级实时推送 (true/false)", "is_secret": False, "group": "notifications"},
    {"key": "notify_important_enabled", "description": "启用重要级整点聚合推送 (true/false)", "is_secret": False, "group": "notifications"},
    {"key": "notify_daily_summary_enabled", "description": "启用每日资讯摘要推送 (true/false)", "is_secret": False, "group": "notifications"},
]

KEY_SET = {d["key"] for d in SETTING_DEFS}


def _env_value(key: str) -> str:
    """从 pydantic settings 读取当前环境变量值"""
    return str(getattr(settings, key, "") or "")


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return value[:4] + "****" + value[-4:]


async def get_all_settings(db: AsyncSession) -> list[dict]:
    """返回所有配置项（secret 值脱敏）"""
    db_result = await db.execute(select(AppSetting))
    db_map: dict[str, AppSetting] = {s.key: s for s in db_result.scalars().all()}

    out = []
    for defn in SETTING_DEFS:
        key = defn["key"]
        db_entry = db_map.get(key)
        if db_entry and db_entry.value:
            raw = db_entry.value
            source = "db"
        else:
            raw = _env_value(key)
            source = "env"

        out.append({
            "key": key,
            "value": _mask(raw) if defn["is_secret"] else raw,
            "has_value": bool(raw),
            "description": defn["description"],
            "is_secret": defn["is_secret"],
            "group": defn["group"],
            "source": source,
        })
    return out


async def save_setting(db: AsyncSession, key: str, value: str) -> None:
    """保存配置到 DB，并更新内存中的 settings 对象（立即生效）"""
    if key not in KEY_SET:
        raise ValueError(f"未知配置项: {key}")

    stmt = insert(AppSetting).values(key=key, value=value)
    stmt = stmt.on_conflict_do_update(
        index_elements=["key"],
        set_={"value": stmt.excluded.value},
    )
    await db.execute(stmt)
    await db.flush()

    # 更新内存中的 settings（无需重启）
    if hasattr(settings, key):
        try:
            setattr(settings, key, value)
            logger.info(f"Settings.{key} updated in-memory")
        except Exception as e:
            logger.warning(f"Could not update settings.{key} in-memory: {e}")


async def get_effective_value(db: AsyncSession, key: str) -> str:
    """获取有效值（DB 优先，回退 env）"""
    result = await db.execute(select(AppSetting).where(AppSetting.key == key))
    entry = result.scalar_one_or_none()
    if entry and entry.value:
        return entry.value
    return _env_value(key)
