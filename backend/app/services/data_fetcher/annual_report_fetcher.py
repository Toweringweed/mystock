"""年报 PDF 下载器 — 巨潮资讯"""
import asyncio
import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

REPORT_BASE_DIR = Path("/app/data/annual_reports")
CNINFO_SEARCH_URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"


class AnnualReportFetcher:
    """从巨潮资讯下载最新年报，提取文本"""

    async def fetch_report_text(self, code: str, max_pages: int = 30) -> str:
        """下载年报 PDF 并提取文本，返回关键章节内容"""
        pdf_path = await self._download_latest_annual_report(code)
        if not pdf_path:
            return ""
        return await asyncio.to_thread(self._extract_supply_chain_text, pdf_path, max_pages)

    async def _download_latest_annual_report(self, code: str) -> Path | None:
        """从巨潮资讯搜索并下载最新年报 PDF"""
        try:
            report_url = await self._search_annual_report_url(code)
            if not report_url:
                return None

            save_dir = REPORT_BASE_DIR / code
            save_dir.mkdir(parents=True, exist_ok=True)
            save_path = save_dir / "latest_annual_report.pdf"

            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.get(report_url)
                resp.raise_for_status()
                save_path.write_bytes(resp.content)

            logger.info(f"[{code}] 年报下载完成: {save_path}")
            return save_path
        except Exception as e:
            logger.error(f"[{code}] 年报下载失败: {e}")
            return None

    async def _search_annual_report_url(self, code: str) -> str | None:
        """搜索个股最新年度报告 URL。

        历史 bug:直接 POST cninfo 的 hisAnnouncement/query 时 stock 参数格式
        缺少 orgId 编码,导致接口返回的是"全市场最新公告"列表,所有股票拿到同一份 PDF。
        改用 AKShare 已封装的 stock_individual_notice_report——它内部已正确处理
        股票 → orgId 映射。
        """
        return await asyncio.to_thread(self._search_annual_report_url_sync, code)

    def _search_annual_report_url_sync(self, code: str) -> str | None:
        """两步走:AKShare 拿公告 art_code → 东财 API 取 PDF 直链"""
        try:
            import akshare as ak
            df = ak.stock_individual_notice_report(security=code, symbol="全部")
        except Exception as e:
            logger.warning(f"[{code}] AKShare 公告查询失败: {e}")
            return None

        if df is None or df.empty:
            return None

        title_col = "公告标题"
        url_col = "网址"
        if title_col not in df.columns or url_col not in df.columns:
            logger.warning(f"[{code}] 公告 DataFrame 缺字段: {df.columns.tolist()}")
            return None

        annual_mask = (
            df[title_col].str.contains("年度报告", na=False)
            & ~df[title_col].str.contains("摘要|英文|更新", na=False)
        )
        candidates = df[annual_mask]
        if candidates.empty:
            candidates = df[df[title_col].str.contains("年报", na=False)]
        if candidates.empty:
            logger.warning(f"[{code}] 未找到年度报告公告")
            return None

        detail_url = str(candidates.iloc[0][url_col]).strip()
        if not detail_url:
            return None

        # 从详情页 URL 提取 art_code(形如 AN202603261820776351)
        import re
        m = re.search(r"(AN\d{18,})", detail_url)
        if not m:
            logger.warning(f"[{code}] 无法从 {detail_url} 提取 art_code")
            return None
        art_code = m.group(1)

        # 同步调东财 API 拿真实 PDF URL(本方法已在 to_thread 里,可同步 httpx)
        try:
            import httpx
            api_url = (
                "https://np-cnotice-stock.eastmoney.com/api/content/ann"
                f"?art_code={art_code}&client_source=web&page_index=1"
            )
            with httpx.Client(timeout=20, headers={"User-Agent": "Mozilla/5.0"}) as c:
                r = c.get(api_url)
                if r.status_code != 200:
                    logger.warning(f"[{code}] 东财 PDF API {r.status_code}")
                    return None
                data = r.json().get("data", {}) or {}
                pdf_url = data.get("attach_url")
                if pdf_url:
                    logger.info(f"[{code}] 找到年报 PDF: {data.get('notice_title')}")
                    return pdf_url
        except Exception as e:
            logger.warning(f"[{code}] 东财 PDF API 调用失败: {e}")
        return None

    def _extract_supply_chain_text(self, pdf_path: Path, max_pages: int) -> str:
        return self._extract_text_by_keywords(
            pdf_path,
            ["主要供应商", "主要客户", "供应商", "客户", "采购", "销售"],
            max_pages,
        )

    async def fetch_segment_text(self, code: str, max_pages: int = 30) -> str:
        """下载年报 PDF 并提取分部信息章节,供 SOTP 拆解使用"""
        pdf_path = await self._download_latest_annual_report(code)
        if not pdf_path:
            return ""
        return await asyncio.to_thread(self._extract_segment_text, pdf_path, max_pages)

    def _extract_segment_text(self, pdf_path: Path, max_pages: int) -> str:
        """从 PDF 中提取分部信息(营收按业务/行业/产品/地区拆分)"""
        return self._extract_text_by_keywords(
            pdf_path,
            ["分行业", "分产品", "分地区", "分部信息", "经营情况分析",
             "营业收入构成", "主营业务收入", "业务板块", "营业利润"],
            max_pages,
            max_chars=12000,  # 分部数据需要更多上下文
        )

    def _extract_text_by_keywords(
        self, pdf_path: Path, target_keywords: list[str],
        max_pages: int, max_chars: int = 8000,
    ) -> str:
        """通用 PDF 关键词章节提取器(供应链/分部信息共用)"""
        try:
            import fitz  # PyMuPDF

            doc = fitz.open(str(pdf_path))
            extracted = []
            pages_found = 0

            for page_num in range(len(doc)):
                if pages_found >= max_pages:
                    break
                page = doc.load_page(page_num)
                text = page.get_text()
                if any(kw in text for kw in target_keywords):
                    extracted.append(text)
                    pages_found += 1

            doc.close()
            return "\n\n".join(extracted)[:max_chars]
        except Exception as e:
            logger.error(f"PDF 文本提取失败: {e}")
            return ""
