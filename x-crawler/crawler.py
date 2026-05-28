"""mystock-x-crawler — 独立 X.com timeline 抓取服务

设计:
- 长驻进程,定时遍历 KOL 列表抓 timeline
- 每个账号间隔 60-120s 随机抖动,降风控
- Playwright + 副号 cookies (auth_token + ct0) 登录态访问
- per-handle Redis cursor (tweet_id) 增量去重
- 抓到的推文 push 到 Redis list `x_pending_tweets`
- backend `consume_x_tweets` celery task 5min 消费一次入 industry_news
"""
import asyncio
import json
import os
import random
import re
from datetime import datetime, timezone

import redis.asyncio as redis_async
from playwright.async_api import async_playwright

# ── 配置 ─────────────────────────────────────────────────────────
KOL_HANDLES_RAW = os.getenv("X_KOL_HANDLES", "")
KOL_HANDLES = [h.strip().lstrip("@") for h in KOL_HANDLES_RAW.split(",") if h.strip()]
INTERVAL_MIN = int(os.getenv("X_CRAWL_INTERVAL_MINUTES", "30"))
AUTH_TOKEN = os.getenv("X_AUTH_TOKEN", "")
CT0 = os.getenv("X_CT0_TOKEN", "")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
QUEUE_KEY = "x_pending_tweets"
CURSOR_KEY_TPL = "x:cursor:{handle}"

UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0",
]


def log(msg: str) -> None:
    print(f"[{datetime.utcnow().isoformat()}] {msg}", flush=True)


async def fetch_handle_timeline(context, handle: str) -> list[dict]:
    """访问 https://x.com/{handle},抓取最新 ~10 条推文"""
    page = await context.new_page()
    try:
        url = f"https://x.com/{handle}"
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        # 等 timeline 加载
        try:
            await page.wait_for_selector("article", timeout=15000)
        except Exception:
            log(f"  [{handle}] no article rendered (page block / 风控?)")
            return []

        # 滚动一次,确保多条 article 加载
        await page.evaluate("window.scrollBy(0, 800)")
        await asyncio.sleep(1.5)

        tweets = await page.evaluate(
            """() => {
                const arts = document.querySelectorAll("article");
                return Array.from(arts).slice(0, 10).map(a => {
                    const link = a.querySelector("a[href*='/status/']");
                    const time_el = a.querySelector("time");
                    const text_el = a.querySelector("div[data-testid='tweetText']");
                    return {
                        permalink: link?.href || "",
                        published_at: time_el?.getAttribute("datetime") || "",
                        text: text_el?.innerText || "",
                    };
                }).filter(t => t.permalink && t.text);
            }"""
        )

        for t in tweets:
            m = re.search(r"/status/(\d+)", t.get("permalink", ""))
            t["tweet_id"] = m.group(1) if m else None
        return [t for t in tweets if t.get("tweet_id")]
    finally:
        await page.close()


async def main_loop() -> None:
    if not (AUTH_TOKEN and CT0):
        log("ERROR: X_AUTH_TOKEN 或 X_CT0_TOKEN 未配置,退出")
        return
    if not KOL_HANDLES:
        log("ERROR: X_KOL_HANDLES 为空,退出")
        return

    log(f"配置: KOL={len(KOL_HANDLES)} 账号, 间隔={INTERVAL_MIN}min")

    redis = redis_async.from_url(REDIS_URL, decode_responses=True)

    async with async_playwright() as p:
        while True:
            cycle_start = datetime.utcnow()
            ua = random.choice(UA_POOL)
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
            )
            try:
                context = await browser.new_context(
                    user_agent=ua,
                    viewport={"width": 1280, "height": 900},
                    locale="en-US",
                )
                # 注入 cookies
                await context.add_cookies(
                    [
                        {
                            "name": "auth_token",
                            "value": AUTH_TOKEN,
                            "domain": ".x.com",
                            "path": "/",
                            "httpOnly": True,
                            "secure": True,
                            "sameSite": "None",
                        },
                        {
                            "name": "ct0",
                            "value": CT0,
                            "domain": ".x.com",
                            "path": "/",
                            "secure": True,
                            "sameSite": "Lax",
                        },
                    ]
                )

                handles = list(KOL_HANDLES)
                random.shuffle(handles)
                total_new = 0

                for handle in handles:
                    cursor = await redis.get(CURSOR_KEY_TPL.format(handle=handle)) or ""
                    try:
                        tweets = await fetch_handle_timeline(context, handle)
                    except Exception as e:
                        log(f"  [{handle}] fetch ERR: {e}")
                        await asyncio.sleep(random.uniform(60, 120))
                        continue

                    max_id = cursor
                    new_count = 0
                    for t in tweets:
                        tid = t["tweet_id"]
                        if cursor and tid <= cursor:
                            continue
                        if tid > max_id:
                            max_id = tid
                        t["handle"] = handle
                        t["fetched_at"] = datetime.now(timezone.utc).isoformat()
                        await redis.lpush(QUEUE_KEY, json.dumps(t, ensure_ascii=False))
                        new_count += 1

                    if max_id and max_id != cursor:
                        await redis.set(
                            CURSOR_KEY_TPL.format(handle=handle),
                            max_id,
                            ex=60 * 60 * 24 * 14,
                        )

                    total_new += new_count
                    log(f"  [{handle}] +{new_count} (cursor: {cursor[:8]}..→{max_id[:8] if max_id else ''}..)")

                    # 抗风控:60-120s 随机间隔
                    await asyncio.sleep(random.uniform(60, 120))

                log(f"cycle done, total_new={total_new}")

            finally:
                await browser.close()

            # 计算休眠时间
            elapsed = (datetime.utcnow() - cycle_start).total_seconds()
            target = INTERVAL_MIN * 60
            sleep_for = max(0, target - elapsed) + random.uniform(0, 60)
            log(f"sleep {int(sleep_for)}s before next cycle")
            await asyncio.sleep(sleep_for)


if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        log("interrupted")
