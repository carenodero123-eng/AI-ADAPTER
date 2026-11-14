"""Budget-related application errors."""

from __future__ import annotations

from app.core.errors import ApplicationError

_MESSAGES = {
    "per_request": "The estimated request cost exceeds the per-request budget limit.",
    "daily": "The daily budget limit has been reached.",
    "monthly": "The monthly budget limit has been reached.",
}


class BudgetExceededError(ApplicationError):
    code = "budget_exceeded"
    status_code = 402
    retryable = False

    def __init__(self, scope: str) -> None:
        if scope not in _MESSAGES:
            raise ValueError(f"unknown budget scope: {scope}")
        super().__init__(_MESSAGES[scope])
        self.scope = scope
