"""HTTP 客户端：连接复用、令牌桶限流、指数退避重试。"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import httpx

Sleeper = Callable[[float], Awaitable[None]]

RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


class TokenBucket:
    """异步令牌桶；`sleep` 可注入以便测试。"""

    def __init__(self, rate: float, capacity: float | None = None) -> None:
        if rate <= 0:
            raise ValueError("rate must be positive")
        self.rate = rate
        self.capacity = capacity if capacity is not None else rate
        self._tokens = self.capacity
        self._updated = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, amount: float = 1.0, sleep: Sleeper = asyncio.sleep) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                self._tokens = min(self.capacity, self._tokens + (now - self._updated) * self.rate)
                self._updated = now
                if self._tokens >= amount:
                    self._tokens -= amount
                    return
                wait = (amount - self._tokens) / self.rate
                await sleep(wait)
                self._tokens = min(self.capacity, self._tokens + wait * self.rate)
                self._updated = time.monotonic()


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 8.0
    retry_statuses: frozenset[int] = field(default=RETRYABLE_STATUSES)


def retry_after_seconds(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def backoff_delay(attempt: int, policy: RetryPolicy) -> float:
    delay = min(policy.max_delay, policy.base_delay * (2 ** (attempt - 1)))
    return delay * random.uniform(0.8, 1.2)


class HttpClient:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        bucket: TokenBucket | None = None,
        policy: RetryPolicy | None = None,
        sleeper: Sleeper = asyncio.sleep,
    ) -> None:
        self._client = client
        self._bucket = bucket
        self._policy = policy or RetryPolicy()
        self._sleep = sleeper

    @property
    def client(self) -> httpx.AsyncClient:
        return self._client

    async def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        policy = self._policy
        last_error: Exception | None = None
        for attempt in range(1, policy.max_attempts + 1):
            if self._bucket is not None:
                await self._bucket.acquire(sleep=self._sleep)
            try:
                response = await self._client.request(method, url, **kwargs)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                if attempt == policy.max_attempts:
                    raise
                await self._sleep(backoff_delay(attempt, policy))
                continue

            if response.status_code in policy.retry_statuses and attempt < policy.max_attempts:
                delay = retry_after_seconds(response)
                await self._sleep(delay if delay is not None else backoff_delay(attempt, policy))
                continue
            return response

        if last_error is not None:
            raise last_error
        raise RuntimeError("retry loop exhausted without response")

    async def get(self, url: str, **kwargs) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> httpx.Response:
        return await self.request("POST", url, **kwargs)


def make_client(
    *,
    base_url: str = "",
    headers: dict[str, str] | None = None,
    timeout: float = 10.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=base_url,
        headers=headers or {},
        timeout=timeout,
        transport=transport,
    )
