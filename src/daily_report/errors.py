"""统一错误码与异常，契约见 design.md 4.6。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ErrorCode(StrEnum):
    COL_AUTH = "E-COL-001"
    COL_RATE_LIMITED = "E-COL-002"
    COL_TIMEOUT = "E-COL-003"
    GEN_SCHEMA = "E-GEN-001"
    GEN_NO_SOURCE = "E-GEN-002"
    GEN_LLM = "E-GEN-003"
    PUSH_AUTH = "E-PUSH-001"
    PUSH_TARGET = "E-PUSH-002"
    PUSH_NOT_CONFIGURED = "E-PUSH-010"


@dataclass
class AppError(Exception):
    code: ErrorCode
    message: str = ""
    retryable: bool = False

    def __post_init__(self) -> None:
        super().__init__(self.message or self.code.value)

    def __str__(self) -> str:
        return f"{self.code.value}: {self.message}" if self.message else self.code.value
