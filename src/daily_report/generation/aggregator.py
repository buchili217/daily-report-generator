"""聚合：时间窗过滤、去重与稳定排序。"""

from __future__ import annotations

from collections.abc import Iterable

from daily_report.collectors.base import CollectedEvent, TimeWindow


def aggregate(
    events: Iterable[CollectedEvent], window: TimeWindow | None = None
) -> list[CollectedEvent]:
    seen: set[tuple[str, str]] = set()
    result: list[CollectedEvent] = []
    for event in events:
        if window is not None and not (window.since <= event.occurred_at < window.until):
            continue
        key = (event.source, event.source_id)
        if key in seen:
            continue
        seen.add(key)
        result.append(event)
    return sorted(result, key=lambda event: (event.occurred_at, event.source, event.source_id))
