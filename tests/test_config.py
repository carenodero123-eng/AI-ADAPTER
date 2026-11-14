"""Configuration loading and validation tests."""

from __future__ import annotations

import pytest
from app import __version__
from app.core.config import Settings
from pydantic import ValidationError


def test_defaults_are_valid() -> None:
    settings = Settings(_env_file=None)

    assert settings.app_name == "AI Adapter"
    assert settings.app_version == __version__
    assert settings.api_prefix == "/api/v1"
    assert settings.is_production is False


def test_environment_variables_override_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_PORT", "9100")
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("LOG_FORMAT", "console")

    settings = Settings(_env_file=None)

    assert settings.api_port == 9100
    assert settings.environment == "staging"
    assert settings.log_format == "console"


def test_cors_origins_are_split_and_trimmed() -> None:
    settings = Settings(
        _env_file=None,
        cors_origins="http://a.test, http://b.test ,",
    )

    assert settings.cors_origin_list == ["http://a.test", "http://b.test"]


@pytest.mark.parametrize("prefix", ["api/v1", "/api/v1/", ""])
def test_invalid_api_prefix_is_rejected(prefix: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, api_prefix=prefix)


def test_invalid_request_id_header_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, request_id_header="X Request ID")


def test_port_must_be_in_range() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, api_port=70000)


def test_fake_model_configuration_is_parsed() -> None:
    settings = Settings(
        _env_file=None,
        fake_provider_models=" small , large ",
        fake_provider_default_model="large",
    )

    assert settings.fake_model_list == ["small", "large"]
    assert settings.fake_provider_default_model == "large"


def test_fake_default_model_must_be_listed() -> None:
    with pytest.raises(ValidationError, match="fake_provider_default_model"):
        Settings(
            _env_file=None,
            fake_provider_models="small,large",
            fake_provider_default_model="missing",
        )


def test_provider_settings_are_validated() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, default_provider="Invalid Provider")

    with pytest.raises(ValidationError, match="duplicates"):
        Settings(_env_file=None, fake_provider_models="small,small")


def test_openai_settings_are_normalized_and_disabled_by_default() -> None:
    settings = Settings(
        _env_file=None,
        openai_api_key="  ",
        openai_base_url="https://gateway.test/v1/",
        openai_models=" mini , large ",
        openai_default_model="large",
    )

    assert settings.openai_enabled is False
    assert settings.openai_api_key is None
    assert settings.openai_base_url == "https://gateway.test/v1"
    assert settings.openai_model_list == ["mini", "large"]
    assert settings.openai_timeout_seconds == 30.0


def test_openai_settings_accept_a_key_without_exposing_it() -> None:
    secret = "sk-config-secret-12345678"
    settings = Settings(_env_file=None, openai_api_key=secret)

    assert settings.openai_enabled is True
    assert secret not in repr(settings)
    assert settings.openai_api_key.get_secret_value() == secret


def test_openai_default_model_must_be_listed() -> None:
    with pytest.raises(ValidationError, match="openai_default_model"):
        Settings(
            _env_file=None,
            openai_models="mini,large",
            openai_default_model="missing",
        )


@pytest.mark.parametrize(
    "base_url",
    ["api.openai.com/v1", "ftp://api.openai.com/v1", "/v1", "https://api.openai.com/v1?x=1"],
)
def test_invalid_openai_base_url_is_rejected(base_url: str) -> None:
    with pytest.raises(ValidationError, match="openai_base_url"):
        Settings(_env_file=None, openai_base_url=base_url)


def test_openai_timeout_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, openai_timeout_seconds=0)
