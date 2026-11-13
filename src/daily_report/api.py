"""FastAPI 接口：OAuth 回调、草稿、提交、推送与团队汇总。"""

from __future__ import annotations

import json
import secrets
from collections.abc import Iterator
from datetime import date
from urllib.parse import quote

from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from daily_report.audit import AuditService
from daily_report.auth import create_session_token, decode_session_token
from daily_report.config import Settings, get_settings
from daily_report.errors import AppError
from daily_report.generation.builder import SECTIONS
from daily_report.http import HttpClient, make_client
from daily_report.pipeline import PipelineService
from daily_report.publishers.base import PushPayload, deliver
from daily_report.repositories import MemberRepository, ReportRepository, TeamRepository
from daily_report.rollup import build_team_digest
from daily_report.service import build_service


class ItemIn(BaseModel):
    section: str
    content: str
    source_event_ids: list[int] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    confirmed: bool = False


class ItemsUpdate(BaseModel):
    items: list[ItemIn]


def _serialize_report(report, items) -> dict:
    sections: dict[str, list[dict]] = {section: [] for section in SECTIONS}
    for item in items:
        sections.setdefault(item.section, []).append(
            {
                "id": item.id,
                "content": item.content,
                "source_event_ids": json.loads(item.source_event_ids or "[]"),
                "confidence": item.confidence,
                "confirmed": bool(item.confirmed),
            }
        )
    return {
        "id": report.id,
        "member_id": report.member_id,
        "report_date": report.report_date,
        "status": report.status,
        "version": report.version,
        "sections": sections,
    }


