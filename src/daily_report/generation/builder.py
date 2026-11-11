"""草稿构建：模板生成四段式日报，可选接入模型润色并降级。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from typing import Any

from daily_report.collectors.base import CollectedEvent
from daily_report.generation.attribution import Attribution
from daily_report.generation.llm import LLMProvider

SECTIONS = ("done", "doing", "risk", "plan")

SECTION_TITLES = {
    "done": "今日完成",
    "doing": "进行中",
    "risk": "风险与阻塞",
    "plan": "明日计划",
}

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"index": {"type": "integer"}, "content": {"type": "string"}},
                "required": ["index", "content"],
            },
        }
    },
    "required": ["items"],
}


@dataclass
class DraftItem:
    content: str
    section: str
    source_event_ids: list[int] = field(default_factory=list)
    confidence: float = 1.0
    status: str = "auto"
    manual: bool = False


@dataclass
class ReportDraft:
    member_id: int
    report_date: str
    sections: dict[str, list[DraftItem]]
    provider_used: str | None = None
    degraded: bool = False


def _section_for(attribution: Attribution) -> str:
    event: CollectedEvent = attribution.event
    if (
        attribution.status == "auto"
        and event.event_type == "task_update"
        and str(event.payload.get("status", "")).lower() in {"blocked", "overdue"}
    ):
        return "risk"
    return "done" if attribution.status == "auto" else "doing"


def template_draft(
    member_id: int, report_date: str, attributions: list[Attribution]
) -> ReportDraft:
    sections: dict[str, list[DraftItem]] = {section: [] for section in SECTIONS}
    for attribution in attributions:
        if attribution.status == "dropped":
            continue
        section = _section_for(attribution)
        source_ids = [attribution.event.db_id] if attribution.event.db_id is not None else []
        sections[section].append(
            DraftItem(
                content=attribution.event.title,
                section=section,
                source_event_ids=source_ids,
                confidence=attribution.confidence,
                status=attribution.status,
            )
        )
    return ReportDraft(member_id=member_id, report_date=report_date, sections=sections)


def _flatten(draft: ReportDraft) -> list[tuple[str, DraftItem]]:
    return [
        (section, item)
        for section in SECTIONS
        for item in draft.sections.get(section, [])
    ]


def build_prompt(draft: ReportDraft) -> str:
    lines = [
        "把下列工作事实改写为日报条目。要求：",
        "1) 只改写措辞，不得新增事实；2) 每条保留原序号；",
        '3) 输出 JSON：{"items":[{"index":0,"content":"..."}]}。',
        "工作事实：",
    ]
    for index, (section, item) in enumerate(_flatten(draft)):
        lines.append(f"{index}. [{SECTION_TITLES[section]}] {item.content}")
    return "\n".join(lines)


def merge_polished(draft: ReportDraft, raw: str) -> ReportDraft:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return replace(draft, degraded=True)
    entries = data.get("items")
    if not isinstance(entries, list):
        return replace(draft, degraded=True)

    flat = _flatten(draft)
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        index = entry.get("index")
        content = entry.get("content")
        if not isinstance(index, int) or not isinstance(content, str) or not content.strip():
            continue
        if 0 <= index < len(flat):
            flat[index][1].content = content.strip()
    return draft


async def build_report(
    member_id: int,
    report_date: str,
    attributions: list[Attribution],
    provider: LLMProvider | None = None,
    timeout: float = 20.0,
) -> ReportDraft:
    draft = template_draft(member_id, report_date, attributions)
    if provider is None or not any(draft.sections.values()):
        return draft
    try:
        raw = await provider.generate(build_prompt(draft), SCHEMA, timeout)
    except Exception:  # noqa: BLE001 - 模型失败必须降级，不阻断日报
        return replace(draft, degraded=True)
    merged = merge_polished(draft, raw)
    return replace(merged, provider_used=provider.name, degraded=merged.degraded)


def render_markdown(draft: ReportDraft) -> str:
    lines: list[str] = []
    for section in SECTIONS:
        items = draft.sections.get(section, [])
        if not items:
            continue
        lines.append(f"**{SECTION_TITLES[section]}**")
        lines.extend(f"- {item.content}" for item in items)
        lines.append("")
    return "\n".join(lines).strip() or "今日暂无可采集的工作数据。"
