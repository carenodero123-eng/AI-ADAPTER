"""Typed application settings loaded from environment variables and .env."""

from __future__ import annotations

import re
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app import __version__
from app.budget.pricing import PricingRates

Environment = Literal["development", "test", "staging", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
LogFormat = Literal["json", "console"]

_PROVIDER_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")


def _default_provider_pricing() -> dict[str, PricingRates]:
    return {
        "fake": PricingRates.free(),
        "openai": PricingRates(
            input_per_million_usd=Decimal("0.15"),
            output_per_million_usd=Decimal("0.60"),
        ),
    }


def _normalize_model_list(value: str, field_name: str) -> str:
    models = [model.strip() for model in value.split(",") if model.strip()]
    if not models:
        raise ValueError(f"{field_name} must contain at least one model")
    if len(set(models)) != len(models):
        raise ValueError(f"{field_name} must not contain duplicates")
    if any(len(model) > 100 for model in models):
        raise ValueError(f"model names in {field_name} must be at most 100 characters")
    return ",".join(models)


class Settings(BaseSettings):
    """Runtime configuration.

    Every field can be overridden with an environment variable of the same
    name in upper case (for example ``API_PORT=9000``). Values in ``.env``
    are loaded as well; real environment variables take precedence.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "AI Adapter"
    app_version: str = __version__
    environment: Environment = "development"
    debug: bool = False

    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    api_prefix: str = "/api/v1"

    log_level: LogLevel = "INFO"
    log_format: LogFormat = "json"
    request_id_header: str = "X-Request-ID"

    cors_origins: str = "http://localhost:8501,http://127.0.0.1:8501"

    default_provider: str = "fake"
    fake_provider_models: str = "fake-small,fake-large"
    fake_provider_default_model: str = "fake-small"

    openai_api_key: SecretStr | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_models: str = "gpt-4o-mini,gpt-4o"
    openai_default_model: str = "gpt-4o-mini"
    openai_timeout_seconds: float = Field(default=30.0, gt=0.0, le=300.0)

    model_version_manifest: str = ""

    fault_report_max_tokens: int = Field(default=512, ge=1, le=8192)

    database_enabled: bool = False
    database_url: SecretStr = SecretStr(
        "sqlite+aiosqlite:///./data/ai_adapter.db"
    )
    database_echo: bool = False
    database_auto_create: bool = True
    database_pool_size: int = Field(default=5, ge=1, le=50)
    database_max_overflow: int = Field(default=10, ge=0, le=100)
    database_write_timeout_seconds: float = Field(default=2.0, gt=0.0, le=30.0)

    monitoring_query_timeout_seconds: float = Field(default=5.0, gt=0.0, le=60.0)
    monitoring_latency_sample_limit: int = Field(
        default=10_000, ge=10, le=100_000
    )

    reliability_max_attempts: int = Field(default=3, ge=1, le=10)
    reliability_backoff_base_seconds: float = Field(default=0.25, ge=0.0, le=30.0)
    reliability_backoff_max_seconds: float = Field(default=2.0, ge=0.0, le=60.0)
    reliability_jitter_seconds: float = Field(default=0.1, ge=0.0, le=10.0)
    reliability_timeout_seconds: float = Field(default=35.0, gt=0.0, le=300.0)
    reliability_circuit_failure_threshold: int = Field(default=3, ge=1, le=20)
    reliability_circuit_recovery_seconds: float = Field(
        default=30.0, gt=0.0, le=3600.0
    )
    reliability_secondary_provider: str = ""
    reliability_fallback_provider: str = "fake"

    security_require_auth: bool = False
    security_api_keys: SecretStr | None = None
    security_admin_api_keys: SecretStr | None = None
    security_rate_limit_requests: int = Field(default=60, ge=0, le=100_000)
    security_rate_limit_window_seconds: float = Field(
        default=60.0, gt=0.0, le=3600.0
    )

    budget_enforcement_enabled: bool = True
    budget_per_request_usd: Decimal = Field(default=Decimal("0.25"), ge=0)
    budget_daily_usd: Decimal = Field(default=Decimal("50"), ge=0)
    budget_monthly_usd: Decimal = Field(default=Decimal("500"), ge=0)
    budget_assumed_completion_tokens: int = Field(default=512, ge=1, le=8192)
    budget_provider_pricing: dict[str, PricingRates] = Field(
        default_factory=_default_provider_pricing
    )

    @field_validator("api_prefix")
    @classmethod
    def _validate_api_prefix(cls, value: str) -> str:
        value = value.strip()
        if not value.startswith("/") or value.endswith("/"):
            raise ValueError("api_prefix must start with '/' and must not end with '/'")
        return value

    @field_validator("request_id_header")
    @classmethod
    def _validate_request_id_header(cls, value: str) -> str:
        value = value.strip()
        if not value or not all(char.isalnum() or char == "-" for char in value):
            raise ValueError(
                "request_id_header must contain only letters, digits, and hyphens"
            )
        return value

    @field_validator("default_provider")
    @classmethod
    def _validate_default_provider(cls, value: str) -> str:
        value = value.strip().lower()
        if not _PROVIDER_NAME.fullmatch(value):
            raise ValueError(
                "default_provider must match ^[a-z][a-z0-9_-]{0,31}$"
            )
        return value

    @field_validator("fake_provider_models")
    @classmethod
    def _validate_fake_provider_models(cls, value: str) -> str:
        return _normalize_model_list(value, "fake_provider_models")

    @field_validator("database_url")
    @classmethod
    def _validate_database_url(cls, value: SecretStr) -> SecretStr:
        dsn = value.get_secret_value().strip()
        if not dsn:
            raise ValueError("database_url must not be blank")
        if any(char.isspace() for char in dsn):
            raise ValueError("database_url must not contain whitespace")
        if dsn.startswith("postgres://"):
            dsn = "postgresql+asyncpg://" + dsn.removeprefix("postgres://")
        elif dsn.startswith("postgresql://"):
            dsn = "postgresql+asyncpg://" + dsn.removeprefix("postgresql://")
        elif dsn.startswith("sqlite://"):
            dsn = "sqlite+aiosqlite://" + dsn.removeprefix("sqlite://")
        scheme = dsn.split("://", 1)[0].lower()
        if scheme not in {"postgresql+asyncpg", "sqlite+aiosqlite"}:
            raise ValueError(
                "database_url must use postgresql+asyncpg or sqlite+aiosqlite"
            )
        if scheme == "postgresql+asyncpg" and dsn == "postgresql+asyncpg://":
            raise ValueError("database_url must identify a PostgreSQL database")
        return SecretStr(dsn)

    @field_validator("openai_api_key", mode="after")
    @classmethod
    def _normalize_openai_api_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        secret = value.get_secret_value().strip()
        return SecretStr(secret) if secret else None

    @field_validator("openai_base_url")
    @classmethod
    def _validate_openai_base_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("openai_base_url must be an absolute http(s) URL")
        if parsed.query or parsed.fragment:
            raise ValueError("openai_base_url must not contain a query or fragment")
        return value

    @field_validator("openai_models")
    @classmethod
    def _validate_openai_models(cls, value: str) -> str:
        return _normalize_model_list(value, "openai_models")

    @field_validator("openai_default_model")
    @classmethod
    def _validate_openai_default_model(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("openai_default_model must not be blank")
        return value

    @field_validator("model_version_manifest")
    @classmethod
    def _validate_model_version_manifest(cls, value: str) -> str:
        value = value.strip()
        if not value:
            return ""
        if (
            len(value) > 500
            or "\x00" in value
            or "\r" in value
            or "\n" in value
        ):
            raise ValueError(
                "model_version_manifest must be a single path of at most "
                "500 characters"
            )
        if Path(value).suffix.lower() != ".json":
            raise ValueError("model_version_manifest must point to a .json file")
        return value

    @field_validator(
        "reliability_secondary_provider", "reliability_fallback_provider"
    )
    @classmethod
    def _validate_optional_provider_name(cls, value: str) -> str:
        value = value.strip().lower()
        if value and not _PROVIDER_NAME.fullmatch(value):
            raise ValueError(
                "reliability provider names must match ^[a-z][a-z0-9_-]{0,31}$"
            )
        return value

    @field_validator("security_api_keys", "security_admin_api_keys")
    @classmethod
    def _validate_api_key_list(
        cls, value: SecretStr | None
    ) -> SecretStr | None:
        if value is None:
            return None
        keys = [key.strip() for key in value.get_secret_value().split(",") if key.strip()]
        if not keys:
            return None
        if len(set(keys)) != len(keys):
            raise ValueError("API key lists must not contain duplicates")
        if any(
            len(key) < 16 or len(key) > 512 or any(char.isspace() for char in key)
            for key in keys
        ):
            raise ValueError(
                "each API key must be 16-512 characters without whitespace"
            )
        return SecretStr(",".join(keys))

    @field_validator("budget_provider_pricing")
    @classmethod
    def _validate_provider_pricing(
        cls, value: dict[str, PricingRates]
    ) -> dict[str, PricingRates]:
        normalized: dict[str, PricingRates] = {}
        for provider, rates in value.items():
            name = provider.strip().lower()
            if not _PROVIDER_NAME.fullmatch(name):
                raise ValueError(
                    "budget pricing provider names must match ^[a-z][a-z0-9_-]{0,31}$"
                )
            if name in normalized:
                raise ValueError(
                    "budget pricing provider names must be unique after normalization"
                )
            normalized[name] = rates
        return normalized

    @model_validator(mode="after")
    def _validate_reliability_backoff(self) -> Settings:
        if (
            self.reliability_backoff_base_seconds
            > self.reliability_backoff_max_seconds
        ):
            raise ValueError(
                "reliability_backoff_base_seconds must not exceed "
                "reliability_backoff_max_seconds"
            )
        return self

    @model_validator(mode="after")
    def _validate_budget_limits(self) -> Settings:
        if self.budget_per_request_usd > self.budget_daily_usd:
            raise ValueError(
                "budget_per_request_usd must not exceed budget_daily_usd"
            )
        if self.budget_daily_usd > self.budget_monthly_usd:
            raise ValueError(
                "budget_daily_usd must not exceed budget_monthly_usd"
            )
        return self

    @model_validator(mode="after")
    def _validate_database_configuration(self) -> Settings:
        if not self.database_enabled:
            return self
        if self.environment == "production":
            if not self.database_dsn.startswith("postgresql+asyncpg://"):
                raise ValueError(
                    "database_url must use PostgreSQL in production"
                )
            if self.database_auto_create:
                raise ValueError(
                    "database_auto_create must be disabled in production; "
                    "run Alembic migrations instead"
                )
            if self.database_echo:
                raise ValueError("database_echo must be disabled in production")
        return self

    @model_validator(mode="after")
    def _validate_security_configuration(self) -> Settings:
        if self.environment == "production" and not self.security_require_auth:
            raise ValueError(
                "security_require_auth must be enabled in production"
            )
        if self.security_require_auth and not self.security_api_key_list:
            raise ValueError(
                "security_api_keys must contain at least one key when "
                "authentication is enabled"
            )
        if set(self.security_api_key_list) & set(self.security_admin_key_list):
            raise ValueError(
                "security_api_keys and security_admin_api_keys must not overlap"
            )
        return self

    @model_validator(mode="after")
    def _validate_fake_default_model(self) -> Settings:
        if self.fake_provider_default_model not in self.fake_model_list:
            raise ValueError(
                "fake_provider_default_model must be one of fake_provider_models"
            )
        return self

    @model_validator(mode="after")
    def _validate_openai_default_model_membership(self) -> Settings:
        if self.openai_default_model not in self.openai_model_list:
            raise ValueError(
                "openai_default_model must be one of openai_models"
            )
        return self

    @property
    def fake_model_list(self) -> list[str]:
        return [model.strip() for model in self.fake_provider_models.split(",") if model.strip()]

    @property
    def openai_model_list(self) -> list[str]:
        return [model.strip() for model in self.openai_models.split(",") if model.strip()]

    @property
    def openai_enabled(self) -> bool:
        return self.openai_api_key is not None

    @property
    def security_api_key_list(self) -> list[str]:
        if self.security_api_keys is None:
            return []
        return [
            key.strip()
            for key in self.security_api_keys.get_secret_value().split(",")
            if key.strip()
        ]

    @property
    def security_admin_key_list(self) -> list[str]:
        if self.security_admin_api_keys is None:
            return []
        return [
            key.strip()
            for key in self.security_admin_api_keys.get_secret_value().split(",")
            if key.strip()
        ]

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def database_dsn(self) -> str:
        return self.database_url.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()
