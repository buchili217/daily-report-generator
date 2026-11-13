from __future__ import annotations

import httpx
import pytest

from daily_report.errors import AppError, ErrorCode
from daily_report.feishu_api import FeishuApi
from daily_report.http import HttpClient, make_client


def _api(handler) -> tuple[HttpClient, FeishuApi]:
    http = HttpClient(make_client(transport=httpx.MockTransport(handler)))
    return http, FeishuApi(http, app_id="a", app_secret="b", base_url="https://feishu.test")


def _token(request: httpx.Request) -> httpx.Response | None:
    if request.url.path.endswith(("app_access_token/internal", "tenant_access_token/internal")):
        return httpx.Response(
            200,
            json={
                "code": 0,
                "app_access_token": "app-token",
                "tenant_access_token": "tenant-token",
            },
        )
    return None


async def test_exchange_code_returns_user_info() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        token = _token(request)
        if token:
            return token
        if request.url.path.endswith("oidc/access_token"):
            assert request.headers["Authorization"] == "Bearer app-token"
            return httpx.Response(200, json={"code": 0, "data": {"access_token": "user-token"}})
        if request.url.path.endswith("user_info"):
            assert request.headers["Authorization"] == "Bearer user-token"
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "open_id": "ou_real",
                        "name": "王五",
                        "email": "w@e.com",
                    },
                },
            )
        return httpx.Response(404)

    http, api = _api(handler)
    async with http.client:
        data = await api.exchange_code("code-1")
    assert data == {"open_id": "ou_real", "name": "王五", "email": "w@e.com"}


async def test_exchange_code_without_user_token_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        token = _token(request)
        if token:
            return token
        return httpx.Response(200, json={"code": 0, "data": {}})

    http, api = _api(handler)
    async with http.client:
        with pytest.raises(AppError) as exc:
            await api.exchange_code("code-2")
    assert exc.value.code == ErrorCode.COL_AUTH


async def test_permission_error_includes_scope_hint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        token = _token(request)
        if token:
            return token
        return httpx.Response(
            400,
            json={
                "code": 99991672,
                "msg": "Access denied. One of the following scopes is required: [im:message:send]",
            },
        )

    http, api = _api(handler)
    async with http.client:
        with pytest.raises(AppError) as exc:
            await api.post("/open-apis/im/v1/messages", {})
    assert exc.value.code == ErrorCode.COL_AUTH
    assert "im:message" in str(exc.value)
    assert "99991672" in str(exc.value)
