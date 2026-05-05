"""事件推送 Markdown 模板（企业微信群机器人）"""

EVENT_ICONS = {
    "MACD_DIVERGENCE_NEW": "🔄",
    "VOLUME_SPIKE": "📊",
    "PE_EXTREME_LOW": "💰",
    "PE_EXTREME_HIGH": "⚠️",
    "URGENT_NEWS": "🚨",
    "AI_SIGNAL_FLIP": "🔁",
    "INSIDER_TRADE": "👥",
    "CALENDAR_REMINDER": "📅",
}

SEVERITY_BADGE = {
    "high": "<font color=\"warning\">[紧急]</font>",
    "medium": "<font color=\"comment\">[关注]</font>",
    "low": "[参考]",
}


def format_event(*, event_type: str, severity: str, title: str, payload: dict | None) -> str:
    icon = EVENT_ICONS.get(event_type, "🔔")
    badge = SEVERITY_BADGE.get(severity, "[?]")
    payload = payload or {}

    body = ""
    if event_type == "MACD_DIVERGENCE_NEW":
        body = (
            f"- 信号类型：{payload.get('signal_type')}\n"
            f"- 置信度：{payload.get('confidence')}\n"
            f"- 极值价位：{payload.get('price_point1')} → {payload.get('price_point2')}"
        )
    elif event_type == "VOLUME_SPIKE":
        body = (
            f"- 当日成交量：{payload.get('volume'):,}\n"
            f"- 20 日均量：{payload.get('avg_20')}\n"
            f"- 放大倍数：**{payload.get('ratio')}x**\n"
            f"- 当日涨跌：{(payload.get('change_pct') or 0):+.2f}%"
        )
    elif event_type in ("PE_EXTREME_LOW", "PE_EXTREME_HIGH"):
        body = (
            f"- 当前 PE-TTM：**{payload.get('current_pe')}**\n"
            f"- 历史百分位：{payload.get('percentile')}%\n"
            f"- 5 年区间 [{payload.get('low_threshold')} , {payload.get('high_threshold')}]"
        )
    elif event_type == "URGENT_NEWS":
        body = (
            f"- 来源：{payload.get('source')}\n"
            f"- 方向：{payload.get('direction')}\n"
            f"- 摘要：{payload.get('summary') or '—'}"
        )
        url = payload.get("source_url")
        if url:
            body += f"\n- [查看原文]({url})"
    elif event_type == "AI_SIGNAL_FLIP":
        body = (
            f"- 信号变化：**{payload.get('from_signal')}** → **{payload.get('to_signal')}**\n"
            f"- 标签：{payload.get('label')}\n"
            f"- 一句话：{payload.get('one_liner') or '—'}"
        )
    elif event_type == "INSIDER_TRADE":
        action = "减持" if payload.get("trade_type") == "reduce" else "增持"
        pct = payload.get("pct_of_total")
        shares = payload.get("shares")
        body = (
            f"- 类型：**{action}**\n"
            f"- 股东：{payload.get('holder_name') or '—'}\n"
            f"- 占总股本：**{pct:.2f}%**" if pct is not None else "- 占总股本：—"
        ) + (f"\n- 股数：{shares:,}" if shares else "") + (
            f"\n- 价格区间：{payload.get('price_low')} ~ {payload.get('price_high')}"
            if payload.get('price_low') else ""
        )
    elif event_type == "CALENDAR_REMINDER":
        body = (
            f"- 类型：{payload.get('calendar_event_type')}\n"
            f"- 事件日：{payload.get('event_date')}\n"
            f"- 距今：T-{payload.get('lead_days')} 天"
        )
    return f"## {icon} {badge} {title}\n\n{body}"


def format_aggregated(events: list[dict]) -> str:
    """整点聚合 medium 级事件"""
    if not events:
        return ""
    lines = ["## 📋 整点事件汇总", ""]
    for e in events[:30]:
        icon = EVENT_ICONS.get(e["event_type"], "🔔")
        lines.append(f"- {icon} **{e['event_type']}** | {e['title']}")
    return "\n".join(lines)