def create_app(
    service: PipelineService | None = None, settings: Settings | None = None
) -> FastAPI:
    settings = settings or get_settings()
    service = service or build_service(settings)

    app = FastAPI(title="智能日报生成器", version="0.1.0")
    app.state.service = service
    app.state.settings = settings

    def get_session() -> Iterator[Session]:
        with service.db.session() as session:
            yield session

    def current_member_id(authorization: str | None = Header(default=None)) -> int:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="missing bearer token")
        try:
            token = authorization.removeprefix("Bearer ").strip()
            return decode_session_token(token, settings.app_secret_key)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=401, detail="invalid token") from exc

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "mock_mode": settings.mock_mode}

    @app.get("/api/me")
    def me(
        member_id: int = Depends(current_member_id),
        session: Session = Depends(get_session),
    ) -> dict:
        member = MemberRepository(session).get(member_id)
        if member is None:
            raise HTTPException(status_code=404, detail="member not found")
        teams = TeamRepository(session).list_for_member(member_id)
        return {
            "id": member.id,
            "name": member.name,
            "email": member.email,
            "teams": [
                {
                    "id": team.id,
                    "name": team.name,
                    "role": role,
                    "is_lead": team.lead_member_id == member_id,
                }
                for team, role in teams
            ],
        }

    @app.post("/api/reports/{report_date}/generate")
    async def generate_report(
        report_date: str,
        member_id: int = Depends(current_member_id),
    ) -> dict:
        try:
            target = date.fromisoformat(report_date)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="invalid date") from exc
        result = await service.run_member_pipeline(member_id, target)
        if result.status == "failed":
            raise HTTPException(status_code=502, detail=result.error or "generate failed")
        return {
            "status": result.status,
            "report_id": result.report_id,
            "events": result.events,
            "inserted": result.inserted,
            "pushed": result.pushed,
            "degraded": result.degraded,
        }

    @app.get("/api/oauth/feishu/login-url")
    def feishu_login_url() -> dict:
        if not settings.feishu_app_id:
            raise HTTPException(status_code=422, detail="FEISHU_APP_ID 未配置")
        state = f"web:{secrets.token_urlsafe(8)}"
        url = (
            f"{settings.feishu_api_base}/open-apis/authen/v1/authorize"
            f"?app_id={quote(settings.feishu_app_id)}"
            f"&redirect_uri={quote(settings.feishu_redirect_uri, safe='')}"
            f"&state={state}"
        )
        return {"url": url, "state": state}

    @app.get("/api/oauth/feishu/callback")
    async def feishu_callback(
        code: str,
        redirect: bool = False,
        state: str = "",
        session: Session = Depends(get_session),
    ) -> Response:
        if settings.mock_mode:
            open_id, name, email = code, code, None
        else:
            http = HttpClient(make_client(timeout=10))
            from daily_report.feishu_api import FeishuApi

            try:
                async with http.client:
                    api = FeishuApi(
                        http,
                        app_id=settings.feishu_app_id,
                        app_secret=settings.feishu_app_secret,
                        base_url=settings.feishu_api_base,
                    )
                    data = await api.exchange_code(code)
            except AppError as exc:
                raise HTTPException(status_code=401, detail=str(exc)) from exc
            candidate = data.get("open_id")
            if not candidate:
                raise HTTPException(status_code=401, detail="feishu exchange failed")
            open_id = str(candidate)
            name = str(data.get("name") or open_id)
            email = data.get("email")

        members = MemberRepository(session)
        member = members.get_by_open_id(open_id) or members.add(
            open_id=open_id, name=name, email=email
        )
        token = create_session_token(member.id, settings.app_secret_key)
        if redirect or state.startswith("web:"):
            target = (
                f"{settings.frontend_base_url.rstrip('/')}/login"
                f"?token={quote(token)}&name={quote(member.name)}"
            )
            return RedirectResponse(target, status_code=303)
        return JSONResponse({"token": token, "member_id": member.id, "name": member.name})

    @app.get("/api/reports/{report_date}")
    def get_report(
        report_date: str,
        member_id: int = Depends(current_member_id),
        session: Session = Depends(get_session),
    ) -> dict:
        report = ReportRepository(session).get(member_id, report_date)
        if report is None:
            raise HTTPException(status_code=404, detail="report not found")
        items = ReportRepository(session).items(report.id)
        return _serialize_report(report, items)

    @app.put("/api/reports/{report_id}/items")
    def update_items(
        report_id: int,
        body: ItemsUpdate,
        member_id: int = Depends(current_member_id),
        session: Session = Depends(get_session),
    ) -> dict:
        repo = ReportRepository(session)
        report = repo.get_by_id(report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="report not found")
        if report.member_id != member_id:
            raise HTTPException(status_code=403, detail="forbidden")
        if report.status != "draft":
            raise HTTPException(status_code=409, detail="report is not editable")
        for item in body.items:
            if item.section not in SECTIONS:
                raise HTTPException(status_code=422, detail=f"unknown section: {item.section}")
        repo.replace_items(report, [item.model_dump() for item in body.items])
        return _serialize_report(report, repo.items(report.id))

    @app.post("/api/reports/{report_id}/submit")
    def submit_report(
        report_id: int,
        member_id: int = Depends(current_member_id),
        session: Session = Depends(get_session),
    ) -> dict:
        repo = ReportRepository(session)
        report = repo.get_by_id(report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="report not found")
        if report.member_id != member_id:
            raise HTTPException(status_code=403, detail="forbidden")
        if report.status in {"submitted", "pushed"}:
            return _serialize_report(report, repo.items(report.id))
        if report.status != "draft":
            raise HTTPException(status_code=409, detail="invalid status")
        repo.add_version(report, _serialize_report(report, repo.items(report.id)))
        repo.set_status(report, "submitted")
        AuditService(session).log(
            action="submit_report", object_type="report", actor_id=member_id, object_id=report.id
        )
        return _serialize_report(report, repo.items(report.id))

    @app.post("/api/reports/{report_id}/push")
    async def push_report(
        report_id: int,
        member_id: int = Depends(current_member_id),
        session: Session = Depends(get_session),
    ) -> dict:
        repo = ReportRepository(session)
        report = repo.get_by_id(report_id)
        member = MemberRepository(session).get(member_id)
        if report is None or member is None:
            raise HTTPException(status_code=404, detail="report not found")
        if report.member_id != member_id:
            raise HTTPException(status_code=403, detail="forbidden")
        if report.status not in {"submitted", "pushed"}:
            raise HTTPException(status_code=409, detail="report is not submitted")
        items = repo.items(report.id)
        content = "\n".join(f"- {item.content}" for item in items) or "无条目"
        result = await deliver(
            service.publisher,
            session,
            PushPayload(
                title=f"日报（{report.report_date}）",
                content_md=content,
                report_id=report.id,
                target_type="user",
                target_id=member.open_id,
            ),
            idempotency_key=f"push:{report.id}:{report.version}",
        )
        if not result.success:
            session.commit()
            detail = result.error_message or result.error_code or "push failed"
            raise HTTPException(status_code=502, detail=detail)
        repo.set_status(report, "pushed")
        AuditService(session).log(
            action="push_report", object_type="report", actor_id=member_id, object_id=report.id
        )
        return {"success": True, "provider_msg_id": result.provider_msg_id}

    @app.get("/api/teams/{team_id}/digest")
    def team_digest(
        team_id: int,
        report_date: str,
        member_id: int = Depends(current_member_id),
        session: Session = Depends(get_session),
    ) -> dict:
        team = TeamRepository(session).get(team_id)
        if team is None:
            raise HTTPException(status_code=404, detail="team not found")
        if team.lead_member_id != member_id:
            raise HTTPException(status_code=403, detail="forbidden")
        digest = build_team_digest(session, team_id, report_date)
        return {
            "team_id": team_id,
            "report_date": report_date,
            "content_md": digest.content_md,
            "member_count": digest.member_count,
            "submitted_count": digest.submitted_count,
        }

    return app
