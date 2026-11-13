"""审计服务：只记录元数据，不记录日报正文、令牌与邮箱。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from daily_report.logging import redact
from daily_report.models import AuditLog

_SENSITIVE_KEYS = {
    "token",
    "access_token",
    "refresh_token",
    "app_secret",
    "api_key",
    "password",
    "authorization",
    "secret",
    "content",
    "body",
    "email",
}


def sanitize_detail(detail: Mapping[str, Any] | None) -> dict[str, Any]:
    if not detail:
        return {}
    cleaned: dict[str, Any] = {}
    for key, value in detail.items():
        if key.lower() in _SENSITIVE_KEYS:
            continue
        if isinstance(value, str):
            cleaned[key] = redact(value)
        elif isinstance(value, Mapping):
            cleaned[key] = sanitize_detail(value)
        else:
            cleaned[key] = value
    return cleaned


class AuditService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def log(
        self,
        *,
        action: str,
        object_type: str,
        actor_id: int | None = None,
        object_id: str | int | None = None,
        result: str = "success",
        ip: str | None = None,
        detail: Mapping[str, Any] | None = None,
    ) -> AuditLog:
        record = AuditLog(
            actor_id=actor_id,
            action=action,
            object_type=object_type,
            object_id=None if object_id is None else str(object_id),
            result=result,
            ip=ip,
            detail_json=json.dumps(sanitize_detail(detail), ensure_ascii=False),
        )
        self.session.add(record)
        self.session.flush()
        return record
