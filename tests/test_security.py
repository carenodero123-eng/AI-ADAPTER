"""Stage E authentication, authorization, and rate limiting."""

from __future__ import annotations

import logging

import pytest
from app.core.config import Settings
from app.main import create_app
from app.security.errors import RateLimitExceededError
from app.security.manager import SecurityManager
from app.security.rate_limit import RateLimiter
from fastapi.testclient import TestClient
from pydantic import ValidationError

USER_KEY = "user-key-0123456789abcdef"
ADMIN_KEY = "admin-key-0123456789abcdef"
OTHER_KEY = "other-key-0123456789abcdef"


def _settings(**overrides) -> Settings:
    values = {
        "security_require_auth": True,
        "security_api_keys": USER_KEY,
        "security_admin_api_keys": ADMIN_KEY,
        "reliability_backoff_base_seconds": 0.0,
        "reliability_backoff_max_seconds": 0.0,
        "reliability_jitter_seconds": 0.0,
        "log_level": "WARNING",
        "log_format": "console",
    }
    values.update(overrides)
    return Settings(
        _env_file=None,
        environment="test",
        **values,
    )


def _client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


def _headers(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def _body() -> dict:
    return {"messages": [{"role": "user", "content": "hello"}]}


def test_security_manager_resolves_roles_without_retaining_tokens() -> None:
    manager = SecurityManager(user_keys=[USER_KEY], admin_keys=[ADMIN_KEY])

    user = manager.authenticate(USER_KEY)
    admin = manager.authenticate(ADMIN_KEY)

    assert user is not None
    assert user.role == "user"
    assert user.rate_limit_key.startswith("key:")
    assert admin is not None
    assert admin.role == "admin"
    assert manager.authenticate("wrong-key-0123456789abcdef") is None
    assert manager.authenticate("") is None
    assert manager.user_key_count == 1
    assert manager.admin_key_count == 1
    assert USER_KEY not in repr(user)
    assert ADMIN_KEY not in repr(admin)


def test_security_configuration_is_validated() -> None:
    with pytest.raises(ValidationError, match="security_api_keys"):
        Settings(_env_file=None, security_require_auth=True)
    with pytest.raises(ValidationError, match="security_require_auth"):
        Settings(_env_file=None, environment="production")
    with pytest.raises(ValidationError, match="must not overlap"):
        Settings(
            _env_file=None,
            security_api_keys=USER_KEY,
            security_admin_api_keys=USER_KEY,
        )
    with pytest.raises(ValidationError, match="16-512"):
        Settings(_env_file=None, security_api_keys="short")
    with pytest.raises(ValidationError, match="duplicates"):
        Settings(_env_file=None, security_api_keys=f"{USER_KEY},{USER_KEY}")


def test_missing_and_invalid_credentials_are_rejected() -> None:
    with _client(_settings()) as client:
        missing = client.post("/api/v1/generate", json=_body())
        basic = client.post(
            "/api/v1/generate",
            json=_body(),
            headers={"Authorization": f"Basic {USER_KEY}"},
        )
        invalid = client.post(
            "/api/v1/generate",
            json=_body(),
            headers=_headers("wrong-key-0123456789abcdef"),
        )

    assert missing.status_code == 401
    assert missing.headers["WWW-Authenticate"] == "Bearer"
    assert missing.json()["error"]["code"] == "authentication_required"
    assert missing.json()["error"]["retryable"] is False
    assert missing.json()["request_id"] == missing.headers["X-Request-ID"]
    assert basic.status_code == 401
    assert invalid.status_code == 401


def test_valid_user_can_generate_and_receives_rate_limit_headers() -> None:
    with _client(_settings()) as client:
        response = client.post(
            "/api/v1/generate", json=_body(), headers=_headers(USER_KEY)
        )

    assert response.status_code == 200
    assert response.json()["provider"] == "fake"
    assert response.headers["X-RateLimit-Limit"] == "60"
    assert response.headers["X-RateLimit-Remaining"] == "59"


def test_admin_operations_require_an_admin_key() -> None:
    with _client(_settings()) as client:
        anonymous = client.get("/api/v1/providers")
        user = client.get("/api/v1/providers", headers=_headers(USER_KEY))
        admin = client.get("/api/v1/providers", headers=_headers(ADMIN_KEY))

    assert anonymous.status_code == 401
    assert user.status_code == 403
    assert user.json()["error"]["code"] == "permission_denied"
    assert admin.status_code == 200
    assert [item["name"] for item in admin.json()] == ["fake"]


def test_admin_key_can_also_generate_and_role_is_logged(caplog) -> None:
    caplog.set_level(logging.INFO)

    with _client(_settings(log_level="INFO")) as client:
        response = client.post(
            "/api/v1/generate", json=_body(), headers=_headers(ADMIN_KEY)
        )

    assert response.status_code == 200
    summaries = [
        record for record in caplog.records if record.name == "app.api.generation"
    ]
    assert summaries
    assert summaries[-1].auth_role == "admin"
    assert ADMIN_KEY not in " ".join(str(record.__dict__) for record in caplog.records)


def test_credentials_never_appear_in_logs(caplog) -> None:
    caplog.set_level(logging.DEBUG)

    with _client(_settings()) as client:
        client.post("/api/v1/generate", json=_body(), headers=_headers(OTHER_KEY))

    logged = " ".join(str(record.__dict__) for record in caplog.records)
    assert OTHER_KEY not in logged
    assert "Authorization" not in logged


def test_auth_disabled_allows_anonymous_access() -> None:
    settings = Settings(_env_file=None, environment="test", log_level="WARNING")
    with _client(settings) as client:
        response = client.post("/api/v1/generate", json=_body())

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_rate_limiter_window_reset_and_key_isolation() -> None:
    clock = [100.0]
    limiter = RateLimiter(
        max_requests=2, window_seconds=10.0, clock=lambda: clock[0]
    )

    first = await limiter.check("a")
    second = await limiter.check("a")
    assert first is not None and first.remaining == 1
    assert second is not None and second.remaining == 0

    with pytest.raises(RateLimitExceededError) as info:
        await limiter.check("a")
    assert info.value.retry_after_seconds == 10
    assert info.value.headers["Retry-After"] == "10"

    assert await limiter.check("b") is not None
    clock[0] += 10.0
    assert await limiter.check("a") is not None


@pytest.mark.asyncio
async def test_rate_limiter_can_be_disabled() -> None:
    limiter = RateLimiter(max_requests=0, window_seconds=60.0)
    assert limiter.enabled is False
    assert await limiter.check("any") is None

    with pytest.raises(ValueError):
        RateLimiter(max_requests=-1, window_seconds=60.0)
    with pytest.raises(ValueError):
        RateLimiter(max_requests=1, window_seconds=0)


def test_rate_limit_returns_429_and_retry_after() -> None:
    settings = _settings(security_rate_limit_requests=2)
    with _client(settings) as client:
        responses = [
            client.post("/api/v1/generate", json=_body(), headers=_headers(USER_KEY))
            for _ in range(3)
        ]

    assert [response.status_code for response in responses] == [200, 200, 429]
    limited = responses[2]
    assert limited.headers["Retry-After"] == "60"
    assert limited.headers["X-RateLimit-Limit"] == "2"
    assert limited.json()["error"]["code"] == "rate_limit_exceeded"
    assert limited.json()["error"]["retryable"] is True


def test_rate_limits_are_isolated_per_key() -> None:
    settings = _settings(
        security_rate_limit_requests=1,
        security_api_keys=f"{USER_KEY},{OTHER_KEY}",
    )
    with _client(settings) as client:
        user = client.post(
            "/api/v1/generate", json=_body(), headers=_headers(USER_KEY)
        )
        other = client.post(
            "/api/v1/generate", json=_body(), headers=_headers(OTHER_KEY)
        )
        user_again = client.post(
            "/api/v1/generate", json=_body(), headers=_headers(USER_KEY)
        )

    assert user.status_code == 200
    assert other.status_code == 200
    assert user_again.status_code == 429


def test_provider_health_requires_admin() -> None:
    with _client(_settings()) as client:
        user = client.get(
            "/api/v1/providers/fake/health", headers=_headers(USER_KEY)
        )
        admin = client.get(
            "/api/v1/providers/fake/health", headers=_headers(ADMIN_KEY)
        )

    assert user.status_code == 403
    assert admin.status_code == 200
    assert admin.json()["circuit"]["state"] == "closed"
