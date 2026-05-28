from types import SimpleNamespace

import pytest

from app.schemas.stock import StockCreate


class FakeDb:
    def __init__(self, calls: list[str]):
        self.calls = calls

    async def commit(self):
        self.calls.append("commit")

    async def refresh(self, _stock):
        self.calls.append("refresh")


@pytest.mark.asyncio
async def test_add_watchlist_commits_before_backfill_trigger(monkeypatch):
    from app.api.v1.endpoints import stocks as endpoint
    from app.services import stock_service

    calls: list[str] = []
    stock = SimpleNamespace(code="688200", market="A", data_ready=False)

    async def fake_add(_db, _payload):
        calls.append("add")
        return stock

    def fake_trigger(code: str, market: str) -> str:
        calls.append(f"trigger:{code}:{market}")
        return "task-123"

    async def fake_mark_pending(_db, code: str, task_id: str | None = None):
        calls.append(f"pending:{code}:{task_id}")

    monkeypatch.setattr(stock_service, "add_to_watchlist", fake_add)
    monkeypatch.setattr(stock_service, "trigger_backfill", fake_trigger)
    monkeypatch.setattr(stock_service, "mark_sync_pending", fake_mark_pending)

    result = await endpoint.add_to_watchlist(
        StockCreate(code="688200", market="A", name="华峰测控"),
        FakeDb(calls),
    )

    assert result is stock
    assert calls == [
        "add",
        "commit",
        "refresh",
        "trigger:688200:A",
        "pending:688200:task-123",
        "commit",
        "refresh",
    ]


@pytest.mark.asyncio
async def test_add_watchlist_does_not_requeue_ready_stock(monkeypatch):
    from app.api.v1.endpoints import stocks as endpoint
    from app.services import stock_service

    calls: list[str] = []
    stock = SimpleNamespace(code="688200", market="A", data_ready=True)

    async def fake_add(_db, _payload):
        calls.append("add")
        return stock

    def fake_trigger(_code: str, _market: str) -> str:
        calls.append("trigger")
        return "task-should-not-run"

    monkeypatch.setattr(stock_service, "add_to_watchlist", fake_add)
    monkeypatch.setattr(stock_service, "trigger_backfill", fake_trigger)

    result = await endpoint.add_to_watchlist(
        StockCreate(code="688200", market="A", name="华峰测控"),
        FakeDb(calls),
    )

    assert result is stock
    assert calls == ["add", "commit", "refresh"]


def test_backfill_and_repair_tasks_route_to_data_queue():
    from app.tasks.celery_app import celery_app

    routes = celery_app.conf.task_routes
    assert routes["app.tasks.data_tasks.backfill_stock_data"]["queue"] == "data"
    assert routes["app.tasks.data_tasks.repair_watchlist_sync_gaps"]["queue"] == "data"


def test_stock_read_exposes_sync_status_fields():
    from datetime import datetime, timezone

    from app.schemas.stock import StockRead

    row = StockRead(
        id=1,
        code="688200",
        market="A",
        name="华峰测控",
        is_watchlist=True,
        is_core=False,
        data_ready=False,
        sync_status="pending",
        sync_task_id="task-123",
        sync_error=None,
        sync_started_at=None,
        sync_completed_at=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    assert row.sync_status == "pending"
    assert row.sync_task_id == "task-123"
