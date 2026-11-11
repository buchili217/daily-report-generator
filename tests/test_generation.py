from __future__ import annotations

import json
from datetime import datetime

import httpx
import pytest

from daily_report.collectors.base import CollectedEvent, Participant, TimeWindow
from daily_report.errors import AppError, ErrorCode
from daily_report.generation.aggregator import aggregate
from daily_report.generation.attribution import attribute
from daily_report.generation.builder import DraftItem, ReportDraft, build_report, template_draft
from daily_report.generation.llm import CachingProvider, DeepSeekProvider, FakeProvider
from daily_report.generation.validator import validate_draft
from daily_report.http import make_client

WINDOW = TimeWindow(datetime(2026, 11, 11), datetime(2026, 11, 12))


def event(
    source_id: str,
    *,
    owner: str = "ou_1",
    occurred: datetime | None = None,
    confidence: float = 1.0,
    event_type: str = "commit",
    participants: list[Participant] | None = None,
    payload: dict | None = None,
    db_id: int | None = 1,
) -> CollectedEvent:
    return CollectedEvent(
        source="github",
        source_id=source_id,
        event_type=event_type,
        owner_open_id=owner,
        occurred_at=occurred or datetime(2026, 11, 11, 9, 0),
        title=f"工作 {source_id}",
        confidence=confidence,
        participants=participants or [],
        payload=payload or {},
        db_id=db_id,
    )


def test_aggregate_dedupes_filters_and_sorts() -> None:
    events = [
        event("b", occurred=datetime(2026, 11, 11, 10, 0)),
        event("a", occurred=datetime(2026, 11, 11, 9, 0)),
        event("a", occurred=datetime(2026, 11, 11, 9, 0)),
        event("out", occurred=datetime(2026, 11, 12)),
    ]
    result = aggregate(events, WINDOW)
    assert [item.source_id for item in result] == ["a", "b"]


def test_attribution_levels() -> None:
    events = [
        event("auto", owner="ou_1", confidence=1.0),
        event(
            "pending",
            owner="ou_2",
            participants=[Participant("ou_1", "collaborator", 0.6)],
        ),
        event(
            "dropped",
            owner="ou_2",
            confidence=0.4,
            participants=[Participant("ou_1", "attendee", 0.4)],
        ),
    ]
    result = attribute(events, "ou_1")
    statuses = {item.event.source_id: item.status for item in result}
    assert statuses == {"auto": "auto", "pending": "pending", "dropped": "dropped"}


def test_template_draft_sections() -> None:
    events = [
        event("done", db_id=1),
        event(
            "doing",
            owner="ou_2",
            db_id=2,
            participants=[Participant("ou_1", "collaborator", 0.6)],
        ),
        event("risk", db_id=3, event_type="task_update", payload={"status": "blocked"}),
    ]
    draft = template_draft(1, "2026-11-11", attribute(events, "ou_1"))
    assert [item.content for item in draft.sections["done"]] == ["工作 done"]
    assert [item.content for item in draft.sections["doing"]] == ["工作 doing"]
    assert [item.content for item in draft.sections["risk"]] == ["工作 risk"]
    assert draft.sections["plan"] == []


async def test_build_report_polishes_with_provider() -> None:
    response = json.dumps({"items": [{"index": 0, "content": "完成接口开发"}]})
    provider = FakeProvider(response=response)
    draft = await build_report(
        1,
        "2026-11-11",
        attribute([event("done")], "ou_1"),
        provider,
    )
    assert draft.sections["done"][0].content == "完成接口开发"
    assert draft.provider_used == "fake"
    assert draft.degraded is False


async def test_build_report_degrades_on_provider_error() -> None:
    provider = FakeProvider(error=RuntimeError("boom"))
    draft = await build_report(1, "2026-11-11", attribute([event("done")], "ou_1"), provider)
    assert draft.degraded is True
    assert draft.sections["done"][0].content == "工作 done"


async def test_build_report_degrades_on_invalid_json() -> None:
    provider = FakeProvider(response="not-json")
    draft = await build_report(1, "2026-11-11", attribute([event("done")], "ou_1"), provider)
    assert draft.degraded is True


def test_validator_removes_items_without_source() -> None:
    draft = ReportDraft(
        member_id=1,
        report_date="2026-11-11",
        sections={
            "done": [DraftItem("有来源", "done", [1])],
            "doing": [DraftItem("无来源", "doing", [])],
            "risk": [DraftItem("手填", "risk", [], manual=True)],
            "plan": [],
        },
    )
    result = validate_draft(draft)
    assert [item.content for item in result.draft.sections["done"]] == ["有来源"]
    assert result.draft.sections["doing"] == []
    assert [item.content for item in result.draft.sections["risk"]] == ["手填"]
    assert result.removed == 1
    assert any(ErrorCode.GEN_NO_SOURCE.value in error for error in result.errors)


async def test_caching_provider_only_calls_once() -> None:
    inner = FakeProvider(response="{}")
    provider = CachingProvider(inner)
    await provider.generate("p", {})
    await provider.generate("p", {})
    assert inner.calls == 1


async def test_deepseek_provider_success_and_failure() -> None:
    def ok_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"choices": [{"message": {"content": '{"items": []}'}}]}
        )

    async with make_client(transport=httpx.MockTransport(ok_handler)) as client:
        provider = DeepSeekProvider(api_key="k", client=client)
        assert await provider.generate("p", {}) == '{"items": []}'

    def fail_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    async with make_client(transport=httpx.MockTransport(fail_handler)) as client:
        provider = DeepSeekProvider(api_key="k", client=client)
        with pytest.raises(AppError) as exc:
            await provider.generate("p", {})
    assert exc.value.code == ErrorCode.GEN_LLM
