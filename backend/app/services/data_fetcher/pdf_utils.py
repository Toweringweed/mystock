"""通用 PDF 工具：下载 + 全文提取（PyMuPDF）

抽离自 annual_report_fetcher 的关键词提取，扩展为"全文按页拼接"模式，
供研报 / 任意 PDF 解析复用。
"""
import asyncio
import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)


PDF_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36"
)


async def download_pdf(
    url: str,
    dest: Path,
    timeout: float = 60.0,
    overwrite: bool = False,
) -> bool:
    """下载 PDF 到本地。返回 True 表示成功（含文件已存在）"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not overwrite and dest.stat().st_size > 0:
        return True
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": PDF_USER_AGENT, "Accept": "application/pdf,*/*"},
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            content = resp.content
            if not content or len(content) < 1024:
                logger.warning(f"[pdf] 下载内容过短（{len(content)} bytes）: {url}")
                return False
            # 简单校验是否为 PDF（前 4 字节 %PDF）
            if not content[:4] == b"%PDF":
                logger.warning(f"[pdf] 非 PDF 内容: {url}")
                return False
            dest.write_bytes(content)
            return True
    except Exception as e:
        logger.error(f"[pdf] 下载失败 {url}: {e}")
        return False


def pdf_to_text(
    pdf_path: Path,
    max_pages: int = 50,
    max_chars: int = 12000,
    keywords: list[str] | None = None,
) -> str:
    """提取 PDF 全文（或关键词页）。max_chars 限制总长度，避免 LLM token 爆炸"""
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(str(pdf_path))
        chunks: list[str] = []
        pages_used = 0
        for page_num in range(min(len(doc), max_pages)):
            text = doc.load_page(page_num).get_text() or ""
            if keywords and not any(kw in text for kw in keywords):
                continue
            chunks.append(text.strip())
            pages_used += 1
        doc.close()
        return "\n\n".join(chunks)[:max_chars]
    except Exception as e:
        logger.error(f"[pdf] 文本提取失败 {pdf_path}: {e}")
        return ""


async def pdf_to_text_async(
    pdf_path: Path,
    max_pages: int = 50,
    max_chars: int = 12000,
    keywords: list[str] | None = None,
) -> str:
    """async 包装"""
    return await asyncio.to_thread(pdf_to_text, pdf_path, max_pages, max_chars, keywords)
