"""券商研报 — Claude web_search 抓取器(增量补充)

用 Anthropic Claude API 的 web_search 工具,搜索最近 N 天的券商研报标题/机构/评级/PDF 链接,
作为 AKShare 研报源的补充(AKShare 对部分股票或新发研报覆盖不足)。

输出格式与 research_report_fetcher.fetch_research_reports() 兼容,可直接喂给 _fetch_and_save_research()。

设计要点:
- 仅抓元数据(标题/机构/评级/日期/PDF链接),不抓正文(正文由 process_research_pdfs 走原 PDF 通道)
- 由 Claude 推理自动去重(prompt 里告诉它已存在的标题集合)
- 失败/无密钥时返回空 list,不阻塞 AKShare 流程
"""
import asyncio
import json
import logging
import re
from datetime import date, datetime, timedelta

from app.core.config import settings as app_settings

logger = logging.getLogger(__name__)


_PROMPT_TEMPLATE = """你需要使用 web_search 工具搜索 A 股 / 港股股票 **{name}({code})** 在最近 {days} 天内发布的卖方券商研报(中信/中金/华泰/招商/国信/光大/海通/广发/兴业/方正/天风/东吴/民生/中泰/国泰君安/申万宏源/平安/华西/中信建投/财通/国投/西部/西南/华创/银河/东方/长江/浙商/西南/申银万国/Goldman/Morgan Stanley/JPMorgan/UBS/Citi 等).

执行步骤:
1) 搜索关键词建议: "{name} 券商研报 {code} 评级 目标价" / "{name} {code} 研报 PDF" / 同义中英文组合
2) 关注东方财富、慧博投研、巨潮资讯、研报中心、雪球等聚合站
3) 提取每条研报的: 报告标题 / 发布日期(YYYY-MM-DD) / 机构 / 评级(买入/增持/中性/减持/卖出 或 Buy/Overweight 等) / PDF 直链(若有) / 三年 EPS · PE 预测(若摘要里出现)
4) 严格按 JSON array 输出,**禁止**任何额外文字、解释、markdown 代码块标记

已存在标题列表(请避免重复 — 完全相同标题或 90% 以上相似的请跳过):
{seen_titles}

JSON 字段(每个对象):
{{
  "title": str,                    // 报告完整标题
  "broker": str,                   // 机构(中文优先)
  "rating": str | null,            // 评级原文
  "published_at": "YYYY-MM-DD",    // 发布日期
  "pdf_url": str | null,           // PDF 链接(无则 null)
  "source_url": str | null,        // 原网页链接(优先 PDF, 否则报告页)
  "forecast_year_base": int | null,// 三年预测起始年
  "eps_y1": float | null,
  "eps_y2": float | null,
  "eps_y3": float | null,
  "pe_y1": float | null,
  "pe_y2": float | null,
  "pe_y3": float | null,
  "summary": str | null            // 研报核心观点(<=120 字,可选)
}}

只输出 JSON array,无其他字符。如果没有找到任何新研报,输出空数组 []。
"""


