"""飞书开放平台 HTTP 客户端：租户令牌、GET/POST 与错误映射。"""

from __future__ import annotations

import time
from typing import Any

from daily_report.errors import AppError, ErrorCode
from daily_report.http import HttpClient


class FeishuApi:
    def __init__(
        self,
        http: HttpClient,
        *,
        app_id: str,
        app_secret: str,
        base_url: str = "https://open.feishu.cn",
    ) -> None:
        self._http = http
        self._app_id = app_id
        self._app_secret = app_secret
        self._base_url = base_url.rstrip("/")
        self._token: str | None = None
        self._expires_at = 0.0

    async def token(self) -> str:
        if self._token and time.monotonic() < self._expires_at:
            return self._token
        response = await self._http.post(
            f"{self._base_url}/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": self._app_id, "app_secret": self._app_secret},
        )
        if response.status_code != 200:
            raise AppError(ErrorCode.COL_AUTH, f"token request failed: {response.status_code}")
        data = response.json()
        if data.get("code") != 0:
            raise AppError(ErrorCode.COL_AUTH, f"token error: {data.get('msg')}")
        self._token = data["tenant_access_token"]
        self._expires_at = time.monotonic() + max(60, int(data.get("expire", 7200)) - 60)
        return self._token

    async def exchange_code(self, code: str) -> dict[str, Any]:
        app_token = await self.app_access_token()
        response = await self._http.post(
            f"{self._base_url}/open-apis/authen/v1/oidc/access_token",
            json={"grant_type": "authorization_code", "code": code},
            headers={"Authorization": f"Bearer {app_token}"},
        )
        body = self._handle(response)
        data = body.get("data", {})
        user_token = data.get("access_token")
        if not user_token:
            raise AppError(ErrorCode.COL_AUTH, "user access_token missing")

        info_response = await self._http.get(
            f"{self._base_url}/open-apis/authen/v1/user_info",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        info = self._handle(info_response).get("data", {})
        open_id = info.get("open_id")
        if not open_id:
            raise AppError(ErrorCode.COL_AUTH, "user info missing open_id")
        return {
            "open_id": open_id,
            "name": info.get("name") or info.get("en_name") or open_id,
            "email": info.get("email") or info.get("enterprise_email"),
        }

    async def app_access_token(self) -> str:
        response = await self._http.post(
            f"{self._base_url}/open-apis/auth/v3/app_access_token/internal",
            json={"app_id": self._app_id, "app_secret": self._app_secret},
        )
        if response.status_code != 200:
            raise AppError(ErrorCode.COL_AUTH, "app token request failed")
        data = response.json()
        if data.get("code") != 0:
            raise AppError(ErrorCode.COL_AUTH, f"app token error: {data.get('msg')}")
        return str(data["app_access_token"])

    async def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = await self._http.get(
            f"{self._base_url}{path}",
            params=params,
            headers={"Authorization": f"Bearer {await self.token()}"},
        )
        return self._handle(response)

    async def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self._http.post(
            f"{self._base_url}{path}",
            json=payload,
            headers={"Authorization": f"Bearer {await self.token()}"},
        )
        return self._handle(response)

    def _handle(self, response) -> dict[str, Any]:
        if response.status_code in (401, 403):
            raise AppError(ErrorCode.COL_AUTH, f"feishu unauthorized: {response.status_code}")
        if response.status_code == 429:
            raise AppError(ErrorCode.COL_RATE_LIMITED, "feishu rate limited", retryable=True)
        if response.status_code >= 400:
            raise AppError(ErrorCode.COL_TIMEOUT, f"feishu upstream error: {response.status_code}")
        body = response.json()
        if body.get("code") not in (0, None):
            raise AppError(ErrorCode.COL_AUTH, f"feishu error: {body.get('msg')}")
        return body
