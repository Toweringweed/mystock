"""紧急级分类器

  urgent    = importance_score ≥ 0.8 OR title 命中紧急关键词
  important = 0.5 ≤ importance_score < 0.8
  info      = importance_score < 0.5
"""
from app.services.news_filter.rule_scorer import has_urgent_keyword

URGENT_THRESHOLD = 0.8
IMPORTANT_THRESHOLD = 0.5


def classify(*, importance_score: float | None, title: str | None) -> str:
    """返回 urgent / important / info"""
    if title and has_urgent_keyword(title):
        return "urgent"
    s = importance_score or 0.0
    if s >= URGENT_THRESHOLD:
        return "urgent"
    if s >= IMPORTANT_THRESHOLD:
        return "important"
    return "info"
