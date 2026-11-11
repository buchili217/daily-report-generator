from __future__ import annotations

from datetime import date

from daily_report.db import Database
from daily_report.pipeline import PipelineService
from daily_report.publishers.base import RecordingPublisher
from daily_report.repositories import (
    PipelineRunRepository,
    PushRecordRepository,
    ReportRepository,
)

DAY = date(2026, 11, 11)


async def test_member_pipeline_generates_report_and_push(
    service: PipelineService, seeded: tuple[int, int]
) -> None:
    member_id, _ = seeded
    result = await service.run_member_pipeline(member_id, DAY)

    assert result.status == "success"
    assert result.events == 4
    assert result.inserted == 4
    assert result.pushed is True
    assert result.report_id is not None

    with service.db.session() as session:
        report = ReportRepository(session).get(member_id, DAY.isoformat())
        assert report is not None
        items = ReportRepository(session).items(report.id)
        assert len(items) == 4
        assert all(item.source_event_ids != "[]" for item in items)
        record = PushRecordRepository(session).get(report.id, "feishu", "user", "ou_1")
        assert record is not None and record.status == "sent"


async def test_member_pipeline_is_idempotent(
    service: PipelineService, seeded: tuple[int, int]
) -> None:
    member_id, _ = seeded
    await service.run_member_pipeline(member_id, DAY)
    with service.db.session() as session:
        reports = ReportRepository(session)
        report = reports.get(member_id, DAY.isoformat())
        first_items = [item.id for item in reports.items(report.id)]

    second = await service.run_member_pipeline(member_id, DAY)
    assert second.status == "skipped"
    with service.db.session() as session:
        reports = ReportRepository(session)
        report = reports.get(member_id, DAY.isoformat())
        assert [item.id for item in reports.items(report.id)] == first_items


async def test_daily_pipeline_runs_all_members(
    service: PipelineService, seeded: tuple[int, int]
) -> None:
    result = await service.run_daily_pipeline(DAY)
    assert result.status == "success"
    assert len(result.results) == 2
    assert all(item.status == "success" for item in result.results)


async def test_pipeline_records_failure(database: Database) -> None:
    service = PipelineService(database, [], RecordingPublisher())
    result = await service.run_member_pipeline(999, DAY)
    assert result.status == "failed"
    assert "member not found" in (result.error or "")
    with database.session() as session:
        run = PipelineRunRepository(session).get(f"{DAY.isoformat()}:member:999")
        assert run is not None and run.status == "failed"


async def test_team_rollup_contains_no_ranking(
    service: PipelineService, seeded: tuple[int, int]
) -> None:
    member_id, team_id = seeded
    await service.run_member_pipeline(member_id, DAY)
    digest = await service.run_team_rollup(team_id, DAY)
    assert digest.member_count == 2
    assert "未提交" in digest.content_md
    assert "排名" in digest.content_md
