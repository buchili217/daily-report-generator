from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from daily_report.db import Database
from daily_report.feishu_api import FeishuApi
from daily_report.http import HttpClient, make_client
from daily_report.publishers.base import PushPayload, RecordingPublisher, deliver
from daily_report.publishers.email import EmailPublisher
from daily_report.publishers.feishu import FeishuPublisher
from daily_report.repositories import MemberRepository, ReportRepository


@pytest.fixture()
def database(tmp_path: Path) -> Database:
    db = Database(f"sqlite:///{(tmp_path / 'push.db').as_posix()}")
    db.create_all()
    with db.session() as session:
        member = MemberRepository(session).add(open_id="ou_1", name="张三")
        ReportRepository(session).ensure(member.id, "2026-11-11")
    return db


def _payload(report_id: int, target_type: str = "user", target_id: str = "ou_1") -> PushPayload:
    return PushPayload(
        title="日报",
        content_md="**今日完成**",
        report_id=report_id,
        target_type=target_type,
        target_id=target_id,
    )


async def test_deliver_is_idempotent(database: Database) -> None:
    publisher = RecordingPublisher()
    with database.session() as session:
        report_id = ReportRepository(session).ensure(1, "2026-11-11").id
        first = await deliver(publisher, session, _payload(report_id), "key")
        second = await deliver(publisher, session, _payload(report_id), "key")
    assert first.success and second.success
    assert len(publisher.payloads) == 1
    assert first.provider_msg_id == second.provider_msg_id


async def test_feishu_publisher_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("tenant_access_token/internal"):
            return httpx.Response(200, json={"code": 0, "tenant_access_token": "t"})
        body = json.loads(request.content)
        assert body["msg_type"] == "interactive"
        return httpx.Response(200, json={"code": 0, "data": {"message_id": "om_1"}})

    http = HttpClient(make_client(transport=httpx.MockTransport(handler)))
    async with http.client:
        api = FeishuApi(http, app_id="a", app_secret="b", base_url="https://feishu.test")
        result = await FeishuPublisher(api).publish(_payload(1), "key")
    assert result.success
    assert result.provider_msg_id == "om_1"


async def test_feishu_publisher_maps_auth_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("tenant_access_token/internal"):
            return httpx.Response(200, json={"code": 0, "tenant_access_token": "t"})
        return httpx.Response(401, json={"code": 1})

    http = HttpClient(make_client(transport=httpx.MockTransport(handler)))
    async with http.client:
        api = FeishuApi(http, app_id="a", app_secret="b", base_url="https://feishu.test")
        result = await FeishuPublisher(api).publish(_payload(1), "key")
    assert not result.success
    assert result.error_code == "E-PUSH-001"


class FakeSMTP:
    sent: list = []

    def __init__(self, host, port, timeout=None):
        self.host = host

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def starttls(self):
        return None

    def login(self, user, password):
        return None

    def send_message(self, message):
        FakeSMTP.sent.append(message)


async def test_email_unconfigured_returns_code() -> None:
    publisher = EmailPublisher(host="", port=587, user="", password="", sender="")
    result = await publisher.publish(_payload(1), "key")
    assert result.error_code == "E-PUSH-010"


async def test_email_configured_sends() -> None:
    FakeSMTP.sent.clear()
    publisher = EmailPublisher(
        host="smtp.test",
        port=587,
        user="u",
        password="p",
        sender="from@test",
        smtp_factory=FakeSMTP,
    )
    result = await publisher.publish(_payload(1, target_type="chat", target_id="to@test"), "key")
    assert result.success
    assert FakeSMTP.sent[0]["To"] == "to@test"
