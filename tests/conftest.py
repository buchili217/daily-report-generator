from __future__ import annotations

from pathlib import Path

import pytest

from daily_report.collectors.mock import build_mock_collectors
from daily_report.config import Settings
from daily_report.db import Database
from daily_report.pipeline import PipelineService
from daily_report.publishers.base import RecordingPublisher
from daily_report.repositories import MemberRepository, TeamRepository


@pytest.fixture()
def database(tmp_path: Path) -> Database:
    db = Database(f"sqlite:///{(tmp_path / 'app.db').as_posix()}")
    db.create_all()
    return db


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(
        APP_SECRET_KEY="test-secret-0123456789abcdef0123456789",
        MOCK_MODE="true",
        DATABASE_URL=f"sqlite:///{(tmp_path / 'app.db').as_posix()}",
        _env_file=None,
    )


@pytest.fixture()
def publisher() -> RecordingPublisher:
    return RecordingPublisher()


@pytest.fixture()
def service(database: Database, publisher: RecordingPublisher) -> PipelineService:
    return PipelineService(database, build_mock_collectors(), publisher)


@pytest.fixture()
def seeded(database: Database) -> tuple[int, int]:
    with database.session() as session:
        members = MemberRepository(session)
        lead = members.add(open_id="ou_1", name="张三", email="zhangsan@example.com")
        peer = members.add(open_id="ou_2", name="李四", email="lisi@example.com")
        teams = TeamRepository(session)
        team = teams.add(name="研发一组", lead_member_id=lead.id)
        teams.add_member(team.id, lead.id, role="lead")
        teams.add_member(team.id, peer.id, role="member")
        return lead.id, team.id
