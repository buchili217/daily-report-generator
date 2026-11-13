"""GitHub 采集器：白名单仓库的 commit 与 PR，支持 ETag 增量。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from daily_report.collectors.base import CollectedEvent, CollectResult, TimeWindow
from daily_report.errors import AppError, ErrorCode
from daily_report.http import HttpClient
from daily_report.models import Member


def _parse_gh_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
            UTC
        ).replace(tzinfo=None)
    except ValueError:
        return None


class GitHubCollector:
    source = "github"

    def __init__(
        self,
        http: HttpClient,
        *,
        token: str,
        repos: list[str],
        api_base: str = "https://api.github.com",
        etags: dict[str, str] | None = None,
        login: str = "",
    ) -> None:
        self._http = http
        self._token = token
        self._repos = repos
        self._api_base = api_base.rstrip("/")
        self._etags = dict(etags or {})
        self._login = login.strip().lower()

    def _headers(self, etag: str | None = None) -> dict[str, str]:
        headers = {"Accept": "application/vnd.github+json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        if etag:
            headers["If-None-Match"] = etag
        return headers

    async def _get(self, path: str, *, params: dict[str, Any], etag: str | None = None):
        response = await self._http.get(
            f"{self._api_base}{path}", params=params, headers=self._headers(etag)
        )
        if response.status_code in (401, 403):
            raise AppError(ErrorCode.COL_AUTH, f"github unauthorized: {response.status_code}")
        if response.status_code == 429:
            raise AppError(ErrorCode.COL_RATE_LIMITED, "github rate limited", retryable=True)
        if response.status_code >= 500:
            raise AppError(ErrorCode.COL_TIMEOUT, "github upstream error", retryable=True)
        return response

    async def collect(self, member: Member, window: TimeWindow) -> CollectResult:
        events: list[CollectedEvent] = []
        next_etags: dict[str, str] = {}
        login = self._login or (member.email or "").split("@")[0].lower()

        for repo in self._repos:
            commits = await self._get(
                f"/repos/{repo}/commits",
                params={
                    "since": window.since.replace(tzinfo=UTC).isoformat(),
                    "until": window.until.replace(tzinfo=UTC).isoformat(),
                    "per_page": 100,
                },
                etag=self._etags.get(repo),
            )
            if commits.status_code == 304:
                next_etags[repo] = self._etags.get(repo, "")
            else:
                etag = commits.headers.get("ETag")
                if etag:
                    next_etags[repo] = etag
                events.extend(self._commit_events(repo, commits.json(), member))

            pulls = await self._get(
                f"/repos/{repo}/pulls",
                params={"state": "all", "sort": "updated", "direction": "desc", "per_page": 100},
            )
            if pulls.status_code != 304:
                events.extend(self._pull_events(repo, pulls.json(), login, member, window))

        return CollectResult(source=self.source, events=events, next_etags=next_etags)

    def _commit_events(
        self, repo: str, data: list[dict[str, Any]], member: Member
    ) -> list[CollectedEvent]:
        events: list[CollectedEvent] = []
        email = (member.email or "").lower()
        for item in data:
            commit = item.get("commit", {})
            author = commit.get("author", {})
            if email and str(author.get("email", "")).lower() != email:
                continue
            occurred = _parse_gh_time(author.get("date"))
            if occurred is None:
                continue
            message = str(commit.get("message", "")).splitlines()
            events.append(
                CollectedEvent(
                    source=self.source,
                    source_id=f"{repo}@{item.get('sha')}",
                    event_type="commit",
                    owner_open_id=member.open_id,
                    occurred_at=occurred,
                    title=message[0][:120] if message else "commit",
                    summary="\n".join(message[1:]).strip() or None,
                    url=item.get("html_url"),
                    confidence=1.0,
                    payload={"repo": repo, "sha": item.get("sha")},
                )
            )
        return events

    def _pull_events(
        self,
        repo: str,
        data: list[dict[str, Any]],
        login: str,
        member: Member,
        window: TimeWindow,
    ) -> list[CollectedEvent]:
        events: list[CollectedEvent] = []
        for item in data:
            updated = _parse_gh_time(item.get("updated_at"))
            if updated is None or not (window.since <= updated < window.until):
                continue
            user = item.get("user") or {}
            if login and str(user.get("login", "")).lower() != login:
                continue
            events.append(
                CollectedEvent(
                    source=self.source,
                    source_id=f"{repo}#{item.get('number')}",
                    event_type="pr",
                    owner_open_id=member.open_id,
                    occurred_at=updated,
                    title=item.get("title") or "pull request",
                    summary=item.get("body"),
                    url=item.get("html_url"),
                    confidence=1.0,
                    payload={"repo": repo, "state": item.get("state")},
                )
            )
        return events
