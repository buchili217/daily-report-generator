"""飞书开放平台采集器：日历、云文档、任务。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from daily_report.collectors.base import (
    CollectedEvent,
    CollectResult,
    Participant,
    TimeWindow,
)
from daily_report.feishu_api import FeishuApi
from daily_report.models import Member


def _from_ms(value: Any) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=UTC).replace(tzinfo=None)
    except (TypeError, ValueError, OSError):
        return None


def _first_open_id(item: dict[str, Any]) -> str | None:
    for key in ("open_id", "user_id", "union_id"):
        value = item.get(key)
        if isinstance(value, str) and value:
            return value
    nested = item.get("attendee_id") or item.get("id")
    if isinstance(nested, dict):
        return _first_open_id(nested)
    if isinstance(nested, str) and nested:
        return nested
    return None


class FeishuCalendarCollector:
    source = "feishu_calendar"

    def __init__(self, api: FeishuApi) -> None:
        self._api = api

    async def collect(self, member: Member, window: TimeWindow) -> CollectResult:
        body = await self._api.get(
            "/open-apis/calendar/v4/calendars/primary/events",
            params={
                "start_time": int(window.since.timestamp()),
                "end_time": int(window.until.timestamp()),
                "page_size": 100,
            },
        )
        data = body.get("data", {})
        events: list[CollectedEvent] = []
        for item in data.get("items", []):
            occurred = _from_ms((item.get("start_time") or {}).get("timestamp")) or window.since
            participants: list[Participant] = []
            for attendee in item.get("attendees") or []:
                open_id = _first_open_id(attendee)
                if open_id and open_id != member.open_id:
                    participants.append(
                        Participant(open_id=open_id, role="attendee", confidence=0.6)
                    )
            events.append(
                CollectedEvent(
                    source=self.source,
                    source_id=str(item.get("event_id") or item.get("uid")),
                    event_type="meeting",
                    owner_open_id=member.open_id,
                    occurred_at=occurred,
                    title=item.get("summary") or "日程",
                    summary=item.get("description"),
                    url=item.get("app_link"),
                    confidence=0.9,
                    payload={"attendee_count": len(participants)},
                    participants=participants,
                )
            )
        return CollectResult(
            source=self.source, events=events, next_cursor=data.get("page_token")
        )


class FeishuDocCollector:
    source = "feishu_doc"

    def __init__(self, api: FeishuApi) -> None:
        self._api = api

    async def collect(self, member: Member, window: TimeWindow) -> CollectResult:
        body = await self._api.get(
            "/open-apis/drive/v1/files",
            params={"page_size": 100, "order_by": "EditedTime", "direction": "DESC"},
        )
        data = body.get("data", {})
        events: list[CollectedEvent] = []
        for item in data.get("files", []):
            modified = _from_ms(item.get("modified_time"))
            if modified is None or not (window.since <= modified < window.until):
                continue
            events.append(
                CollectedEvent(
                    source=self.source,
                    source_id=str(item.get("token")),
                    event_type="doc_edit",
                    owner_open_id=member.open_id,
                    occurred_at=modified,
                    title=item.get("name") or "云文档",
                    summary=f"文档类型：{item.get('type', 'docx')}",
                    url=item.get("url"),
                    confidence=1.0,
                    payload={"type": item.get("type")},
                )
            )
        return CollectResult(
            source=self.source, events=events, next_cursor=data.get("next_page_token")
        )


class FeishuTaskCollector:
    source = "feishu_task"

    def __init__(self, api: FeishuApi) -> None:
        self._api = api

    async def collect(self, member: Member, window: TimeWindow) -> CollectResult:
        body = await self._api.get(
            "/open-apis/task/v2/tasks",
            params={"page_size": 100, "completed": "false"},
        )
        data = body.get("data", {})
        events: list[CollectedEvent] = []
        for item in data.get("items", []):
            updated = _from_ms(item.get("updated_at") or item.get("completed_at"))
            if updated is None or not (window.since <= updated < window.until):
                continue
            participants = [
                Participant(open_id=str(entry.get("id")), role="collaborator", confidence=0.6)
                for entry in item.get("members") or []
                if entry.get("id") and entry.get("id") != member.open_id
            ]
            events.append(
                CollectedEvent(
                    source=self.source,
                    source_id=str(item.get("guid") or item.get("id")),
                    event_type="task_update",
                    owner_open_id=member.open_id,
                    occurred_at=updated,
                    title=item.get("summary") or "任务更新",
                    summary=f"任务状态：{item.get('status', 'updated')}",
                    url=item.get("url"),
                    confidence=1.0,
                    payload={"status": item.get("status")},
                    participants=participants,
                )
            )
        return CollectResult(
            source=self.source, events=events, next_cursor=data.get("page_token")
        )
