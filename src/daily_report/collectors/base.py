"""采集层契约：统一时间窗、事件结构与失败隔离。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from daily_report.models import Member


@dataclass(frozen=True)
class TimeWindow:
    since: datetime
    until: datetime


@dataclass
class Participant:
    open_id: str
    role: str
    confidence: float


@dataclass
class CollectedEvent:
    source: str
    source_id: str
    event_type: str
    owner_open_id: str
    occurred_at: datetime
    title: str
    summary: str | None = None
    url: str | None = None
    confidence: float = 1.0
    payload: dict[str, Any] = field(default_factory=dict)
    participants: list[Participant] = field(default_factory=list)
    db_id: int | None = None

    def as_row(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "source_id": self.source_id,
            "event_type": self.event_type,
            "occurred_at": self.occurred_at,
            "title": self.title,
            "summary": self.summary,
            "url": self.url,
            "confidence": self.confidence,
            "payload": self.payload,
        }


@dataclass
class CollectError:
    source: str
    code: str
    message: str


@dataclass
class CollectResult:
    source: str
    events: list[CollectedEvent] = field(default_factory=list)
    next_cursor: str | None = None
    next_etag: str | None = None
    next_etags: dict[str, str] = field(default_factory=dict)
    errors: list[CollectError] = field(default_factory=list)


@runtime_checkable
class Collector(Protocol):
    source: str

    async def collect(self, member: Member, window: TimeWindow) -> CollectResult: ...


async def collect_all(
    collectors: list[Collector],
    member: Member,
    window: TimeWindow,
    *,
    concurrency: int = 3,
) -> dict[str, CollectResult]:
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def run(collector: Collector) -> CollectResult:
        async with semaphore:
            try:
                return await collector.collect(member, window)
            except Exception as exc:  # noqa: BLE001 - 单源失败必须隔离
                code = getattr(exc, "code", "E-COL-999")
                error = CollectError(
                    source=collector.source, code=str(code), message=str(exc)
                )
                return CollectResult(source=collector.source, errors=[error])

    results = await asyncio.gather(*(run(collector) for collector in collectors))
    return {result.source: result for result in results}
