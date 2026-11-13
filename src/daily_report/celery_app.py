"""Celery 定时任务：工作日 17:30 生成日报，17:45 汇总团队日报。"""

from __future__ import annotations

import asyncio
import os
from datetime import date

from celery import Celery
from celery.schedules import crontab

_BROKER = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery("daily_report", broker=_BROKER, backend=_BROKER)
celery_app.conf.timezone = os.getenv("APP_TIMEZONE", "Asia/Shanghai")
celery_app.conf.beat_schedule = {
    "daily-report": {
        "task": "daily_report.run_daily",
        "schedule": crontab(
            hour=int(os.getenv("DAILY_RUN_HOUR", "17")),
            minute=int(os.getenv("DAILY_RUN_MINUTE", "30")),
            day_of_week="1-5",
        ),
    },
    "team-rollup": {
        "task": "daily_report.run_rollups",
        "schedule": crontab(
            hour=int(os.getenv("DAILY_RUN_HOUR", "17")),
            minute=min(int(os.getenv("DAILY_RUN_MINUTE", "30")) + 15, 59),
            day_of_week="1-5",
        ),
    },
}


def _target(date_str: str | None) -> date:
    return date.fromisoformat(date_str) if date_str else date.today()


@celery_app.task(name="daily_report.run_daily")
def run_daily_task(date_str: str | None = None, team_id: int | None = None) -> dict:
    from daily_report.service import build_service

    service = build_service()
    result = asyncio.run(service.run_daily_pipeline(_target(date_str), team_id))
    return {
        "status": result.status,
        "report_date": result.report_date,
        "members": len(result.results),
        "failed": sum(1 for item in result.results if item.status == "failed"),
    }


@celery_app.task(name="daily_report.run_rollups")
def run_rollups_task(date_str: str | None = None) -> dict:
    from sqlalchemy import select

    from daily_report.models import Team
    from daily_report.service import build_service

    service = build_service()
    with service.db.session() as session:
        team_ids = list(session.scalars(select(Team.id).order_by(Team.id)))
    for team_id in team_ids:
        asyncio.run(service.run_team_rollup(team_id, _target(date_str)))
    return {"teams": len(team_ids)}
