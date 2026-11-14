"""Administrative model version inventory schemas."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from app.model_catalog.versions import ModelStatus


class ModelVersionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=32)
    model: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=64)
    status: ModelStatus
    released_on: date | None = None
    notes: str | None = Field(default=None, max_length=240)
    configured: bool


class ModelVersionList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    models: list[ModelVersionItem]
