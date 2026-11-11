from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from daily_report.collectors.base import TimeWindow
from daily_report.collectors.feishu import (
    FeishuApi,
    FeishuCalendarCollector,
    FeishuDocCollector,
    FeishuTaskCollector,
)
from daily_report.errors import AppError, ErrorCode
from daily_report.http import HttpClient, make_client
from daily_report.models import Member

WINDOW = TimeWindow(datetime(2026, 11, 11), datetime(2026, 11, 12))
MEMBER = Member(id=1, open_id="ou_1", name="张三", email="z@example.com")

MS = int(datetime(2026, 11, 11, 10, 0, tzinfo=UTC).timestamp() * 1000)


def _api(handler) -> tuple[HttpClient, FeishuApi]:
    http = HttpClient(make_client(transport=httpx.MockTransport(handler)))
    return http, FeishuApi(http, app_id="a", app_secret="b", base_url="https://feishu.test")


def _token(request: httpx.Request) -> httpx.Response | None:
    if request.url.path.endswith("tenant_access_token/internal"):
        return httpx.Response(200, json={"code": 0, "tenant_access_token": "t", "expire": 7200})
    return None


async def test_calendar_collector_parses_events() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        early = _token(request)
        if early:
            return early
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "items": [
                        {
                            "event_id": "evt-1",
                            "summary": "周会",
                            "start_time": {"timestamp": str(MS)},
                            "attendees": [
                                {"attendee_id": {"open_id": "ou_2"}},
                                {"attendee_id": {"open_id": "ou_1"}},
                            ],
                        }
                    ]
                },
            },
        )

    http, api = _api(handler)
    async with http.client:
        result = await FeishuCalendarCollector(api).collect(MEMBER, WINDOW)
    assert len(result.events) == 1
    event = result.events[0]
    assert event.title == "周会"
    assert event.occurred_at == datetime(2026, 11, 11, 10, 0)
    assert [p.open_id for p in event.participants] == ["ou_2"]


async def test_doc_collector_filters_window() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        early = _token(request)
        if early:
            return early
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "files": [
                        {"token": "d1", "name": "接口文档", "modified_time": str(MS)},
                        {"token": "d2", "name": "旧文档", "modified_time": "1"},
                    ]
                },
            },
        )

    http, api = _api(handler)
    async with http.client:
        result = await FeishuDocCollector(api).collect(MEMBER, WINDOW)
    assert [event.source_id for event in result.events] == ["d1"]


async def test_task_collector_reads_updates() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        early = _token(request)
        if early:
            return early
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "items": [
                        {
                            "guid": "task-1",
                            "summary": "修复缺陷",
                            "status": "done",
                            "updated_at": str(MS),
                            "members": [{"id": "ou_2", "role": "assignee"}],
                        }
                    ]
                },
            },
        )

    http, api = _api(handler)
    async with http.client:
        first = await FeishuTaskCollector(api).collect(MEMBER, WINDOW)
        second = await FeishuTaskCollector(api).collect(MEMBER, WINDOW)
    assert first.events[0].source_id == second.events[0].source_id == "task-1"
    assert first.events[0].participants[0].open_id == "ou_2"


async def test_unauthorized_raises_col_auth() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        early = _token(request)
        if early:
            return early
        return httpx.Response(401, json={"code": 99991663, "msg": "invalid token"})

    http, api = _api(handler)
    async with http.client:
        with pytest.raises(AppError) as exc:
            await FeishuCalendarCollector(api).collect(MEMBER, WINDOW)
    assert exc.value.code == ErrorCode.COL_AUTH
