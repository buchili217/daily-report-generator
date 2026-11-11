"""命令行入口：初始化数据库、运行流水线、启动 API 服务。"""

from __future__ import annotations

import argparse
import asyncio
from datetime import date


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="daily-report", description="智能日报生成器 v1")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="运行指定日期的日报流水线")
    run.add_argument("--date", default=date.today().isoformat())
    run.add_argument("--team-id", type=int, default=None)
    run.add_argument("--member-id", type=int, default=None)

    sub.add_parser("init-db", help="创建数据库表")
    sub.add_parser("seed-demo", help="写入演示成员与团队")
    sub.add_parser("serve", help="启动 FastAPI 服务")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "init-db":
        from daily_report.db import init_db

        init_db()
        print("database initialized")
        return 0

    if args.command == "serve":
        import uvicorn

        from daily_report.api import create_app
        from daily_report.config import get_settings

        settings = get_settings()
        uvicorn.run(create_app(), host="0.0.0.0", port=settings.app_port)
        return 0

    if args.command == "run":
        from daily_report.service import build_service, run_once

        target = date.fromisoformat(args.date)
        return asyncio.run(run_once(build_service(), target, args.team_id, args.member_id))

    if args.command == "seed-demo":
        from daily_report.service import build_service, seed_demo

        seed_demo(build_service())
        print("demo data seeded")
        return 0

    return 1
