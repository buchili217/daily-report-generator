"""草稿校验：段落合法、内容非空、条目必须有来源或标记为手填。"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from daily_report.errors import ErrorCode
from daily_report.generation.builder import SECTIONS, DraftItem, ReportDraft


@dataclass
class ValidationResult:
    draft: ReportDraft
    removed: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_draft(draft: ReportDraft) -> ValidationResult:
    errors: list[str] = []
    removed = 0
    sections: dict[str, list[DraftItem]] = {section: [] for section in SECTIONS}

    for section, items in draft.sections.items():
        if section not in SECTIONS:
            errors.append(f"{ErrorCode.GEN_SCHEMA.value}: 未知段落 {section}")
            continue
        for item in items:
            if not item.content.strip():
                removed += 1
                continue
            if not item.source_event_ids and not item.manual:
                removed += 1
                errors.append(
                    f"{ErrorCode.GEN_NO_SOURCE.value}: 条目无来源被剔除: {item.content[:30]}"
                )
                continue
            if item.confidence < 0 or item.confidence > 1:
                removed += 1
                errors.append(f"{ErrorCode.GEN_NO_SOURCE.value}: 置信度非法: {item.content[:30]}")
                continue
            sections[section].append(item)

    validated = replace(draft, sections=sections)
    return ValidationResult(draft=validated, removed=removed, errors=errors)
