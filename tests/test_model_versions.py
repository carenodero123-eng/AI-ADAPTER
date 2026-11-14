"""Model version manifest, catalog, and administrative endpoint tests."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from app.core.config import Settings
from app.main import create_app
from app.model_catalog.errors import ModelCatalogConfigurationError
from app.model_catalog.factory import build_model_catalog
from app.model_catalog.manifest import load_model_catalog
from app.providers.factory import build_provider_registry
from app.providers.fake import FakeProvider
from app.providers.registry import ProviderRegistry
from fastapi.testclient import TestClient
from pydantic import ValidationError

pytestmark = pytest.mark.regression

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_MANIFEST = PROJECT_ROOT / "config" / "model_versions.json"
USER_KEY = "catalog-user-key-0123456789abcdef"
ADMIN_KEY = "catalog-admin-key-0123456789abcdef"


def _entry(model: str, *, status: str = "active", version: str = "1.0.0") -> dict:
    return {
        "provider": "fake",
        "model": model,
        "version": version,
        "status": status,
    }


def _write_manifest(tmp_path: Path, models: list[dict]) -> Path:
    path = tmp_path / "model_versions.json"
    path.write_text(
        json.dumps({"schema_version": 1, "models": models}),
        encoding="utf-8",
    )
    return path


def _registry(models: tuple[str, ...] = ("fake-small", "fake-large")) -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(
        FakeProvider(models=list(models), default_model=models[0])
    )
    return registry


def _settings(*, manifest: str = "", **overrides) -> Settings:
    values = {
        "_env_file": None,
        "environment": "test",
        "log_level": "WARNING",
        "log_format": "console",
        "model_version_manifest": manifest,
    }
    values.update(overrides)
    return Settings(**values)


def test_catalog_loads_sorted_unique_entries(tmp_path: Path) -> None:
    path = _write_manifest(
        tmp_path,
        [
            _entry("fake-small"),
            _entry("fake-large", version="1.1.0"),
        ],
    )

    catalog = load_model_catalog(path)

    assert [(entry.model, entry.version) for entry in catalog.entries] == [
        ("fake-large", "1.1.0"),
        ("fake-small", "1.0.0"),
    ]
    assert catalog.get("fake", "fake-small") is not None
    assert catalog.get("fake", "missing") is None
    assert catalog.status_counts() == {"active": 2}


def test_shipped_manifest_covers_default_provider_configuration() -> None:
    registry = build_provider_registry(
        Settings(_env_file=None, environment="test")
    )

    catalog = build_model_catalog(_settings(manifest=str(PROJECT_MANIFEST)), registry)

    assert catalog is not None
    for provider in registry.list_providers():
        for model in provider.models:
            entry = catalog.get(provider.name, model)
            assert entry is not None
            assert entry.status == "active"
    assert catalog.get("openai", "gpt-4o-mini") is not None


def test_missing_configured_model_fails_closed(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path, [_entry("fake-small")])
    settings = _settings(manifest=str(path))

    with pytest.raises(ModelCatalogConfigurationError, match="fake-large"):
        build_model_catalog(settings, _registry())


def test_retired_configured_model_fails_closed(tmp_path: Path) -> None:
    path = _write_manifest(
        tmp_path,
        [_entry("fake-small"), _entry("fake-large", status="retired")],
    )

    with pytest.raises(ModelCatalogConfigurationError, match="retired"):
        build_model_catalog(_settings(manifest=str(path)), _registry())


def test_deprecated_non_default_model_is_allowed_with_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = _write_manifest(
        tmp_path,
        [_entry("fake-small"), _entry("fake-large", status="deprecated")],
    )
    caplog.set_level(logging.WARNING, logger="app.model_catalog.factory")

    catalog = build_model_catalog(_settings(manifest=str(path)), _registry())

    assert catalog is not None
    warnings = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "model.version.deprecated"
    ]
    assert len(warnings) == 1
    assert warnings[0].provider == "fake"
    assert warnings[0].model == "fake-large"


@pytest.mark.parametrize("status", ["deprecated", "retired"])
def test_default_model_must_be_active(tmp_path: Path, status: str) -> None:
    path = _write_manifest(
        tmp_path,
        [_entry("fake-small", status=status), _entry("fake-large")],
    )

    with pytest.raises(ModelCatalogConfigurationError, match="retired|active"):
        build_model_catalog(_settings(manifest=str(path)), _registry())


def test_duplicate_model_entries_are_rejected(tmp_path: Path) -> None:
    path = _write_manifest(
        tmp_path,
        [_entry("fake-small"), _entry("fake-small", version="2.0.0")],
    )

    with pytest.raises(ModelCatalogConfigurationError, match="duplicate"):
        load_model_catalog(path)


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("{", "not valid JSON"),
        (
            json.dumps(
                {
                    "schema_version": 1,
                    "models": [
                        {
                            "provider": "fake",
                            "model": "fake-small",
                            "version": "bad version",
                        }
                    ],
                }
            ),
            "failed validation",
        ),
        (json.dumps({"schema_version": 2, "models": []}), "failed validation"),
    ],
)
def test_invalid_manifest_content_is_rejected(
    tmp_path: Path, content: str, expected: str
) -> None:
    path = tmp_path / "model_versions.json"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(ModelCatalogConfigurationError, match=expected):
        load_model_catalog(path)


def test_missing_manifest_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ModelCatalogConfigurationError, match="does not exist"):
        load_model_catalog(tmp_path / "missing.json")


def test_oversized_manifest_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "model_versions.json"
    path.write_bytes(b"x" * (256 * 1024 + 1))

    with pytest.raises(ModelCatalogConfigurationError, match="256 KiB"):
        load_model_catalog(path)


def test_non_utf8_manifest_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "model_versions.json"
    path.write_bytes(
        b'{"schema_version":1,"models":[{"provider":"fake",'
        b'"model":"fake-small","version":"\xff"}]}'
    )

    with pytest.raises(ModelCatalogConfigurationError, match="UTF-8"):
        load_model_catalog(path)


def test_blank_manifest_disables_catalog() -> None:
    assert build_model_catalog(_settings(), _registry()) is None


def test_manifest_setting_requires_json_path() -> None:
    with pytest.raises(ValidationError, match="\\.json"):
        Settings(_env_file=None, model_version_manifest="model_versions.txt")


def test_app_startup_fails_closed_on_catalog_mismatch(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path, [_entry("fake-small")])

    with pytest.raises(ModelCatalogConfigurationError, match="fake-large"):
        create_app(_settings(manifest=str(path)))


def test_model_versions_endpoint_requires_admin_and_marks_configured_entries() -> None:
    settings = _settings(
        manifest=str(PROJECT_MANIFEST),
        security_require_auth=True,
        security_api_keys=USER_KEY,
        security_admin_api_keys=ADMIN_KEY,
        security_rate_limit_requests=0,
    )

    with TestClient(create_app(settings)) as client:
        unauthorized = client.get("/api/v1/model-versions")
        forbidden = client.get(
            "/api/v1/model-versions",
            headers={"Authorization": f"Bearer {USER_KEY}"},
        )
        allowed = client.get(
            "/api/v1/model-versions",
            headers={"Authorization": f"Bearer {ADMIN_KEY}"},
        )
        readiness = client.get("/health/ready")

    assert unauthorized.status_code == 401
    assert unauthorized.json()["error"]["code"] == "authentication_required"
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "permission_denied"
    assert allowed.status_code == 200

    items = allowed.json()["models"]
    assert [(item["provider"], item["model"]) for item in items] == sorted(
        (item["provider"], item["model"]) for item in items
    )
    configured = {
        (item["provider"], item["model"]): item["configured"] for item in items
    }
    assert configured[("fake", "fake-small")] is True
    assert configured[("fake", "fake-large")] is True
    assert configured[("openai", "gpt-4o-mini")] is False
    assert all(item["version"] for item in items)

    assert readiness.status_code == 200
    assert readiness.json()["checks"]["models"] == "ok"


def test_model_versions_endpoint_reports_unavailable_catalog(client) -> None:
    response = client.get("/api/v1/model-versions")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "model_catalog_unavailable"
    assert response.json()["error"]["retryable"] is False
