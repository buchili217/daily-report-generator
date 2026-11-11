"""大模型接入：统一 Provider 协议、DeepSeek 实现、Fake 与缓存包装。"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Protocol

import httpx

from daily_report.errors import AppError, ErrorCode


class LLMProvider(Protocol):
    name: str

    async def generate(self, prompt: str, schema: dict[str, Any], timeout: float = 20.0) -> str:
        ...


class DeepSeekProvider:
    name = "deepseek"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = client

    async def generate(self, prompt: str, schema: dict[str, Any], timeout: float = 20.0) -> str:
        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    "content": "你是日报助手。只根据给定事实改写，不得编造；输出 JSON。",
                },
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        client = self._client or httpx.AsyncClient(timeout=timeout)
        owns_client = self._client is None
        try:
            response = await client.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=timeout,
            )
        finally:
            if owns_client:
                await client.aclose()
        if response.status_code >= 400:
            raise AppError(
                ErrorCode.GEN_LLM,
                f"llm http {response.status_code}",
                retryable=response.status_code >= 500 or response.status_code == 429,
            )
        body = response.json()
        try:
            return str(body["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise AppError(ErrorCode.GEN_LLM, "llm response malformed") from exc


class FakeProvider:
    name = "fake"

    def __init__(self, response: str = "{}", error: Exception | None = None) -> None:
        self._response = response
        self._error = error
        self.calls = 0

    async def generate(self, prompt: str, schema: dict[str, Any], timeout: float = 20.0) -> str:
        self.calls += 1
        if self._error is not None:
            raise self._error
        return self._response


class CachingProvider:
    def __init__(self, inner: LLMProvider) -> None:
        self._inner = inner
        self._cache: dict[str, str] = {}
        self.name = inner.name

    async def generate(self, prompt: str, schema: dict[str, Any], timeout: float = 20.0) -> str:
        key = hashlib.sha256(
            (prompt + json.dumps(schema, sort_keys=True)).encode("utf-8")
        ).hexdigest()
        if key in self._cache:
            return self._cache[key]
        result = await self._inner.generate(prompt, schema, timeout)
        self._cache[key] = result
        return result
