"""Provider catalog, inspection, and availability endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import AdminDep, ProviderRouterDep, RegistryDep, SettingsDep
from app.api.errors import PROVIDER_ERROR_RESPONSES, SECURITY_ERROR_RESPONSES
from app.api.schemas.providers import (
    CircuitStatus,
    ProviderHealthReport,
    ProviderSummary,
)
from app.providers.schemas import ProviderInfo

router = APIRouter(prefix="/providers", tags=["providers"])


def _summary(
    provider_info: ProviderInfo,
    default_provider: str,
    provider_name: str,
) -> ProviderSummary:
    return ProviderSummary(
        **provider_info.model_dump(),
        is_default=provider_name == default_provider,
    )


@router.get(
    "",
    response_model=list[ProviderSummary],
    responses=SECURITY_ERROR_RESPONSES,
    summary="List providers",
)
async def list_providers(
    _admin: AdminDep,
    registry: RegistryDep,
    settings: SettingsDep,
) -> list[ProviderSummary]:
    return [
        _summary(provider.info(), settings.default_provider, provider.name)
        for provider in registry.list_providers()
    ]


@router.get(
    "/{provider_name}",
    response_model=ProviderSummary,
    responses={**PROVIDER_ERROR_RESPONSES, **SECURITY_ERROR_RESPONSES},
    summary="Get one provider",
)
async def get_provider(
    provider_name: str,
    _admin: AdminDep,
    registry: RegistryDep,
    settings: SettingsDep,
) -> ProviderSummary:
    provider = registry.get(provider_name)
    return _summary(provider.info(), settings.default_provider, provider.name)


@router.get(
    "/{provider_name}/health",
    response_model=ProviderHealthReport,
    responses={**PROVIDER_ERROR_RESPONSES, **SECURITY_ERROR_RESPONSES},
    summary="Check provider availability and circuit state",
)
async def provider_health(
    provider_name: str,
    _admin: AdminDep,
    registry: RegistryDep,
    provider_router: ProviderRouterDep,
) -> ProviderHealthReport:
    health = await registry.health(provider_name)
    snapshot = provider_router.circuit_snapshot(health.provider)
    return ProviderHealthReport(
        **health.model_dump(),
        circuit=CircuitStatus(
            state=snapshot.state,
            failure_count=snapshot.failure_count,
            recovery_remaining_seconds=snapshot.recovery_remaining_seconds,
        ),
    )
