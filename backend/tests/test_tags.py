"""标签功能单元测试（仅纯函数 / 解析层，不触数据库）"""
from app.services.ai_analyzer.tags_extractor import TagsExtractor
from app.services.tags_service import VALID_CATEGORIES

# ────────── extractor _parse 容错 ──────────

def test_parse_valid_json():
    raw = '{"tags":[{"name":"国产替代","category":"theme","confidence":0.9}]}'
    out = TagsExtractor()._parse(raw)
    assert len(out) == 1
    assert out[0]["name"] == "国产替代"
    assert out[0]["category"] == "theme"
    assert out[0]["confidence"] == 0.9


def test_parse_strips_hash_and_whitespace():
    raw = '{"tags":[{"name":"  #英伟达链  ","category":"industry_chain"}]}'
    out = TagsExtractor()._parse(raw)
    assert len(out) == 1
    assert out[0]["name"] == "英伟达链"


def test_parse_drops_empty_or_too_long_names():
    too_long = "a" * 20
    raw = (
        '{"tags":['
        '{"name":"","category":"theme"},'
        f'{{"name":"{too_long}","category":"theme"}},'
        '{"name":"OK","category":"theme"}'
        ']}'
    )
    out = TagsExtractor()._parse(raw)
    assert [t["name"] for t in out] == ["OK"]


def test_parse_normalizes_invalid_category():
    raw = '{"tags":[{"name":"X","category":"random_garbage"}]}'
    out = TagsExtractor()._parse(raw)
    assert out[0]["category"] == "theme"  # 落回默认


def test_parse_handles_extra_text_around_json():
    raw = "好的，以下是标签：\n{\"tags\":[{\"name\":\"国产替代\",\"category\":\"theme\"}]}\n希望对你有帮助"
    out = TagsExtractor()._parse(raw)
    assert len(out) == 1
    assert out[0]["name"] == "国产替代"


def test_parse_returns_empty_for_invalid_json():
    assert TagsExtractor()._parse("not json at all") == []
    assert TagsExtractor()._parse("") == []


def test_parse_handles_missing_confidence():
    raw = '{"tags":[{"name":"A","category":"theme"}]}'
    out = TagsExtractor()._parse(raw)
    assert out[0]["confidence"] is None


def test_parse_dedupes_keeping_higher_confidence():
    raw = (
        '{"tags":['
        '{"name":"A","category":"theme","confidence":0.5},'
        '{"name":"A","category":"theme","confidence":0.9},'
        '{"name":"B","category":"theme","confidence":0.7}'
        ']}'
    )
    out = TagsExtractor()._parse(raw)
    by_name = {t["name"]: t for t in out}
    assert by_name["A"]["confidence"] == 0.9
    assert by_name["B"]["confidence"] == 0.7


def test_parse_handles_invalid_confidence_type():
    raw = '{"tags":[{"name":"A","category":"theme","confidence":"high"}]}'
    out = TagsExtractor()._parse(raw)
    assert out[0]["confidence"] is None


# ────────── 服务层常量 ──────────

def test_valid_categories_set():
    assert VALID_CATEGORIES == {"theme", "industry_chain", "attribute"}


# ────────── 模型/Schema 可导入 ──────────

def test_models_importable():
    from app.models.tag import StockTag, Tag
    assert Tag.__tablename__ == "tags"
    assert StockTag.__tablename__ == "stock_tags"


def test_schemas_importable():
    from app.schemas.tags import StockTagAttach

    payload = StockTagAttach(name="测试", category="theme")
    assert payload.name == "测试"
    assert payload.category == "theme"


def test_attach_schema_rejects_invalid_category():
    from pydantic import ValidationError

    from app.schemas.tags import StockTagAttach

    try:
        StockTagAttach(name="X", category="bogus")  # type: ignore[arg-type]
    except ValidationError:
        pass
    else:
        raise AssertionError("expected ValidationError for bad category")
