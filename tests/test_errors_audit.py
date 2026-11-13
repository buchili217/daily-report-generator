from __future__ import annotations

import json
from pathlib import Path

from daily_report.audit import AuditService, sanitize_detail
from daily_report.db import Database
from daily_report.errors import AppError, ErrorCode
from daily_report.models import AuditLog


def test_app_error_str() -> None:
    error = AppError(ErrorCode.COL_AUTH, "token expired", retryable=False)
    assert str(error) == "E-COL-001: token expired"
    assert isinstance(error, Exception)
    assert error.retryable is False


def test_sanitize_detail_drops_sensitive_keys() -> None:
    cleaned = sanitize_detail(
        {
            "token": "abc",
            "content": "日报正文",
            "email": "a@b.com",
            "nested": {"api_key": "k", "count": 2},
            "note": "user=a@b.com",
        }
    )
    assert "token" not in cleaned
    assert "content" not in cleaned
    assert "email" not in cleaned
    assert cleaned["nested"] == {"count": 2}
    assert "a@b.com" not in cleaned["note"]


def test_audit_log_stores_metadata_only(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{(tmp_path / 'audit.db').as_posix()}")
    database.create_all()
    with database.session() as session:
        record = AuditService(session).log(
            action="push_report",
            object_type="report",
            actor_id=1,
            object_id=10,
            detail={"token": "secret", "content": "正文", "count": 1},
        )
        stored = session.get(AuditLog, record.id)
        detail = json.loads(stored.detail_json)
    assert detail == {"count": 1}
    assert stored.object_id == "10"


def test_error_codes_are_stable() -> None:
    assert ErrorCode.COL_AUTH.value == "E-COL-001"
    assert ErrorCode.PUSH_NOT_CONFIGURED.value == "E-PUSH-010"
    assert str(AppError(ErrorCode.GEN_SCHEMA)) == "E-GEN-001"
