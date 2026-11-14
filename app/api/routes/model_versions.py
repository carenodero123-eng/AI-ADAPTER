"""Administrative model version inventory endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import AdminDep, ModelCatalogDep, RegistryDep
from app.api.errors import MODEL_CATALOG_ERROR_RESPONSES, SECURITY_ERROR_RESPONSES
from app.api.schemas.model_versions import ModelVersionItem, ModelVersionList
from app.model_catalog.errors import ModelCatalogUnavailableError

router = APIRouter(prefix="/model-versions", tags=["model-versions"])


@router.get(
    "",
    response_model=ModelVersionList,
    responses={**MODEL_CATALOG_ERROR_RESPONSES, **SECURITY_ERROR_RESPONSES},
    summary="List tracked model versions",
)
async def list_model_versions(
    _admin: AdminDep,
    catalog: ModelCatalogDep,
    registry: RegistryDep,
) -> ModelVersionList:
    if catalog is None:
        raise ModelCatalogUnavailableError()

    configured = {
        (provider.name, model)
        for provider in registry.list_providers()
        for model in provider.models
    }
    return ModelVersionList(
        models=[
            ModelVersionItem(
                provider=entry.provider,
                model=entry.model,
                version=entry.version,
                status=entry.status,
                released_on=entry.released_on,
                notes=entry.notes,
                configured=(entry.provider, entry.model) in configured,
            )
            for entry in catalog.entries
        ]
    )
