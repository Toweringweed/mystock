"""规则层打分器

输出 0~1 的 rule_score。低于阈值（默认 0.3）的资讯直接丢弃，不进 LLM。

公式：
  rule_score =
    0.4 × 公告类型权重(title)
  + 0.2 × 消息源权威度(source)
  + 0.2 × 时间敏感词命中(title+content)
  + 0.2 × 数字/百分比命中

紧急关键词单独标记，由 urgency_classifier 使用。
"""
import re

from app.services.news_crawler.base_crawler import SOURCE_AUTHORITY

LLM_THRESHOLD = 0.3  # 低于此值的资讯不进 LLM

# 公告类型权重表
ANNOUNCEMENT_WEIGHTS: list[tuple[str, float]] = [
    # 1.0 级（紧急）
    ("停牌", 1.0), ("复牌", 1.0), ("退市", 1.0), ("ST", 1.0), ("*ST", 1.0),
    ("被收购", 1.0), ("要约收购", 1.0), ("重大违规", 1.0), ("立案调查", 1.0),
    ("破产", 1.0), ("重组失败", 1.0),
    # 0.9 级
    ("业绩预告", 0.9), ("业绩快报", 0.9), ("年度报告", 0.9), ("年报", 0.9),
    ("半年报", 0.9), ("半年度报告", 0.9), ("亏损", 0.9), ("扭亏", 0.9),
    ("预亏", 0.9), ("预增", 0.9), ("超预期", 0.9), ("不及预期", 0.9),
    # 0.8 级
    ("重大合同", 0.8), ("中标", 0.8), ("股东减持", 0.8), ("股东增持", 0.8),
    ("回购", 0.8), ("分红", 0.8), ("股权激励", 0.8), ("定增", 0.8),
    ("可转债", 0.8),
    # 0.6 级
    ("一季报", 0.6), ("三季报", 0.6), ("季度报告", 0.6), ("机构调研", 0.6),
    ("调研", 0.6), ("公告", 0.6), ("股东大会", 0.6),
    # 0.4 级
    ("行业", 0.4), ("政策", 0.4),
]

# 紧急词表（独立判断 urgent，不受总分影响）
URGENT_KEYWORDS = [
    "停牌", "复牌", "退市", "ST", "*ST", "被收购", "要约收购",
    "重大违规", "立案调查", "破产", "重组失败", "黑天鹅",
]

# 时间敏感词
TIME_SENSITIVE_KEYWORDS = [
    "今日", "今天", "立即", "紧急", "停牌", "复牌", "暂停", "警示",
    "重大", "突发", "刚刚", "最新",
]

# 数字命中（金额/百分比）
_NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?[%％]|\d+(?:\.\d+)?\s*[亿万千]")


def announcement_weight(title: str) -> float:
    """返回公告类型最高匹配权重；未命中返回 0"""
    if not title:
        return 0.0
    max_w = 0.0
    for kw, w in ANNOUNCEMENT_WEIGHTS:
        if kw in title:
            if w > max_w:
                max_w = w
    return max_w


def time_sensitive_score(text: str) -> float:
    """命中任一时间敏感词记 1.0，未命中 0"""
    if not text:
        return 0.0
    for kw in TIME_SENSITIVE_KEYWORDS:
        if kw in text:
            return 1.0
    return 0.0


def number_hit_score(text: str) -> float:
    """命中数字/百分比记 1.0"""
    if not text:
        return 0.0
    return 1.0 if _NUMBER_PATTERN.search(text) else 0.0


def has_urgent_keyword(title: str) -> bool:
    """是否命中紧急关键词（用于强制 urgent 分级）"""
    if not title:
        return False
    return any(kw in title for kw in URGENT_KEYWORDS)


def score(
    *,
    title: str,
    content: str | None,
    source: str,
    source_authority: float | None = None,
) -> float:
    """计算 rule_score（0~1）"""
    text = f"{title or ''} {content or ''}"
    authority = source_authority if source_authority is not None else SOURCE_AUTHORITY.get(source, 0.5)

    a = announcement_weight(title or "")
    b = authority
    c = time_sensitive_score(text)
    d = number_hit_score(text)

    s = 0.4 * a + 0.2 * b + 0.2 * c + 0.2 * d
    return round(min(1.0, max(0.0, s)), 4)
