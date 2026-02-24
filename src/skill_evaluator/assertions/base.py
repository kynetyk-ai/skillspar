"""Assertion result types."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class AssertionStatus(Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass(frozen=True)
class AssertionResult:
    status: AssertionStatus
    assertion_type: str
    message: str
    details: dict[str, Any] | None = None
