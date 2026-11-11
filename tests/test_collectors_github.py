from __future__ import annotations

from datetime import datetime

import httpx
import pytest

from daily_report.collectors.base import TimeWindow
from daily_report.collectors.github import GitHubCollector
from daily_report.errors import AppError, ErrorCode
from daily_report.http import HttpClient, make_client
from daily_report.models import Member

WINDOW = TimeWindow(datetime(2026, 11, 11), datetime(2026, 11, 12))
MEMBER = Member(id=1, open_id="ou_1", name="张三", email="zhangsan@example.com")


def _collector(handler, etags=None) -> tuple[HttpClient, GitHubCollector]:
    http = HttpClient(make_client(transport=httpx.MockTransport(handler)))
    return http, GitHubCollector(
        http,
        token="t",
        repos=["org/repo"],
        api_base="https://github.test",
        etags=etags,
    )


async def test_collects_only_member_commits_and_prs() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/commits"):
            return httpx.Response(
                200,
                headers={"ETag": 'W/"1"'},
                json=[
                    {
                        "sha": "sha1",
                        "html_url": "https://github.test/c1",
                        "commit": {
                            "message": "feat: 日报\n\n详细说明",
                            "author": {
                                "email": "zhangsan@example.com",
                                "date": "2026-11-11T09:00:00Z",
                            },
                        },
                    },
                    {
                        "sha": "sha2",
                        "commit": {
                            "message": "chore: other",
                            "author": {
                                "email": "other@example.com",
                                "date": "2026-11-11T09:30:00Z",
                            },
                        },
                    },
                ],
            )
        return httpx.Response(
            200,
            json=[
                {
                    "number": 7,
                    "title": "feat: PR",
                    "state": "open",
                    "user": {"login": "zhangsan"},
                    "updated_at": "2026-11-11T10:00:00Z",
                    "html_url": "https://github.test/pr/7",
                },
                {
                    "number": 8,
                    "title": "other",
                    "user": {"login": "someone"},
                    "updated_at": "2026-11-11T10:00:00Z",
                },
            ],
        )

    http, collector = _collector(handler)
    async with http.client:
        result = await collector.collect(MEMBER, WINDOW)

    assert {event.source_id for event in result.events} == {"org/repo@sha1", "org/repo#7"}
    assert result.next_etags == {"org/repo": 'W/"1"'}


async def test_etag_304_skips_commits() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/commits"):
            return httpx.Response(304)
        return httpx.Response(200, json=[])

    http, collector = _collector(handler, etags={"org/repo": 'W/"1"'})
    async with http.client:
        result = await collector.collect(MEMBER, WINDOW)

    assert result.events == []
    assert result.next_etags == {"org/repo": 'W/"1"'}
    assert any(path.endswith("/pulls") for path in calls)


async def test_unauthorized_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Bad credentials"})

    http, collector = _collector(handler)
    async with http.client:
        with pytest.raises(AppError) as exc:
            await collector.collect(MEMBER, WINDOW)
    assert exc.value.code == ErrorCode.COL_AUTH
