from datetime import date, datetime, time

from app.services.news_crawler.cailianshe_crawler import CailiansheCrawler


def test_parse_published_at_from_cls_date_and_time_columns():
    crawler = CailiansheCrawler()

    parsed = crawler._parse_published_at({
        "发布日期": date(2026, 6, 4),
        "发布时间": time(9, 30, 5),
    })

    assert parsed == datetime(2026, 6, 4, 9, 30, 5)


def test_parse_published_at_from_cls_string_columns():
    crawler = CailiansheCrawler()

    parsed = crawler._parse_published_at({
        "发布日期": "2026-06-04",
        "发布时间": "09:30:05",
    })

    assert parsed == datetime(2026, 6, 4, 9, 30, 5)
