"""Validated model version records and an immutable lookup catalog."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ModelStatus = Literal["active", "deprecated", "retired"]

_PROVIDER_PATTERN = r"^[a-z][a-z0-9_-]{0,31}$"
_VERSION_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$"


class ModelVersion(BaseModel):
    """One provider model release tracked by the deployment manifest."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str = Field(
        min_length=1,
        max_length=32,
        pattern=_PROVIDER_PATTERN,
    )
    model: str = Field(min_length=1, max_length=100)
    version: str = Field(
        min_length=1,
        max_length=64,
        pattern=_VERSION_PATTERN,
    )
    status: ModelStatus = "active"
    released_on: date | None = None
    notes: str | None = Field(default=None, max_length=240)

    @field_validator("model")
    @classmethod
    def _validate_model(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("model must not be blank")
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("model must not contain control characters")
        return value

    @field_validator("notes")
    @classmethod
    def _normalize_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split()).strip()
        return normalized or None


class ModelCatalog:
    """Unique, sorted model versions keyed by provider and model name."""

    def __init__(self, entries: Iterable[ModelVersion]) -> None:
        ordered = tuple(
            sorted(
                entries,
                key=lambda entry: (entry.provider, entry.model, entry.version),
            )
        )
        if not ordered:
            raise ValueError("model version catalog must not be empty")

        index: dict[tuple[str, str], ModelVersion] = {}
        for entry in ordered:
            key = (entry.provider, entry.model)
            if key in index:
                raise ValueError(
                    f"duplicate model version entry for "
                    f"'{entry.provider}/{entry.model}'"
                )
            index[key] = entry

        self._entries = ordered
        self._index = index

    @property
    def entries(self) -> tuple[ModelVersion, ...]:
        return self._entries

    def get(self, provider: str, model: str) -> ModelVersion | None:
        return self._index.get((provider, model))

    def status_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for entry in self._entries:
            counts[entry.status] = counts.get(entry.status, 0) + 1
        return counts
