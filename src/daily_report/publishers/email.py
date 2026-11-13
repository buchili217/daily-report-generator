"""邮件推送（P2）：SMTP 发送，未配置时返回 E-PUSH-010。"""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage

from daily_report.publishers.base import PushPayload, PushResult


class EmailPublisher:
    channel = "email"

    def __init__(
        self,
        *,
        host: str,
        port: int,
        user: str,
        password: str,
        sender: str,
        smtp_factory=smtplib.SMTP,
    ) -> None:
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._sender = sender
        self._smtp_factory = smtp_factory

    async def publish(self, payload: PushPayload, idempotency_key: str) -> PushResult:
        if not self._host or not self._sender:
            return PushResult(success=False, error_code="E-PUSH-010")
        try:
            message_id = await asyncio.to_thread(self._send, payload)
        except OSError:
            return PushResult(success=False, error_code="E-PUSH-002", retryable=True)
        return PushResult(success=True, provider_msg_id=message_id)

    def _send(self, payload: PushPayload) -> str:
        message = EmailMessage()
        message["Subject"] = payload.title
        message["From"] = self._sender
        message["To"] = payload.target_id
        message.set_content(payload.content_md)
        with self._smtp_factory(self._host, self._port, timeout=10) as smtp:
            if self._port == 587:
                smtp.starttls()
            if self._user:
                smtp.login(self._user, self._password)
            smtp.send_message(message)
        return f"email-{payload.report_id}"
