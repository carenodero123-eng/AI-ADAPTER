"""Application factory behavior tests."""

from __future__ import annotations

from app.core.config import Settings
from app.main import create_app
from fastapi import FastAPI


def test_factory_returns_configured_app(settings: Settings) -> None:
    app = create_app(settings)

    assert isinstance(app, FastAPI)
    assert app.title == settings.app_name
    assert app.version == "0.1.0"
    paths = set(app.openapi()["paths"])
    assert "/health/live" in paths
    assert "/api/v1/system/info" in paths


def test_production_disables_interactive_docs() -> None:
    settings = Settings(
        _env_file=None,
        environment="production",
        security_require_auth=True,
        security_api_keys="prod-user-key-1234567890",
    )
    app = create_app(settings)

    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None


def test_custom_api_prefix_is_respected() -> None:
    from fastapi.testclient import TestClient

    settings = Settings(_env_file=None, environment="test", api_prefix="/internal/v2")
    app = create_app(settings)

    with TestClient(app) as client:
        assert client.get("/internal/v2/system/info").status_code == 200
        assert client.get("/api/v1/system/info").status_code == 404


def test_app_version_setting_is_consistent_across_surfaces() -> None:
    from fastapi.testclient import TestClient

    settings = Settings(_env_file=None, environment="test", app_version="2.3.4")
    app = create_app(settings)

    assert app.version == "2.3.4"
    assert app.openapi()["info"]["version"] == "2.3.4"

    with TestClient(app) as client:
        health = client.get("/health/live").json()
        info = client.get("/api/v1/system/info").json()

    assert health["version"] == "2.3.4"
    assert info["version"] == "2.3.4"
