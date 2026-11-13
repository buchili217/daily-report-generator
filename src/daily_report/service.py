"""服务装配：根据配置选择 Mock 或真实采集/推送实现。"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date

from daily_report.collectors.base import Collector
from daily_report.collectors.feishu import (
    FeishuCalendarCollector,
    FeishuDocCollector,
    FeishuTaskCollector,
)
from daily_report.collectors.github import GitHubCollector
from daily_report.collectors.mock import build_mock_collectors
from daily_report.config import Settings, get_settings
from daily_report.db import Database
from daily_report.feishu_api import FeishuApi
from daily_report.generation.llm import DeepSeekProvider
from daily_report.http import HttpClient, make_client
from daily_report.pipeline import DailyResult, PipelineResult, PipelineService
from daily_report.publishers.base import RecordingPublisher
from daily_report.publishers.feishu import FeishuPublisher
from daily_report.repositories import MemberRepository, TeamRepository


def build_service(settings: Settings | None = None) -> PipelineService:
    settings = settings or get_settings()
    database = Database(settings.database_url)
    database.create_all()

    if settings.mock_mode:
        return PipelineService(
            database,
            build_mock_collectors(),
            RecordingPublisher(),
            provider=None,
        )

    http = HttpClient(make_client(timeout=10))
    api = FeishuApi(
        http,
        app_id=settings.feishu_app_id,
        app_secret=settings.feishu_app_secret,
        base_url=settings.feishu_api_base,
    )
    collectors: list[Collector] = [
        FeishuCalendarCollector(api),
        FeishuDocCollector(api),
        FeishuTaskCollector(api),
    ]
    if settings.github_repo_list:
        collectors.append(
            GitHubCollector(
                http,
                token=settings.github_token,
                repos=settings.github_repo_list,
                api_base=settings.github_api_base,
                login=settings.github_login,
            )
        )
    provider = (
        DeepSeekProvider(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
        )
        if settings.llm_api_key
        else None
    )
    return PipelineService(database, collectors, FeishuPublisher(api), provider=provider)


async def run_once(
    service: PipelineService,
    target: date,
    team_id: int | None = None,
    member_id: int | None = None,
) -> int:
    if member_id is not None:
        result: PipelineResult | DailyResult = await service.run_member_pipeline(
            member_id, target
        )
    else:
        result = await service.run_daily_pipeline(target, team_id)
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    return 1 if result.status == "failed" else 0


def seed_demo(service: PipelineService) -> None:
    with service.db.session() as session:
        members = MemberRepository(session)
        if members.get_by_open_id("ou_1") is not None:
            return
        lead = members.add(open_id="ou_1", name="张三", email="zhangsan@example.com", dept="研发")
        peer = members.add(open_id="ou_2", name="李四", email="lisi@example.com", dept="研发")
        teams = TeamRepository(session)
        team = teams.add(name="研发一组", lead_member_id=lead.id)
        teams.add_member(team.id, lead.id, role="lead")
        teams.add_member(team.id, peer.id, role="member")
