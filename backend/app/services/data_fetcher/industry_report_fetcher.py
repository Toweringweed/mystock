"""SEC EDGAR 10-Q 下载与文本提取（NVDA + 4 大 CSP）

复用 annual_report_fetcher 的设计：下载到本地 → PyMuPDF / HTML 解析 → 关键章节文本切片。
SEC EDGAR 不需要 API key，但要求 User-Agent header。
"""
import logging
from dataclasses import dataclass
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

REPORT_DIR = Path("/app/data/sec_filings")
SEC_USER_AGENT = "MyStock Research mystock@example.com"  # SEC 要求标识

# Ticker → SEC CIK
CIK_MAP = {
    "NVDA":  "0001045810",
    "GOOGL": "0001652044",
    "META":  "0001326801",
    "MSFT":  "0000789019",
    "AMZN":  "0001018724",
}


@dataclass
class FilingInfo:
    ticker: str
    accession: str          # e.g. 0001045810-26-000123
    primary_doc: str        # main .htm
    filing_date: str        # YYYY-MM-DD
    form: str               # "10-Q" / "10-K"


async def get_latest_10q(ticker: str) -> FilingInfo | None:
    """通过 SEC submissions API 找最新 10-Q"""
    cik = CIK_MAP.get(ticker.upper())
    if not cik:
        logger.warning(f"[industry] Unknown ticker {ticker}, no CIK map entry")
        return None
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    try:
        async with httpx.AsyncClient(timeout=30, headers={"User-Agent": SEC_USER_AGENT}) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.error(f"[industry][{ticker}] SEC submissions 拉取失败: {e}")
        return None

    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])
    dates = recent.get("filingDate", [])
    for i, form in enumerate(forms):
        if form == "10-Q":
            return FilingInfo(
                ticker=ticker.upper(),
                accession=accessions[i],
                primary_doc=primary_docs[i],
                filing_date=dates[i],
                form=form,
            )
    return None


async def download_filing_text(filing: FilingInfo, max_chars: int = 12000) -> str:
    """下载 10-Q 主文档（HTML），过滤 Data Center / Capex 等关键词章节"""
    cik_int = int(CIK_MAP[filing.ticker])  # 用于 URL 路径（去前导 0）
    accession_no_dash = filing.accession.replace("-", "")
    url = (
        f"https://www.sec.gov/Archives/edgar/data/{cik_int}/"
        f"{accession_no_dash}/{filing.primary_doc}"
    )
    save_dir = REPORT_DIR / filing.ticker
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / f"{filing.accession}_{filing.primary_doc}"

    if not save_path.exists():
        try:
            async with httpx.AsyncClient(
                timeout=120, headers={"User-Agent": SEC_USER_AGENT}
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                save_path.write_bytes(resp.content)
        except Exception as e:
            logger.error(f"[industry][{filing.ticker}] 10-Q 下载失败 {url}: {e}")
            return ""

    return _extract_industry_metrics_text(save_path, max_chars)


def _extract_industry_metrics_text(html_path: Path, max_chars: int) -> str:
    """从 SEC 10-Q (inline XBRL HTML) 提取数据中心/capex 相关段落

    关键技术点:NVDA/CSP 的 10-Q 主文档是 inline XBRL,大量 ix:* 命名空间标签
    携带 XBRL 元数据(日期/CIK/财务标签等)。BeautifulSoup 默认 get_text 会把这些
    元数据当成文本,淹没真实的"Management's Discussion"自然语言段落。

    解决:先移除 script/style/ix:hidden/ix:header,再优先取 <p>/<div>/<td> 含
    自然语言段落的元素,跳过纯数字/日期堆叠的元数据节点。
    """
    try:
        from bs4 import BeautifulSoup
        html = html_path.read_text(encoding="utf-8", errors="ignore")
        soup = BeautifulSoup(html, "lxml")

        # 移除非内容节点 + XBRL 元数据
        for tag_name in ["script", "style", "ix:hidden", "ix:header"]:
            for t in soup.find_all(tag_name):
                t.decompose()

        # 优先用 <p> 段落,跳过短(<30 字)/全数字/全标签的节点
        good_paragraphs: list[str] = []
        for p in soup.find_all(["p", "div"]):
            txt = p.get_text(separator=" ", strip=True)
            if len(txt) < 50:
                continue
            # 数字/日期占比过高的节点(XBRL 表格)跳过
            digit_ratio = sum(1 for c in txt if c.isdigit()) / max(1, len(txt))
            if digit_ratio > 0.4:
                continue
            good_paragraphs.append(txt)

        text = "\n\n".join(good_paragraphs)
        if not text:  # 兜底:用全文 get_text
            text = soup.get_text(separator="\n")
    except Exception as e:
        logger.warning(f"HTML 解析失败 {html_path}: {e}")
        return ""

    keywords = [
        "Data Center", "data center", "Capital expenditures", "capital expenditure",
        "AI infrastructure", "data centers", "datacenter", "Data center",
    ]
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    matched = [p for p in paragraphs if any(k in p for k in keywords)]
    out = "\n\n".join(matched) if matched else "\n\n".join(paragraphs[:50])
    return out[:max_chars]
