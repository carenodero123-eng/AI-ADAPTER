"""Parsing and validation of the JSON model version manifest."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.model_catalog.errors import ModelCatalogConfigurationError
from app.model_catalog.versions import ModelCatalog, ModelVersion

_MAX_MANIFEST_BYTES = 256 * 1024


class ModelVersionManifest(BaseModel):
    """The only accepted top-level manifest shape."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    models: list[ModelVersion] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def _unique_models(self) -> ModelVersionManifest:
        seen: set[tuple[str, str]] = set()
        for entry in self.models:
            key = (entry.provider, entry.model)
            if key in seen:
                raise ValueError(
                    f"duplicate model version entry for "
                    f"'{entry.provider}/{entry.model}'"
                )
            seen.add(key)
        return self


def _validation_summary(error: ValidationError) -> str:
    details = error.errors(include_input=False, include_url=False)
    return "; ".join(
        f"{'.'.join(str(part) for part in detail['loc'])}: {detail['msg']}"
        for detail in details[:5]
    )


def load_model_catalog(path: str | Path) -> ModelCatalog:
    """Load a bounded JSON manifest and return a validated catalog."""

    manifest_path = Path(path).expanduser()
    if manifest_path.suffix.lower() != ".json":
        raise ModelCatalogConfigurationError(
            "Model version manifest must be a .json file."
        )
    if not manifest_path.is_file():
        raise ModelCatalogConfigurationError(
            f"Model version manifest '{manifest_path.name}' does not exist."
        )

    try:
        with manifest_path.open("rb") as handle:
            raw_bytes = handle.read(_MAX_MANIFEST_BYTES + 1)
    except OSError as error:
        raise ModelCatalogConfigurationError(
            f"Model version manifest '{manifest_path.name}' cannot be read."
        ) from error
    if len(raw_bytes) > _MAX_MANIFEST_BYTES:
        raise ModelCatalogConfigurationError(
            "Model version manifest exceeds the 256 KiB size limit."
        )

    try:
        raw_text = raw_bytes.decode("utf-8")
    except UnicodeError as error:
        raise ModelCatalogConfigurationError(
            f"Model version manifest '{manifest_path.name}' cannot be read as UTF-8."
        ) from error

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as error:
        raise ModelCatalogConfigurationError(
            "Model version manifest is not valid JSON "
            f"(line {error.lineno}, column {error.colno})."
        ) from error

    try:
        manifest = ModelVersionManifest.model_validate(payload)
    except ValidationError as error:
        raise ModelCatalogConfigurationError(
            "Model version manifest failed validation: "
            f"{_validation_summary(error)}"
        ) from error

    return ModelCatalog(manifest.models)
