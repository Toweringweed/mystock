"""资讯过滤流水线单元测试

不依赖数据库与 LLM；纯函数模块的行为校验。
"""
from app.services.news_filter import dedup, entity_matcher, rule_scorer, urgency_classifier
from app.services.news_filter.keyword_builder import (
    KeywordEntry,
    derive_short_name,
    normalize_code_variants,
)

# ────────────────── keyword_builder ──────────────────

def test_derive_short_name_strips_corporate_suffix():
    assert derive_short_name("中国平安保险(集团)股份有限公司") == "中国平安保险"
    assert derive_short_name("贵州茅台股份有限公司") == "贵州茅台"
    assert derive_short_name("腾讯控股有限公司") == "腾讯"
    # 长度低于 MIN_ALIAS_LEN(2) 的派生结果应被拒绝
    assert derive_short_name("A公司") is None
    # 派生结果与原名相同（无后缀可去）应返回 None
    assert derive_short_name("中国平安") is None


def test_normalize_code_variants_for_hk():
    assert normalize_code_variants("00700", "HK") == ["00700", "700"]
    assert normalize_code_variants("000001", "A") == ["000001"]


# ────────────────── entity_matcher ──────────────────

def test_entity_matcher_chinese_substring_hits_stock():
    keywords = {
        1: [
            KeywordEntry(keyword="平安银行", weight=1.0, source_type="name"),
            KeywordEntry(keyword="000001", weight=1.0, source_type="code"),
        ],
    }
    text = "平安银行发布Q1业绩预告，归母净利润同比增长 5.2%"
    results = entity_matcher.match(text, keywords)
    assert len(results) == 1
    assert results[0].stock_id == 1
    assert results[0].relevance > 0.3
    assert "平安银行" in results[0].matched_keywords


def test_entity_matcher_ascii_word_boundary():
    keywords = {1: [KeywordEntry(keyword="ROE", weight=1.0, source_type="alias:manual")]}
    # ROE 应命中
    assert entity_matcher.match("公司 ROE 创新高", keywords)[0].stock_id == 1
    # 不应误匹配 'BROETHER'
    assert entity_matcher.match("无关词 BROETHER 的句子", keywords) == []


def test_entity_matcher_returns_empty_when_no_hit():
    keywords = {1: [KeywordEntry(keyword="特斯拉", weight=1.0, source_type="name")]}
    assert entity_matcher.match("普通市场新闻", keywords) == []


# ────────────────── dedup ──────────────────

def test_simhash_normalize_strips_punctuation():
    assert dedup.normalize_title("特斯拉 Q1 交付 48 万辆") == "特斯拉q1交付48万辆"
    assert dedup.normalize_title("（紧急）停牌！") == "紧急停牌"


def test_simhash_distinct_titles_have_high_hamming_distance():
    """完全不相干的新闻应在汉明距离上明显高于相似的新闻"""
    h1 = dedup.compute_simhash("贵州茅台发布业绩预告，归母净利润同比增长 5.2%")
    h2 = dedup.compute_simhash("特斯拉宣布全球裁员 10%，影响约 14000 名员工")
    assert h1 is not None and h2 is not None
    # 不相干新闻的距离应明显大于阈值（默认 3）
    assert dedup.hamming_distance(h1, h2) > dedup.HAMMING_THRESHOLD


def test_simhash_identical_titles_have_zero_distance():
    h1 = dedup.compute_simhash("特斯拉Q1交付48万辆")
    h2 = dedup.compute_simhash("特斯拉Q1交付48万辆")
    assert h1 == h2
    assert dedup.hamming_distance(h1, h2) == 0


def test_simhash_returns_none_for_short_input():
    assert dedup.compute_simhash("") is None
    assert dedup.compute_simhash("ab") is None  # 归一化后小于 4 字符


# ────────────────── rule_scorer ──────────────────

def test_rule_scorer_high_for_suspension_announcement():
    s = rule_scorer.score(
        title="某股份有限公司股票停牌核查重大事项",
        content="公司接监管部门要求即日起停牌。",
        source="disclosure_em",
        source_authority=1.0,
    )
    # 停牌(1.0) × 0.4 + 1.0 × 0.2 + 时间敏感(1.0) × 0.2 + 数字(0) × 0.2 = 0.8
    assert s >= 0.7


def test_rule_scorer_low_for_generic_news():
    s = rule_scorer.score(
        title="某行业讨论会顺利召开",
        content="各方嘉宾积极交流",
        source="xueqiu",
        source_authority=0.3,
    )
    assert s < rule_scorer.LLM_THRESHOLD


def test_has_urgent_keyword_detection():
    assert rule_scorer.has_urgent_keyword("XX公司被立案调查")
    assert rule_scorer.has_urgent_keyword("ST 风险警示")
    assert not rule_scorer.has_urgent_keyword("一季度营收增长")


# ────────────────── urgency_classifier ──────────────────

def test_urgency_classifier_urgent_by_keyword():
    # 即使分数低，命中紧急关键词也应判 urgent
    assert urgency_classifier.classify(
        importance_score=0.2, title="XX股份停牌核查"
    ) == "urgent"


def test_urgency_classifier_by_score():
    assert urgency_classifier.classify(importance_score=0.85, title="一般新闻") == "urgent"
    assert urgency_classifier.classify(importance_score=0.6, title="一般新闻") == "important"
    assert urgency_classifier.classify(importance_score=0.2, title="一般新闻") == "info"
    assert urgency_classifier.classify(importance_score=None, title=None) == "info"
