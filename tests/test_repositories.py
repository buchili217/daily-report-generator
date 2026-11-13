from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from daily_report.db import Database
from daily_report.models import Member
from daily_report.repositories import (
    MemberRepository,
    PipelineRunRepository,
    PushRecordRepository,
    ReportRepository,
    SyncCursorRepository,
    TeamRepository,
    WorkEventRepository,
)


@pytest.fixture()
def database(tmp_path: Path) -> Database:
    db = Database(f"sqlite:///{(tmp_path / 'repo.db').as_posix()}")
    db.create_all()
    return db


def _seed_member_and_team(session) -> tuple[Member, int]:
    members = MemberRepository(session)
    teams = TeamRepository(session)
    member = members.add(open_id="ou_1", name="张三", email="z@example.com")
    team = teams.add(name="研发一组", lead_member_id=member.id)
    teams.add_member(team.id, member.id, role="lead")
    return member, team.id


def test_team_members_and_active(database: Database) -> None:
    with database.session() as session:
        member, team_id = _seed_member_and_team(session)
        assert MemberRepository(session).list_active() == [member]
        assert TeamRepository(session).member_ids(team_id) == [member.id]


def test_work_event_upsert_is_idempotent(database: Database) -> None:
    event = {
        "source": "github",
        "source_id": "commit-1",
        "event_type": "commit",
        "occurred_at": datetime(2026, 11, 11, 9, 0),
        "title": "feat: x",
        "payload": {"repo": "org/a"},
    }
    with database.session() as session:
        member, _ = _seed_member_and_team(session)
        repo = WorkEventRepository(session)
        assert repo.upsert_many(member.id, [event]) == 1
        assert repo.upsert_many(member.id, [event]) == 0
        rows = repo.list_for_member(
            member.id, datetime(2026, 11, 11), datetime(2026, 11, 12)
        )
        assert len(rows) == 1


def test_report_items_and_versions(database: Database) -> None:
    with database.session() as session:
        member, _ = _seed_member_and_team(session)
        repo = ReportRepository(session)
        report = repo.ensure(member.id, "2026-11-11")
        repo.replace_items(
            report,
            [
                {"section": "done", "content": "修复接口", "source_event_ids": [1]},
                {"section": "plan", "content": "联调", "source_event_ids": []},
            ],
        )
        assert len(repo.items(report.id)) == 2
        repo.replace_items(report, [{"section": "done", "content": "只保留一条"}])
        assert [item.content for item in repo.items(report.id)] == ["只保留一条"]
        repo.add_version(report, {"sections": {"done": ["只保留一条"]}})
        repo.set_status(report, "submitted")
        assert repo.get(member.id, "2026-11-11").status == "submitted"


def test_push_record_ensure_is_unique(database: Database) -> None:
    with database.session() as session:
        member, _ = _seed_member_and_team(session)
        report = ReportRepository(session).ensure(member.id, "2026-11-11")
        records = PushRecordRepository(session)
        first = records.ensure(report.id, "feishu", "user", member.open_id)
        second = records.ensure(report.id, "feishu", "user", member.open_id)
        assert first.id == second.id
        records.mark_sent(first, "om_1")
        assert records.get(report.id, "feishu", "user", member.open_id).status == "sent"


def test_pipeline_run_start_finish(database: Database) -> None:
    with database.session() as session:
        runs = PipelineRunRepository(session)
        run = runs.start("2026-11-11:member:1", "2026-11-11")
        assert run.status == "running"
        runs.finish(run, "success", {"pushed": 1})
        again = runs.start("2026-11-11:member:1", "2026-11-11")
        assert again.status == "running"
        assert again.id == run.id


def test_sync_cursor_roundtrip(database: Database) -> None:
    with database.session() as session:
        cursors = SyncCursorRepository(session)
        assert cursors.get("github", "org/a") is None
        cursors.save("github", "org/a", cursor="2", etag="W/\"abc\"")
        saved = cursors.get("github", "org/a")
        assert saved is not None
        assert saved.etag == 'W/"abc"'
