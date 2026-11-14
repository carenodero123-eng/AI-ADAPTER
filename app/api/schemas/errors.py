"""Public error response contract."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ApiErrorDetail(BaseModel):
    code: str
    message: str
    provider: str | None = None
    retryable: bool


class ErrorResponse(BaseModel):
    error: ApiErrorDetail
    request_id: str | None = Field(default=None)
