"""团队汇总：只聚合已提交日报，不生成排名。"""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy.orm import Session

from daily_report.generation.builder import SECTION_TITLES, SECTIONS
from daily_report.repositories import (
    MemberRepository,
    ReportRepository,
    TeamRepository,
)


@dataclass
class TeamDigest:
    team_id: int
    report_date: str
    content_md: str
    member_count: int
    submitted_count: int


def build_team_digest(session: Session, team_id: int, report_date: str) -> TeamDigest:
    team = TeamRepository(session).get(team_id)
    if team is None:
        raise ValueError(f"team not found: {team_id}")
    members = MemberRepository(session)
    reports = ReportRepository(session)
    member_ids = TeamRepository(session).member_ids(team_id)
    submitted = {
        report.member_id: report
        for report in reports.list_submitted(team_id, report_date)
    }

    lines = [f"## 团队日报（{report_date}）", ""]
    submitted_count = 0
    for member_id in member_ids:
        member = members.get(member_id)
        if member is None:
            continue
        report = submitted.get(member_id)
        lines.append(f"### {member.name}")
        if report is None:
            lines.append("- 未提交")
            lines.append("")
            continue
        submitted_count += 1
        items = reports.items(report.id)
        if not items:
            lines.append("- 无条目")
        for section in SECTIONS:
            section_items = [item for item in items if item.section == section]
            if not section_items:
                continue
            lines.append(f"**{SECTION_TITLES[section]}**")
            for item in section_items:
                lines.append(f"- {item.content}")
        lines.append("")

    lines.append("> 本汇总仅用于进度同步，不包含排名或绩效评价。")
    return TeamDigest(
        team_id=team_id,
        report_date=report_date,
        content_md="\n".join(lines),
        member_count=len(member_ids),
        submitted_count=submitted_count,
    )


def digest_snapshot(digest: TeamDigest) -> str:
    return json.dumps(
        {
            "team_id": digest.team_id,
            "report_date": digest.report_date,
            "member_count": digest.member_count,
            "submitted_count": digest.submitted_count,
        },
        ensure_ascii=False,
    )
