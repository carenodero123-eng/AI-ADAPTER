"""Health and metadata endpoint tests, including async transport coverage."""

from __future__ import annotations

import uuid

import httpx
import pytest


def test_liveness_returns_service_metadata(client) -> None:
    response = client.get("/health/live")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "AI Adapter"
    assert body["environment"] == "test"
    assert body["version"] == "0.1.0"
    assert body["uptime_seconds"] >= 0


def test_readiness_reports_checks(client) -> None:
    response = client.get("/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"] == {"configuration": "ok", "logging": "ok"}


def test_system_info_does_not_expose_secrets(client) -> None:
    response = client.get("/api/v1/system/info")

    assert response.status_code == 200
    body = response.json()
    assert body["api_prefix"] == "/api/v1"
    assert body["docs_url"] == "/docs"
    assert body["uptime_seconds"] >= 0
    assert "secret" not in str(body).lower()
    assert "key" not in str(body).lower()


def test_valid_request_id_is_echoed(client) -> None:
    response = client.get("/health/live", headers={"X-Request-ID": "client-req-0001"})

    assert response.headers["X-Request-ID"] == "client-req-0001"


def test_missing_request_id_is_generated(client) -> None:
    response = client.get("/health/live")

    generated = response.headers["X-Request-ID"]
    assert uuid.UUID(generated)
    assert len(generated) == 32


def test_invalid_request_id_is_replaced(client) -> None:
    response = client.get("/health/live", headers={"X-Request-ID": "bad id!"})

    generated = response.headers["X-Request-ID"]
    assert generated != "bad id!"
    assert uuid.UUID(generated)


@pytest.mark.asyncio
async def test_health_over_async_asgi_transport(app) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
