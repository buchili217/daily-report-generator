from __future__ import annotations

from datetime import date

from daily_report.collectors.base import CollectResult
from daily_report.collectors.mock import MockGitHubCollector
from daily_report.db import Database
from daily_report.errors import AppError, ErrorCode
from daily_report.generation.llm import FakeProvider
from daily_report.pipeline import PipelineService
from daily_report.publishers.base import PushResult, RecordingPublisher
from daily_report.repositories import PushRecordRepository, ReportRepository

DAY = date(2026, 11, 11)


class FailingPublisher:
    channel = "feishu"

    async def publish(self, payload, idempotency_key: str) -> PushResult:
        return PushResult(success=False, error_code="E-PUSH-002")


class UnauthorizedCollector:
    source = "github"

    async def collect(self, member, window) -> CollectResult:
        raise AppError(ErrorCode.COL_AUTH, "token expired")


async def test_collector_error_does_not_block_pipeline(
    database: Database, seeded: tuple[int, int]
) -> None:
    member_id, _ = seeded
    service = PipelineService(
        database,
        [UnauthorizedCollector(), MockGitHubCollector()],
        RecordingPublisher(),
    )
    result = await service.run_member_pipeline(member_id, DAY)
    assert result.status == "success"
    assert result.events == 1
    assert result.pushed is True


async def test_empty_collection_creates_report_but_no_push(
    database: Database, seeded: tuple[int, int]
) -> None:
    member_id, _ = seeded
    service = PipelineService(database, [], RecordingPublisher())
    result = await service.run_member_pipeline(member_id, DAY)
    assert result.status == "success"
    assert result.events == 0
    assert result.pushed is False
    with database.session() as session:
        report = ReportRepository(session).get(member_id, DAY.isoformat())
        assert report is not None
        assert ReportRepository(session).items(report.id) == []


async def test_push_failure_marks_partial(
    database: Database, seeded: tuple[int, int]
) -> None:
    member_id, _ = seeded
    service = PipelineService(
        database,
        [MockGitHubCollector()],
        FailingPublisher(),
    )
    result = await service.run_member_pipeline(member_id, DAY)
    assert result.status == "partial"
    assert result.pushed is False
    with database.session() as session:
        report = ReportRepository(session).get(member_id, DAY.isoformat())
        record = PushRecordRepository(session).get(report.id, "feishu", "user", "ou_1")
        assert record is not None and record.status == "failed"


async def test_llm_failure_degrades_but_delivers(
    database: Database, seeded: tuple[int, int]
) -> None:
    member_id, _ = seeded
    service = PipelineService(
        database,
        [MockGitHubCollector()],
        RecordingPublisher(),
        provider=FakeProvider(error=RuntimeError("llm down")),
    )
    result = await service.run_member_pipeline(member_id, DAY)
    assert result.status == "success"
    assert result.degraded is True
    assert result.pushed is True


async def test_repeated_push_is_idempotent(
    database: Database, seeded: tuple[int, int]
) -> None:
    member_id, _ = seeded
    publisher = RecordingPublisher()
    service = PipelineService(database, [MockGitHubCollector()], publisher)
    await service.run_member_pipeline(member_id, DAY)
    await service.run_member_pipeline(member_id, DAY)
    assert len(publisher.payloads) == 1
