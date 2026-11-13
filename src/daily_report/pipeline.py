"""主编排：单成员流水线、全员流水线与团队汇总推送。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from daily_report.audit import AuditService
from daily_report.collectors.base import Collector, TimeWindow, collect_all
from daily_report.db import Database
from daily_report.generation.attribution import attribute
from daily_report.generation.builder import build_report, render_markdown
from daily_report.generation.llm import LLMProvider
from daily_report.generation.validator import validate_draft
from daily_report.publishers.base import Publisher, PushPayload, deliver
from daily_report.repositories import (
    MemberRepository,
    PipelineRunRepository,
    ReportRepository,
    TeamRepository,
    WorkEventRepository,
)
from daily_report.rollup import TeamDigest, build_team_digest


def day_window(target: date) -> TimeWindow:
    start = datetime.combine(target, time.min)
    return TimeWindow(since=start, until=start + timedelta(days=1))


@dataclass
class PipelineResult:
    status: str
    member_id: int
    report_id: int | None = None
    events: int = 0
    inserted: int = 0
    removed: int = 0
    degraded: bool = False
    pushed: bool = False
    error: str | None = None


@dataclass
class DailyResult:
    status: str
    report_date: str
    results: list[PipelineResult] = field(default_factory=list)


class PipelineService:
    def __init__(
        self,
        database: Database,
        collectors: Sequence[Collector],
        publisher: Publisher,
        *,
        provider: LLMProvider | None = None,
        concurrency: int = 3,
    ) -> None:
        self.db = database
        self.collectors = list(collectors)
        self.publisher = publisher
        self.provider = provider
        self.concurrency = concurrency

    async def run_member_pipeline(self, member_id: int, report_date: date) -> PipelineResult:
        date_str = report_date.isoformat()
        run_key = f"{date_str}:member:{member_id}"

        with self.db.session() as session:
            runs = PipelineRunRepository(session)
            existing = runs.get(run_key)
            if existing is not None and existing.status == "success":
                return PipelineResult(status="skipped", member_id=member_id)
            runs.start(run_key, date_str)

        try:
            with self.db.session() as session:
                members = MemberRepository(session)
                member = members.get(member_id)
                if member is None:
                    raise ValueError(f"member not found: {member_id}")

                reports = ReportRepository(session)
                report = reports.get(member_id, date_str)
                if report is not None and report.status in {"submitted", "pushed"}:
                    runs = PipelineRunRepository(session)
                    runs.finish(runs.start(run_key, date_str), "success", {"skipped": True})
                    return PipelineResult(
                        status="skipped", member_id=member_id, report_id=report.id
                    )

                window = day_window(report_date)
                results = await collect_all(
                    self.collectors, member, window, concurrency=self.concurrency
                )
                events = [event for result in results.values() for event in result.events]
                events = [
                    event
                    for event in events
                    if window.since <= event.occurred_at < window.until
                ]

                work_events = WorkEventRepository(session)
                inserted = work_events.upsert_many(member.id, [e.as_row() for e in events])
                id_map = work_events.id_map((e.source, e.source_id) for e in events)
                for event in events:
                    event.db_id = id_map.get((event.source, event.source_id))

                attributions = attribute(events, member.open_id)
                draft = await build_report(
                    member.id, date_str, attributions, self.provider
                )
                validation = validate_draft(draft)
                items = [
                    {
                        "section": item.section,
                        "content": item.content,
                        "source_event_ids": item.source_event_ids,
                        "confidence": item.confidence,
                        "confirmed": item.status == "auto",
                    }
                    for section in validation.draft.sections.values()
                    for item in section
                ]

                report = reports.ensure(member.id, date_str)
                reports.replace_items(report, items)

                pushed = False
                if items:
                    payload = PushPayload(
                        title=f"日报草稿（{date_str}）",
                        content_md=render_markdown(validation.draft),
                        report_id=report.id,
                        target_type="user",
                        target_id=member.open_id,
                    )
                    push_result = await deliver(
                        self.publisher,
                        session,
                        payload,
                        idempotency_key=f"draft:{report.id}:{report.version}",
                    )
                    pushed = push_result.success

                runs = PipelineRunRepository(session)
                run_status = "success" if pushed or not items else "partial"
                runs.finish(
                    runs.start(run_key, date_str),
                    run_status,
                    {
                        "events": len(events),
                        "inserted": inserted,
                        "items": len(items),
                        "removed": validation.removed,
                        "degraded": draft.degraded,
                        "pushed": pushed,
                    },
                )
                return PipelineResult(
                    status=run_status,
                    member_id=member_id,
                    report_id=report.id,
                    events=len(events),
                    inserted=inserted,
                    removed=validation.removed,
                    degraded=draft.degraded,
                    pushed=pushed,
                )
        except Exception as exc:  # noqa: BLE001 - 失败要落库并返回
            with self.db.session() as session:
                runs = PipelineRunRepository(session)
                run = runs.get(run_key) or runs.start(run_key, date_str)
                runs.finish(run, "failed", {"error": type(exc).__name__, "message": str(exc)})
            return PipelineResult(status="failed", member_id=member_id, error=str(exc))

    async def run_daily_pipeline(
        self, report_date: date, team_id: int | None = None
    ) -> DailyResult:
        with self.db.session() as session:
            if team_id is not None:
                member_ids = TeamRepository(session).member_ids(team_id)
            else:
                member_ids = [member.id for member in MemberRepository(session).list_active()]

        results = [
            await self.run_member_pipeline(member_id, report_date) for member_id in member_ids
        ]
        if not results or all(
            result.status in {"success", "skipped"} for result in results
        ):
            status = "success"
        elif all(result.status == "failed" for result in results):
            status = "failed"
        else:
            status = "partial"

        date_str = report_date.isoformat()
        run_key = f"{date_str}:daily:{team_id or 'all'}"
        with self.db.session() as session:
            runs = PipelineRunRepository(session)
            runs.finish(
                runs.start(run_key, date_str),
                status,
                {
                    "members": len(results),
                    "failed": sum(1 for result in results if result.status == "failed"),
                },
            )
        return DailyResult(status=status, report_date=date_str, results=results)

    async def run_team_rollup(self, team_id: int, report_date: date) -> TeamDigest:
        date_str = report_date.isoformat()
        with self.db.session() as session:
            digest = build_team_digest(session, team_id, date_str)
            team = TeamRepository(session).get(team_id)
            lead = (
                MemberRepository(session).get(team.lead_member_id)
                if team and team.lead_member_id
                else None
            )
            if lead is not None and digest.submitted_count > 0:
                payload = PushPayload(
                    title=f"团队日报（{date_str}）",
                    content_md=digest.content_md,
                    report_id=0,
                    target_type="user",
                    target_id=lead.open_id,
                )
                await self.publisher.publish(payload, f"digest:{team_id}:{date_str}")
            AuditService(session).log(
                action="team_rollup",
                object_type="team",
                object_id=team_id,
                detail={"date": date_str, "submitted": digest.submitted_count},
            )
            return digest
