"""企业微信群机器人推送

文档：https://developer.work.weixin.qq.com/document/path/91770

支持 markdown 与 text 两种消息体；本模块默认 markdown。
"""
import logging

import httpx

logger = logging.getLogger(__name__)

TIMEOUT_SEC = 15


async def send_markdown(webhook_url: str, content: str) -> bool:
    """发送 markdown 消息。返回 True 表示成功送达"""
    if not webhook_url:
        logger.warning("[notifier:wechat] webhook URL 为空，跳过")
        return False
    payload = {
        "msgtype": "markdown",
        "markdown": {"content": content[:4096]},  # 企业微信 markdown 上限 4096 字
    }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SEC) as client:
            resp = await client.post(webhook_url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            if data.get("errcode") != 0:
                logger.warning(f"[notifier:wechat] 推送失败: {data}")
                return False
            return True
    except Exception as e:
        logger.error(f"[notifier:wechat] 推送异常: {e}")
        return False


def format_urgent_card(
    *,
    title: str,
    summary: str,
    source: str,
    direction: str,
    importance_score: float,
    related_stocks: list[tuple[str, str]],  # [(code, name)]
    source_url: str | None = None,
) -> str:
    """紧急级推送 markdown 卡片"""
    direction_icon = {"bullish": "📈", "bearish": "📉", "neutral": "⚖️"}.get(direction, "❓")
    color = {"bullish": "info", "bearish": "warning", "neutral": "comment"}.get(direction, "comment")
    stocks_md = (
        "、".join(f"<font color=\"{color}\">{name}({code})</font>" for code, name in related_stocks)
        if related_stocks else "—"
    )
    link = f"\n\n[查看原文]({source_url})" if source_url else ""
    return (
        f"## 🚨 紧急资讯 {direction_icon}\n"
        f"**{title}**\n\n"
        f"> {summary or '（无摘要）'}\n\n"
        f"**相关股票**：{stocks_md}\n"
        f"**重要性**：{importance_score:.2f} | **来源**：{source}"
        f"{link}"
    )


def format_important_summary(items: list[dict]) -> str:
    """重要级整点聚合推送"""
    if not items:
        return ""
    lines = ["## ⚠️ 重要资讯（整点聚合）", ""]
    for it in items:
        icon = {"bullish": "📈", "bearish": "📉", "neutral": "⚖️"}.get(
            it.get("direction", "neutral"), "❓"
        )
        stocks = "、".join(it.get("stocks", [])) or "—"
        lines.append(
            f"- {icon} **{it['title']}** [{stocks}]\n"
            f"  > {it.get('summary') or ''}"
        )
    return "\n".join(lines)


def format_daily_summary(items: list[dict], date_str: str) -> str:
    """每日摘要推送"""
    if not items:
        return f"## 📊 {date_str} 资讯摘要\n\n（今日无相关资讯）"
    lines = [f"## 📊 {date_str} 资讯摘要", f"共 {len(items)} 条", ""]
    for it in items[:30]:  # 最多 30 条
        icon = {"bullish": "📈", "bearish": "📉", "neutral": "⚖️"}.get(
            it.get("direction", "neutral"), "•"
        )
        stocks = "、".join(it.get("stocks", [])) or "—"
        lines.append(f"- {icon} {it['title']} [{stocks}]")
    return "\n".join(lines)
