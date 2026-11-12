from __future__ import annotations

import asyncio
from datetime import date

from fastapi.testclient import TestClient

from daily_report.api import create_app
from daily_report.auth import create_session_token
from daily_report.config import Settings
from daily_report.pipeline import PipelineService

DAY = date(2026, 11, 11)


def _client(service: PipelineService, settings: Settings) -> TestClient:
    return TestClient(create_app(service, settings))


def _auth(member_id: int, settings: Settings) -> dict[str, str]:
    token = create_session_token(member_id, settings.app_secret_key)
    return {"Authorization": f"Bearer {token}"}


def test_health_and_unauthorized(service: PipelineService, settings: Settings) -> None:
    client = _client(service, settings)
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/reports/2026-11-11").status_code == 401


def test_report_flow(
    service: PipelineService, settings: Settings, seeded: tuple[int, int]
) -> None:
    member_id, team_id = seeded
    asyncio.run(service.run_member_pipeline(member_id, DAY))
    client = _client(service, settings)
    headers = _auth(member_id, settings)

    report = client.get("/api/reports/2026-11-11", headers=headers).json()
    assert report["status"] == "draft"
    assert len(report["sections"]["done"]) == 4

    updated = client.put(
        f"/api/reports/{report['id']}/items",
        headers=headers,
        json={"items": [{"section": "done", "content": "手工整理的成果"}]},
    )
    assert updated.status_code == 200
    assert updated.json()["sections"]["done"][0]["content"] == "手工整理的成果"

    submitted = client.post(f"/api/reports/{report['id']}/submit", headers=headers)
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "submitted"

    pushed = client.post(f"/api/reports/{report['id']}/push", headers=headers)
    assert pushed.status_code == 200
    assert pushed.json()["success"] is True

    digest = client.get(
        f"/api/teams/{team_id}/digest?report_date=2026-11-11", headers=headers
    )
    assert digest.status_code == 200
    assert "手工整理的成果" in digest.json()["content_md"]


def test_report_forbidden_for_other_member(
    service: PipelineService, settings: Settings, seeded: tuple[int, int]
) -> None:
    member_id, _ = seeded
    asyncio.run(service.run_member_pipeline(member_id, DAY))
    client = _client(service, settings)
    report = client.get("/api/reports/2026-11-11", headers=_auth(member_id, settings)).json()
    response = client.post(f"/api/reports/{report['id']}/submit", headers=_auth(2, settings))
    assert response.status_code == 403


def test_oauth_callback_creates_member(
    service: PipelineService, settings: Settings
) -> None:
    client = _client(service, settings)
    response = client.get("/api/oauth/feishu/callback", params={"code": "ou_demo"})
    assert response.status_code == 200
    body = response.json()
    assert body["token"]
    again = client.get("/api/oauth/feishu/callback", params={"code": "ou_demo"})
    assert again.json()["member_id"] == body["member_id"]


def test_me_endpoint_returns_teams(
    service: PipelineService, settings: Settings, seeded: tuple[int, int]
) -> None:
    member_id, team_id = seeded
    client = _client(service, settings)
    body = client.get("/api/me", headers=_auth(member_id, settings)).json()
    assert body["name"] == "张三"
    assert body["teams"] == [
        {"id": team_id, "name": "研发一组", "role": "lead", "is_lead": True}
    ]


def test_generate_endpoint_creates_report(
    service: PipelineService, settings: Settings, seeded: tuple[int, int]
) -> None:
    member_id, _ = seeded
    client = _client(service, settings)
    headers = _auth(member_id, settings)
    response = client.post("/api/reports/2026-11-14/generate", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["report_id"] is not None
    assert body["events"] == 4

    report = client.get("/api/reports/2026-11-14", headers=headers).json()
    assert report["status"] == "draft"
    assert len(report["sections"]["done"]) == 4


def test_feishu_login_url_requires_app_id(
    service: PipelineService, settings: Settings
) -> None:
    client = _client(service, settings)
    assert client.get("/api/oauth/feishu/login-url").status_code == 422


def test_feishu_login_url_contains_redirect(
    service: PipelineService, settings: Settings
) -> None:
    real_config = settings.model_copy(
        update={
            "feishu_app_id": "cli_test",
            "feishu_app_secret": "secret",
            "feishu_redirect_uri": "http://localhost:8000/api/oauth/feishu/callback",
        }
    )
    client = _client(service, real_config)
    body = client.get("/api/oauth/feishu/login-url").json()
    assert "app_id=cli_test" in body["url"]
    assert "open-apis/authen/v1/authorize" in body["url"]
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A8000" in body["url"]


def test_feishu_callback_redirects_to_frontend(
    service: PipelineService, settings: Settings, seeded: tuple[int, int]
) -> None:
    client = TestClient(create_app(service, settings))
    response = client.get(
        "/api/oauth/feishu/callback",
        params={"code": "ou_1", "redirect": "true"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith("http://localhost:5173/login?token=")
    assert "name=" in location
