from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Member(Base):
    __tablename__ = "member"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    open_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str | None] = mapped_column(String)
    dept: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    __table_args__ = (CheckConstraint("status IN ('active', 'inactive')", name="ck_member_status"),)


class Team(Base):
    __tablename__ = "team"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    lead_member_id: Mapped[int | None] = mapped_column(ForeignKey("member.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class TeamMember(Base):
    __tablename__ = "team_member"

    team_id: Mapped[int] = mapped_column(
        ForeignKey("team.id", ondelete="CASCADE"), primary_key=True
    )
    member_id: Mapped[int] = mapped_column(
        ForeignKey("member.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String, nullable=False, default="member")

    __table_args__ = (CheckConstraint("role IN ('lead', 'member')", name="ck_team_member_role"),)


class WorkEvent(Base):
    __tablename__ = "work_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    source_id: Mapped[str] = mapped_column(String, nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    owner_member_id: Mapped[int | None] = mapped_column(ForeignKey("member.id"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    collected_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_work_event_source"),
        Index("idx_work_event_member_time", "owner_member_id", "occurred_at"),
        CheckConstraint(
            "source IN ('github', 'feishu_calendar', 'feishu_doc', 'feishu_task')",
            name="ck_work_event_source",
        ),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_work_event_confidence"),
    )


class EventParticipant(Base):
    __tablename__ = "event_participant"

    event_id: Mapped[int] = mapped_column(
        ForeignKey("work_event.id", ondelete="CASCADE"), primary_key=True
    )
    member_id: Mapped[int] = mapped_column(
        ForeignKey("member.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String, primary_key=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)

    __table_args__ = (
        CheckConstraint(
            "role IN ('owner', 'collaborator', 'reviewer', 'attendee')",
            name="ck_event_participant_role",
        ),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_event_participant_confidence"),
    )


class Report(Base):
    __tablename__ = "report"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("member.id"), nullable=False)
    report_date: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="draft")
    template_version: Mapped[str] = mapped_column(String, nullable=False, default="v1")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    pushed_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (
        UniqueConstraint("member_id", "report_date", name="uq_report_member_date"),
        CheckConstraint(
            "status IN ('draft', 'submitted', 'pushed', 'withdrawn')", name="ck_report_status"
        ),
    )


class ReportItem(Base):
    __tablename__ = "report_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(
        ForeignKey("report.id", ondelete="CASCADE"), nullable=False
    )
    section: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_event_ids: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    confirmed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("idx_report_item_report", "report_id", "section", "sort_order"),
        CheckConstraint(
            "section IN ('done', 'doing', 'risk', 'plan')", name="ck_report_item_section"
        ),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_report_item_confidence"),
        CheckConstraint("confirmed IN (0, 1)", name="ck_report_item_confirmed"),
    )


class ReportVersion(Base):
    __tablename__ = "report_version"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(
        ForeignKey("report.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    __table_args__ = (UniqueConstraint("report_id", "version", name="uq_report_version"),)


class PushRecord(Base):
    __tablename__ = "push_record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(
        ForeignKey("report.id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String, nullable=False)
    target_type: Mapped[str] = mapped_column(String, nullable=False)
    target_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    provider_msg_id: Mapped[str | None] = mapped_column(String)
    error: Mapped[str | None] = mapped_column(Text)
    pushed_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (
        UniqueConstraint(
            "report_id", "channel", "target_type", "target_id", name="uq_push_record_target"
        ),
        CheckConstraint("channel IN ('feishu', 'email')", name="ck_push_record_channel"),
        CheckConstraint("target_type IN ('user', 'chat')", name="ck_push_record_target_type"),
        CheckConstraint("status IN ('pending', 'sent', 'failed')", name="ck_push_record_status"),
    )


class SyncCursor(Base):
    __tablename__ = "sync_cursor"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    scope_key: Mapped[str] = mapped_column(String, nullable=False)
    cursor_value: Mapped[str | None] = mapped_column(String)
    etag: Mapped[str | None] = mapped_column(String)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (UniqueConstraint("source", "scope_key", name="uq_sync_cursor_scope"),)


class PipelineRun(Base):
    __tablename__ = "pipeline_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    run_date: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    stats_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'success', 'partial', 'failed')", name="ck_pipeline_run_status"
        ),
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_id: Mapped[int | None] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String, nullable=False)
    object_type: Mapped[str] = mapped_column(String, nullable=False)
    object_id: Mapped[str | None] = mapped_column(String)
    result: Mapped[str] = mapped_column(String, nullable=False)
    ip: Mapped[str | None] = mapped_column(String)
    detail_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    __table_args__ = (Index("idx_audit_log_time", "created_at"),)
