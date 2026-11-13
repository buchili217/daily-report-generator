from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from daily_report.collectors.base import TimeWindow, collect_all
from daily_report.collectors.mock import (
    MockFailOnceCollector,
    build_mock_collectors,
    empty_window,
)
from daily_report.models import Member


@pytest.fixture()
def member() -> Member:
    return Member(id=1, open_id="ou_1", name="张三", email="z@example.com")


def test_mock_collectors_return_events(member: Member) -> None:
    window = empty_window(datetime(2026, 11, 11))
    import asyncio

    results = asyncio.run(collect_all(build_mock_collectors(), member, window))
    assert set(results) == {"feishu_calendar", "feishu_doc", "feishu_task", "github"}
    assert all(len(result.events) == 1 for result in results.values())
    assert all(not result.errors for result in results.values())


def test_collect_all_isolates_failures(member: Member) -> None:
    import asyncio

    window = TimeWindow(datetime(2026, 11, 11), datetime(2026, 11, 12))
    collectors = [*build_mock_collectors(), MockFailOnceCollector()]
    results = asyncio.run(collect_all(collectors, member, window))
    assert results["github"].events
    assert results["mock_fail"].errors
    assert results["mock_fail"].errors[0].code


def test_event_row_shape(member: Member) -> None:
    import asyncio

    window = empty_window(datetime(2026, 11, 11) + timedelta(days=1))
    results = asyncio.run(collect_all(build_mock_collectors(), member, window))
    row = results["github"].events[0].as_row()
    assert row["source"] == "github"
    assert row["occurred_at"] == datetime(2026, 11, 12, 15, 0)
