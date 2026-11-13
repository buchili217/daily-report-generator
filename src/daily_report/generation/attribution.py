"""协作成果归属：按角色与置信度分为自动写入 / 待确认 / 丢弃。"""

from __future__ import annotations

from dataclasses import dataclass

from daily_report.collectors.base import CollectedEvent

ROLE_CONFIDENCE = {
    "owner": 1.0,
    "reviewer": 0.8,
    "collaborator": 0.6,
    "attendee": 0.6,
}

AUTO_THRESHOLD = 0.9
PENDING_THRESHOLD = 0.5


@dataclass
class Attribution:
    event: CollectedEvent
    member_open_id: str
    role: str
    confidence: float
    status: str  # auto | pending | dropped


def _classify(confidence: float) -> str:
    if confidence >= AUTO_THRESHOLD:
        return "auto"
    if confidence >= PENDING_THRESHOLD:
        return "pending"
    return "dropped"


def attribute(events: list[CollectedEvent], member_open_id: str) -> list[Attribution]:
    results: list[Attribution] = []
    for event in events:
        candidates: list[tuple[str, float]] = []
        if event.owner_open_id == member_open_id:
            candidates.append(("owner", event.confidence))
        for participant in event.participants:
            if participant.open_id == member_open_id:
                candidates.append(
                    (participant.role, min(event.confidence, participant.confidence))
                )
        if not candidates:
            continue
        role, confidence = max(candidates, key=lambda item: item[1])
        results.append(
            Attribution(
                event=event,
                member_open_id=member_open_id,
                role=role,
                confidence=round(confidence, 3),
                status=_classify(confidence),
            )
        )
    return results
