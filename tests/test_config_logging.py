from __future__ import annotations

import logging

import pytest
from pydantic import ValidationError

from daily_report.config import Settings, get_settings
from daily_report.logging import RedactionFilter, redact


def test_settings_requires_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_SECRET_KEY", raising=False)
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    assert "APP_SECRET_KEY" in str(exc.value)


def test_settings_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_SECRET_KEY", "unit-test-secret")
    monkeypatch.setenv("GITHUB_REPOS", "org/a, org/b")
    get_settings.cache_clear()
    settings = Settings(_env_file=None)
    assert settings.github_repo_list == ["org/a", "org/b"]
    get_settings.cache_clear()


def test_redact_removes_tokens_and_emails() -> None:
    result = redact("token=abc12345 user=a@b.com Authorization: Bearer xyz.123")
    assert "abc12345" not in result
    assert "a@b.com" not in result
    assert "xyz.123" not in result
    assert "***" in result


def test_log_filter_scrubs_record() -> None:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="app_secret=%s email=%s",
        args=("s3cr3t", "a@b.com"),
        exc_info=None,
    )
    RedactionFilter().filter(record)
    output = record.getMessage()
    assert "s3cr3t" not in output
    assert "a@b.com" not in output
