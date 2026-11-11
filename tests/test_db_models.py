from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from daily_report.db import Database, make_engine
from daily_report.models import Member, Report, WorkEvent

EXPECTED_TABLES = {
    "member",
    "team",
    "team_member",
    "work_event",
    "event_participant",
    "report",
    "report_item",
    "report_version",
    "push_record",
    "sync_cursor",
    "pipeline_run",
    "audit_log",
}


@pytest.fixture()
def database(tmp_path: Path) -> Database:
    db = Database(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    db.create_all()
    return db


def test_migration_creates_all_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "migrated.db"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    command.upgrade(config, "head")

    engine = make_engine(f"sqlite:///{db_path.as_posix()}")
    tables = set(inspect(engine).get_table_names())
    assert tables >= EXPECTED_TABLES
    with engine.connect() as connection:
        mode = connection.exec_driver_sql("PRAGMA journal_mode").scalar()
        foreign_keys = connection.exec_driver_sql("PRAGMA foreign_keys").scalar()
    assert str(mode).lower() == "wal"
    assert foreign_keys == 1


def test_work_event_unique_source(database: Database) -> None:
    with database.session() as session:
        session.add(Member(open_id="ou_1", name="张三"))
    with pytest.raises(IntegrityError), database.session() as session:
        session.add(
            WorkEvent(
                source="github",
                source_id="c1",
                event_type="commit",
                occurred_at=datetime(2026, 11, 10),
                title="a",
            )
        )
        session.flush()
        session.add(
            WorkEvent(
                source="github",
                source_id="c1",
                event_type="commit",
                occurred_at=datetime(2026, 11, 10),
                title="b",
            )
        )
        session.flush()


def test_report_unique_member_date(database: Database) -> None:
    with database.session() as session:
        session.add(Member(open_id="ou_2", name="李四"))
        session.flush()
        member_id = session.query(Member).filter_by(open_id="ou_2").one().id
    with pytest.raises(IntegrityError), database.session() as session:
        session.add(Report(member_id=member_id, report_date="2026-11-10"))
        session.flush()
        session.add(Report(member_id=member_id, report_date="2026-11-10"))
        session.flush()
