"""推送层契约：发送结果、幂等投递与 Mock 发布器。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from sqlalchemy.orm import Session

from daily_report.errors import AppError
from daily_report.repositories import PushRecordRepository


@dataclass
class PushPayload:
    title: str
    content_md: str
    report_id: int
    target_type: str
    target_id: str


@dataclass
class PushResult:
    success: bool
    provider_msg_id: str | None = None
    error_code: str | None = None
    retryable: bool = False


@runtime_checkable
class Publisher(Protocol):
    channel: str

    async def publish(self, payload: PushPayload, idempotency_key: str) -> PushResult: ...


class RecordingPublisher:
    """Mock 模式：不访问外部系统，但保持与真实发布器相同的返回契约。"""

    channel = "feishu"

    def __init__(self) -> None:
        self.payloads: list[PushPayload] = []

    async def publish(self, payload: PushPayload, idempotency_key: str) -> PushResult:
        self.payloads.append(payload)
        return PushResult(success=True, provider_msg_id=f"mock-{len(self.payloads)}")


async def deliver(
    publisher: Publisher,
    session: Session,
    payload: PushPayload,
    idempotency_key: str,
) -> PushResult:
    records = PushRecordRepository(session)
    existing = records.get(
        payload.report_id, publisher.channel, payload.target_type, payload.target_id
    )
    if existing is not None and existing.status == "sent":
        return PushResult(success=True, provider_msg_id=existing.provider_msg_id)

    record = records.ensure(
        payload.report_id, publisher.channel, payload.target_type, payload.target_id
    )
    try:
        result = await publisher.publish(payload, idempotency_key)
    except AppError as exc:
        records.mark_failed(record, str(exc))
        return PushResult(success=False, error_code=exc.code.value, retryable=exc.retryable)
    if result.success:
        records.mark_sent(record, result.provider_msg_id)
    else:
        records.mark_failed(record, result.error_code or "push failed")
    return result
