"""实体匹配器：将一条资讯文本匹配到自选股集合

设计：
- 自选股 ~20 只 × ~10 关键词 = 200 patterns，量级很小，直接子串扫描即可。
- 中文用一字边界（左/右各一字符的简单合并语义判断），英文/代码用 \\b 词边界。
- 输出每个命中的 stock_id 及综合权重（命中次数 × 关键词权重，归一化到 0~1）。
"""
import logging
import re
from dataclasses import dataclass

from app.services.news_filter.keyword_builder import KeywordEntry

logger = logging.getLogger(__name__)


@dataclass
class MatchResult:
    stock_id: int
    relevance: float  # 0~1
    matched_keywords: list[str]


# 纯英文/数字关键词使用 \b 边界
_ASCII_RE = re.compile(r"^[A-Za-z0-9_\.]+$")


def _matches_with_boundary(text: str, keyword: str) -> int:
    """在 text 中计数 keyword 命中次数（中文不强制边界，ASCII 用 \\b）"""
    if not keyword or not text:
        return 0
    if _ASCII_RE.match(keyword):
        # ASCII：词边界
        try:
            pat = re.compile(r"\b" + re.escape(keyword) + r"\b", re.IGNORECASE)
            return len(pat.findall(text))
        except re.error:
            return text.lower().count(keyword.lower())
    # 中文/混合：直接子串计数（短关键词如 "平安" 易误命中，调用方应在 KeywordEntry.weight 上控制）
    return text.count(keyword)


def match(
    text: str,
    keywords_by_stock: dict[int, list[KeywordEntry]],
) -> list[MatchResult]:
    """对单条资讯文本，返回所有命中的 stock_id 列表"""
    if not text:
        return []
    results: list[MatchResult] = []
    text_len = max(1, len(text))
    for stock_id, entries in keywords_by_stock.items():
        score = 0.0
        matched: list[str] = []
        for e in entries:
            count = _matches_with_boundary(text, e.keyword)
            if count > 0:
                # 命中分数 = 关键词权重 × min(count, 3) / 3（防止刷词）
                score += e.weight * min(count, 3) / 3
                matched.append(e.keyword)
        if score > 0:
            # 长文本归一化（避免长文短文不公平）
            relevance = min(1.0, score / max(1.0, text_len / 200))
            # 至少给一个保底分
            relevance = max(relevance, min(score, 1.0) * 0.4)
            results.append(
                MatchResult(
                    stock_id=stock_id,
                    relevance=round(relevance, 4),
                    matched_keywords=matched,
                )
            )
    return results
