"""Structured errors for resilient-read."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ResilientReadError(Exception):
    error: str
    reason_hint: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)

    def to_envelope(self) -> dict[str, Any]:
        return {
            "ok": False,
            "error": self.error,
            "reason_hint": self.reason_hint,
            "message": self.message,
            "context": self.context,
        }
