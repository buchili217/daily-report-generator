"""飞书推送：个人/群消息卡片。"""

from __future__ import annotations

import json

from daily_report.errors import AppError, ErrorCode
from daily_report.feishu_api import FeishuApi
from daily_report.publishers.base import PushPayload, PushResult


class FeishuPublisher:
    channel = "feishu"

    def __init__(self, api: FeishuApi) -> None:
        self._api = api

    async def publish(self, payload: PushPayload, idempotency_key: str) -> PushResult:
        card = {
            "config": {"wide_screen_mode": True},
            "header": {"title": {"tag": "plain_text", "content": payload.title}},
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": payload.content_md}}
            ],
        }
        receive_id_type = "open_id" if payload.target_type == "user" else "chat_id"
        try:
            body = await self._api.post(
                f"/open-apis/im/v1/messages?receive_id_type={receive_id_type}",
                {
                    "receive_id": payload.target_id,
                    "msg_type": "interactive",
                    "content": json.dumps(card, ensure_ascii=False),
                },
            )
        except AppError as exc:
            code = (
                ErrorCode.PUSH_AUTH if exc.code is ErrorCode.COL_AUTH else ErrorCode.PUSH_TARGET
            )
            return PushResult(
                success=False,
                error_code=code.value,
                retryable=exc.retryable,
            )
        message_id = (body.get("data") or {}).get("message_id")
        return PushResult(success=True, provider_msg_id=message_id)
