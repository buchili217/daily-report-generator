from __future__ import annotations

import httpx
import pytest

from daily_report.http import HttpClient, TokenBucket, make_client


def _transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


async def test_retries_429_then_success() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"ok": True})

    delays: list[float] = []

    async def sleeper(delay: float) -> None:
        delays.append(delay)

    async with make_client(transport=_transport(handler)) as client:
        http = HttpClient(client, sleeper=sleeper)
        response = await http.get("https://example.test/x")

    assert response.status_code == 200
    assert len(calls) == 2
    assert delays == [0.0]


async def test_does_not_retry_4xx() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(401)

    async with make_client(transport=_transport(handler)) as client:
        http = HttpClient(client)
        response = await http.get("https://example.test/x")

    assert response.status_code == 401
    assert len(calls) == 1


async def test_retries_timeout_then_success() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ConnectTimeout("boom", request=request)
        return httpx.Response(200)

    async def sleeper(_delay: float) -> None:
        return None

    async with make_client(transport=_transport(handler)) as client:
        http = HttpClient(client, sleeper=sleeper)
        response = await http.get("https://example.test/x")

    assert response.status_code == 200
    assert len(calls) == 2


async def test_timeout_raises_after_max_attempts() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("boom", request=request)

    async def sleeper(_delay: float) -> None:
        return None

    async with make_client(transport=_transport(handler)) as client:
        http = HttpClient(client, sleeper=sleeper)
        with pytest.raises(httpx.ConnectTimeout):
            await http.get("https://example.test/x")


async def test_token_bucket_waits() -> None:
    bucket = TokenBucket(rate=1, capacity=1)
    waits: list[float] = []

    async def sleeper(delay: float) -> None:
        waits.append(delay)

    await bucket.acquire(sleep=sleeper)
    await bucket.acquire(sleep=sleeper)
    assert waits and waits[0] > 0