def _parse_json_array(raw: str) -> list[dict]:
    """从 LLM 输出里抽 JSON array(容错: 可能被 ```json ... ``` 包裹)"""
    if not raw:
        return []
    s = raw.strip()
    # 去 markdown code block
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    s = s.strip()
    # 找首个 [ 和最后一个 ]
    lb = s.find("[")
    rb = s.rfind("]")
    if lb == -1 or rb == -1 or rb < lb:
        return []
    try:
        arr = json.loads(s[lb : rb + 1])
        return arr if isinstance(arr, list) else []
    except Exception as e:
        logger.warning(f"[websearch] JSON 解析失败: {e}; raw[:200]={s[:200]}")
        return []


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.strptime(str(s).strip()[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _normalize_item(d: dict, code: str) -> dict | None:
    """转成与 research_report_fetcher.fetch_research_reports 一致的格式"""
    title = (d.get("title") or "").strip()
    broker = (d.get("broker") or "").strip()
    if not title or not broker:
        return None
    pub_date = _parse_date(d.get("published_at"))
    if not pub_date:
        return None

    def _f(v):
        try:
            if v is None or v == "":
                return None
            return float(v)
        except (TypeError, ValueError):
            return None

    return {
        "stock_code": code,
        "stock_name": "",
        "title": title[:300],
        "broker": broker[:80],
        "rating": (d.get("rating") or None),
        "industry": None,
        "published_at": pub_date,
        "pdf_url": (d.get("pdf_url") or None),
        "source_url": (d.get("source_url") or d.get("pdf_url") or None),
        "forecast_year_base": int(d["forecast_year_base"]) if d.get("forecast_year_base") else None,
        "eps_y1": _f(d.get("eps_y1")),
        "eps_y2": _f(d.get("eps_y2")),
        "eps_y3": _f(d.get("eps_y3")),
        "pe_y1": _f(d.get("pe_y1")),
        "pe_y2": _f(d.get("pe_y2")),
        "pe_y3": _f(d.get("pe_y3")),
        "summary": (d.get("summary") or None),
    }


async def _get_setting(db, key: str) -> str:
    """统一读 setting:DB 优先,fallback 到环境变量"""
    if db is not None:
        try:
            from app.services.settings_service import get_effective_value
            v = await get_effective_value(db, key)
            if v:
                return v
        except Exception:
            pass
    return str(getattr(app_settings, key, "") or "")


async def _call_anthropic_web_search(
    *, ant_key: str, model: str, prompt: str, max_searches: int
) -> str:
    """走 Anthropic 官方 web_search_20250305 server tool"""
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=ant_key)
    resp = await client.messages.create(
        model=model,
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
        tools=[{
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": max_searches,
        }],
    )
    parts: list[str] = []
    for block in resp.content:
        if getattr(block, "type", None) == "text":
            parts.append(getattr(block, "text", "") or "")
    return "".join(parts).strip()


async def _call_openrouter_online(
    *, or_key: str, prompt: str, max_searches: int
) -> str:
    """走 OpenRouter `:online` plugin(自动注入 web 搜索结果)。

    OpenRouter 的 web search 是 Exa/Brave 驱动的,免费/按 token 计费。
    用 anthropic/claude-sonnet-4:online 触发自动联网。
    """
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=or_key, base_url="https://openrouter.ai/api/v1")
    # :online 后缀 = 启用 web search plugin
    resp = await client.chat.completions.create(
        model="anthropic/claude-sonnet-4:online",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=4000,
        temperature=0.0,
        extra_body={
            "plugins": [{"id": "web", "max_results": max(max_searches, 5)}],
        },
    )
    return (resp.choices[0].message.content or "").strip()


async def fetch_research_via_websearch(
    db,
    *,
    code: str,
    name: str,
    days: int = 7,
    seen_titles: list[str] | None = None,
    max_searches: int = 5,
) -> list[dict]:
    """通过 web_search 工具搜最近 N 天的研报,返回与 AKShare 兼容的 dict list。

    Provider 优先级:
        1. Anthropic 直连(`web_search_20250305` server tool) — 若 key 有效
        2. OpenRouter `:online` plugin — fallback,免 Anthropic 直连密钥

    Args:
        db: AsyncSession
        code, name, days: 股票元信息 + 搜索窗口
        seen_titles: 已存在标题(用于 LLM 去重提示)
        max_searches: web_search 调用次数上限

    Returns:
        list[dict] — 与 fetch_research_reports() 同结构;失败时返回 []
    """
    seen = "\n".join(f"- {t}" for t in (seen_titles or [])[:30]) or "(无)"
    prompt = _PROMPT_TEMPLATE.format(name=name, code=code, days=days, seen_titles=seen)

    raw = ""
    used_provider = ""

    # ── Provider 1: Anthropic 直连 ─────────────────────────────
    ant_key = await _get_setting(db, "anthropic_api_key")
    ant_model = await _get_setting(db, "anthropic_model") or "claude-sonnet-4-6"
    if ant_key:
        try:
            raw = await _call_anthropic_web_search(
                ant_key=ant_key, model=ant_model, prompt=prompt, max_searches=max_searches,
            )
            used_provider = f"anthropic({ant_model})"
        except Exception as e:
            logger.warning(f"[websearch][{code}] Anthropic 失败,fallback OpenRouter: {e}")

    # ── Provider 2: OpenRouter :online ─────────────────────────
    if not raw:
        or_key = await _get_setting(db, "openrouter_api_key")
        if or_key:
            try:
                raw = await _call_openrouter_online(
                    or_key=or_key, prompt=prompt, max_searches=max_searches,
                )
                used_provider = "openrouter(claude-sonnet-4:online)"
            except Exception as e:
                logger.warning(f"[websearch][{code}] OpenRouter 也失败: {e}")

    if not raw:
        logger.info(f"[websearch][{code}] 所有 provider 不可用,跳过 web_search")
        return []

    items_raw = _parse_json_array(raw)
    if not items_raw:
        logger.info(f"[websearch][{code}] 无新研报")
        return []

    cutoff = date.today() - timedelta(days=days + 1)
    out: list[dict] = []
    for item_raw in items_raw:
        if not isinstance(item_raw, dict):
            continue
        norm = _normalize_item(item_raw, code)
        if not norm:
            continue
        if norm["published_at"] and norm["published_at"] < cutoff:
            continue
        out.append(norm)

    logger.info(f"[websearch][{code}] 通过 web_search 找到 {len(out)} 条新研报")
    # 适度限速(Anthropic API + web_search 配额)
    await asyncio.sleep(0.5)
    return out
