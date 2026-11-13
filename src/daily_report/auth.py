"""会话令牌：HS256 JWT，密钥来自 APP_SECRET_KEY。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt


def create_session_token(member_id: int, secret: str, ttl_minutes: int = 720) -> str:
    payload = {
        "sub": str(member_id),
        "exp": datetime.now(UTC) + timedelta(minutes=ttl_minutes),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_session_token(token: str, secret: str) -> int:
    payload = jwt.decode(token, secret, algorithms=["HS256"])
    return int(payload["sub"])
