"""Mock 采集器：无外部凭证时提供可复现的演示数据。"""

from __future__ import annotations

from datetime import datetime, timedelta

from daily_report.collectors.base import (
    CollectedEvent,
    CollectResult,
    Participant,
    TimeWindow,
)
from daily_report.models import Member


class _MockCollector:
    source = "mock"

    async def collect(self, member: Member, window: TimeWindow) -> CollectResult:
        raise NotImplementedError


class MockCalendarCollector(_MockCollector):
    source = "feishu_calendar"

    async def collect(self, member: Member, window: TimeWindow) -> CollectResult:
        start = window.since.replace(hour=10, minute=0, second=0, microsecond=0)
        event = CollectedEvent(
            source=self.source,
            source_id=f"cal-{member.open_id}-{start.date().isoformat()}",
            event_type="meeting",
            owner_open_id=member.open_id,
            occurred_at=start,
            title="团队周会",
            summary="同步本周进展与阻塞项",
            confidence=0.9,
            participants=[
                Participant(open_id="ou_lead", role="attendee", confidence=0.6),
            ],
        )
        return CollectResult(source=self.source, events=[event])


class MockDocCollector(_MockCollector):
    source = "feishu_doc"

    async def collect(self, member: Member, window: TimeWindow) -> CollectResult:
        start = window.since.replace(hour=14, minute=0, second=0, microsecond=0)
        event = CollectedEvent(
            source=self.source,
            source_id=f"doc-{member.open_id}-{start.date().isoformat()}",
            event_type="doc_edit",
            owner_open_id=member.open_id,
            occurred_at=start,
            title="日报生成器接口设计文档",
            summary="补充采集层与生成层接口约定",
            url="https://example.feishu.cn/docx/mock",
            confidence=1.0,
            participants=[
                Participant(open_id="ou_peer", role="collaborator", confidence=0.6),
            ],
        )
        return CollectResult(source=self.source, events=[event])


class MockTaskCollector(_MockCollector):
    source = "feishu_task"

    async def collect(self, member: Member, window: TimeWindow) -> CollectResult:
        start = window.since.replace(hour=16, minute=0, second=0, microsecond=0)
        event = CollectedEvent(
            source=self.source,
            source_id=f"task-{member.open_id}-{start.date().isoformat()}",
            event_type="task_update",
            owner_open_id=member.open_id,
            occurred_at=start,
            title="修复登录回调缺陷",
            summary="任务状态：已完成",
            confidence=1.0,
            payload={"status": "done"},
        )
        return CollectResult(source=self.source, events=[event])


class MockGitHubCollector(_MockCollector):
    source = "github"

    async def collect(self, member: Member, window: TimeWindow) -> CollectResult:
        start = window.since.replace(hour=15, minute=0, second=0, microsecond=0)
        event = CollectedEvent(
            source=self.source,
            source_id=f"commit-{member.open_id}-{start.date().isoformat()}",
            event_type="commit",
            owner_open_id=member.open_id,
            occurred_at=start,
            title="feat: 日报生成流水线",
            summary="实现采集→生成→推送编排",
            url="https://github.com/example/repo/commit/mock",
            confidence=1.0,
            payload={"repo": "example/repo"},
        )
        return CollectResult(source=self.source, events=[event])


class MockFailOnceCollector(_MockCollector):
    """故障注入用：首次调用抛错，用于验证单源失败隔离。"""

    source = "mock_fail"

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error or RuntimeError("mock collector failed")

    async def collect(self, member: Member, window: TimeWindow) -> CollectResult:
        raise self.error


def build_mock_collectors() -> list[_MockCollector]:
    return [
        MockCalendarCollector(),
        MockDocCollector(),
        MockTaskCollector(),
        MockGitHubCollector(),
    ]


def empty_window(day: datetime) -> TimeWindow:
    start = day.replace(hour=0, minute=0, second=0, microsecond=0)
    return TimeWindow(since=start, until=start + timedelta(days=1))
