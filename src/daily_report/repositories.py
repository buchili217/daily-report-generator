"""仓储层：所有 SQL 与事务边界集中在此，业务层不直接拼 SQL。"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from daily_report.models import (
    Member,
    PipelineRun,
    PushRecord,
    Report,
    ReportItem,
    ReportVersion,
    SyncCursor,
    Team,
    TeamMember,
    WorkEvent,
    utcnow,
)


class MemberRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(
        self,
        *,
        open_id: str,
        name: str,
        email: str | None = None,
        dept: str | None = None,
    ) -> Member:
        member = Member(open_id=open_id, name=name, email=email, dept=dept)
        self.session.add(member)
        self.session.flush()
        return member

    def get(self, member_id: int) -> Member | None:
        return self.session.get(Member, member_id)

    def get_by_open_id(self, open_id: str) -> Member | None:
        return self.session.scalar(select(Member).where(Member.open_id == open_id))

    def list_active(self) -> list[Member]:
        return list(
            self.session.scalars(
                select(Member).where(Member.status == "active").order_by(Member.id)
            )
        )


class TeamRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, *, name: str, lead_member_id: int | None = None) -> Team:
        team = Team(name=name, lead_member_id=lead_member_id)
        self.session.add(team)
        self.session.flush()
        return team

    def get(self, team_id: int) -> Team | None:
        return self.session.get(Team, team_id)

    def list_for_member(self, member_id: int) -> list[tuple[Team, str]]:
        rows = self.session.execute(
            select(Team, TeamMember.role)
            .join(TeamMember, TeamMember.team_id == Team.id)
            .where(TeamMember.member_id == member_id)
            .order_by(Team.id)
        ).all()
        return [(team, role) for team, role in rows]

    def add_member(self, team_id: int, member_id: int, role: str = "member") -> None:
        self.session.add(TeamMember(team_id=team_id, member_id=member_id, role=role))
        self.session.flush()

    def member_ids(self, team_id: int) -> list[int]:
        return list(
            self.session.scalars(
                select(TeamMember.member_id)
                .where(TeamMember.team_id == team_id)
                .order_by(TeamMember.member_id)
            )
        )


class WorkEventRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_many(self, owner_member_id: int, events: Iterable[Mapping[str, Any]]) -> int:
        inserted = 0
        for event in events:
            existing = self.session.scalar(
                select(WorkEvent.id).where(
                    WorkEvent.source == event["source"],
                    WorkEvent.source_id == event["source_id"],
                )
            )
            if existing is not None:
                continue
            self.session.add(
                WorkEvent(
                    source=event["source"],
                    source_id=event["source_id"],
                    event_type=event["event_type"],
                    owner_member_id=owner_member_id,
                    occurred_at=event["occurred_at"],
                    title=event["title"],
                    summary=event.get("summary"),
                    url=event.get("url"),
                    confidence=event.get("confidence", 1.0),
                    payload_json=json.dumps(event.get("payload", {}), ensure_ascii=False),
                )
            )
            inserted += 1
        self.session.flush()
        return inserted

    def list_for_member(
        self, member_id: int, since: datetime, until: datetime
    ) -> list[WorkEvent]:
        return list(
            self.session.scalars(
                select(WorkEvent)
                .where(
                    WorkEvent.owner_member_id == member_id,
                    WorkEvent.occurred_at >= since,
                    WorkEvent.occurred_at < until,
                )
                .order_by(WorkEvent.occurred_at, WorkEvent.id)
            )
        )

    def id_map(self, keys: Iterable[tuple[str, str]]) -> dict[tuple[str, str], int]:
        result: dict[tuple[str, str], int] = {}
        for source, source_id in keys:
            value = self.session.scalar(
                select(WorkEvent.id).where(
                    WorkEvent.source == source, WorkEvent.source_id == source_id
                )
            )
            if value is not None:
                result[(source, source_id)] = value
        return result


class ReportRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, member_id: int, report_date: str) -> Report | None:
        return self.session.scalar(
            select(Report).where(
                Report.member_id == member_id, Report.report_date == report_date
            )
        )

    def get_by_id(self, report_id: int) -> Report | None:
        return self.session.get(Report, report_id)

    def ensure(self, member_id: int, report_date: str) -> Report:
        report = self.get(member_id, report_date)
        if report is None:
            report = Report(member_id=member_id, report_date=report_date, status="draft")
            self.session.add(report)
            self.session.flush()
        return report

    def replace_items(self, report: Report, items: Iterable[Mapping[str, Any]]) -> None:
        for existing in list(
            self.session.scalars(select(ReportItem).where(ReportItem.report_id == report.id))
        ):
            self.session.delete(existing)
        for order, item in enumerate(items):
            self.session.add(
                ReportItem(
                    report_id=report.id,
                    section=item["section"],
                    content=item["content"],
                    source_event_ids=json.dumps(
                        list(item.get("source_event_ids", [])), ensure_ascii=False
                    ),
                    confidence=item.get("confidence", 1.0),
                    confirmed=1 if item.get("confirmed") else 0,
                    sort_order=item.get("sort_order", order),
                )
            )
        report.generated_at = utcnow()
        self.session.flush()

    def items(self, report_id: int) -> list[ReportItem]:
        return list(
            self.session.scalars(
                select(ReportItem)
                .where(ReportItem.report_id == report_id)
                .order_by(ReportItem.section, ReportItem.sort_order, ReportItem.id)
            )
        )

    def add_version(self, report: Report, snapshot: Mapping[str, Any]) -> ReportVersion:
        version = ReportVersion(
            report_id=report.id,
            version=report.version,
            snapshot_json=json.dumps(snapshot, ensure_ascii=False),
        )
        self.session.add(version)
        self.session.flush()
        return version

    def set_status(self, report: Report, status: str) -> None:
        report.status = status
        now = utcnow()
        if status == "submitted":
            report.submitted_at = now
        elif status == "pushed":
            report.pushed_at = now
        self.session.flush()

    def list_submitted(self, team_id: int, report_date: str) -> list[Report]:
        return list(
            self.session.scalars(
                select(Report)
                .join(Member, Report.member_id == Member.id)
                .join(TeamMember, TeamMember.member_id == Member.id)
                .where(
                    TeamMember.team_id == team_id,
                    Report.report_date == report_date,
                    Report.status.in_(("submitted", "pushed")),
                )
                .order_by(Member.id)
            )
        )


class PushRecordRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(
        self, report_id: int, channel: str, target_type: str, target_id: str
    ) -> PushRecord | None:
        return self.session.scalar(
            select(PushRecord).where(
                PushRecord.report_id == report_id,
                PushRecord.channel == channel,
                PushRecord.target_type == target_type,
                PushRecord.target_id == target_id,
            )
        )

    def ensure(
        self, report_id: int, channel: str, target_type: str, target_id: str
    ) -> PushRecord:
        record = self.get(report_id, channel, target_type, target_id)
        if record is None:
            record = PushRecord(
                report_id=report_id,
                channel=channel,
                target_type=target_type,
                target_id=target_id,
            )
            self.session.add(record)
            self.session.flush()
        return record

    def mark_sent(self, record: PushRecord, provider_msg_id: str | None) -> None:
        record.status = "sent"
        record.provider_msg_id = provider_msg_id
        record.error = None
        record.pushed_at = utcnow()
        self.session.flush()

    def mark_failed(self, record: PushRecord, error: str) -> None:
        record.status = "failed"
        record.retry_count += 1
        record.error = error
        self.session.flush()


class SyncCursorRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, source: str, scope_key: str) -> SyncCursor | None:
        return self.session.scalar(
            select(SyncCursor).where(
                SyncCursor.source == source, SyncCursor.scope_key == scope_key
            )
        )

    def save(self, source: str, scope_key: str, *, cursor: str | None, etag: str | None) -> None:
        record = self.get(source, scope_key)
        if record is None:
            record = SyncCursor(source=source, scope_key=scope_key)
            self.session.add(record)
        record.cursor_value = cursor
        record.etag = etag
        record.last_synced_at = utcnow()
        self.session.flush()


class PipelineRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, run_key: str) -> PipelineRun | None:
        return self.session.scalar(select(PipelineRun).where(PipelineRun.run_key == run_key))

    def start(self, run_key: str, run_date: str) -> PipelineRun:
        run = self.get(run_key)
        if run is None:
            run = PipelineRun(run_key=run_key, run_date=run_date, status="running")
            self.session.add(run)
        else:
            run.status = "running"
            run.stats_json = "{}"
            run.finished_at = None
        self.session.flush()
        return run

    def finish(self, run: PipelineRun, status: str, stats: Mapping[str, Any]) -> None:
        run.status = status
        run.stats_json = json.dumps(stats, ensure_ascii=False)
        run.finished_at = utcnow()
        self.session.flush()
