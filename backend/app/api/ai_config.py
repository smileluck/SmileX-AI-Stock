from fastapi import APIRouter, HTTPException

from app.models.ai_config import (
    AIModelConfigCreate,
    AIModelConfigListResponse,
    AIModelConfigResponse,
    AIModelConfigUpdate,
    ConnectionTestResponse,
    ProviderInfo,
    PROVIDERS,
)
from app.services.ai_config import (
    EncryptionKeyNotSetError,
    create_config,
    delete_config,
    get_config,
    list_configs,
    update_config,
)
from app.services.llm import test_connection

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/config/providers", response_model=list[ProviderInfo])
def list_providers():
    return [ProviderInfo(id=k, label=v["label"], base_url=v["base_url"]) for k, v in PROVIDERS.items()]


@router.get("/config/models", response_model=AIModelConfigListResponse)
def list_models():
    try:
        items = list_configs()
    except EncryptionKeyNotSetError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return AIModelConfigListResponse(items=items, total=len(items))


@router.post("/config/models", response_model=AIModelConfigResponse)
def create_model(data: AIModelConfigCreate):
    try:
        return create_config(data)
    except EncryptionKeyNotSetError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.put("/config/models/{config_id}", response_model=AIModelConfigResponse)
def update_model(config_id: int, data: AIModelConfigUpdate):
    try:
        result = update_config(config_id, data)
    except EncryptionKeyNotSetError as e:
        raise HTTPException(status_code=503, detail=str(e))
    if not result:
        raise HTTPException(status_code=404, detail="配置不存在")
    return result


@router.delete("/config/models/{config_id}")
def delete_model(config_id: int):
    if not delete_config(config_id):
        raise HTTPException(status_code=404, detail="配置不存在")
    return {"ok": True}


@router.post("/config/test", response_model=ConnectionTestResponse)
def test_model_connection(config_id: int | None = None, data: AIModelConfigCreate | None = None):
    if data:
        return test_connection(config_data=data.model_dump())
    if not config_id:
        raise HTTPException(status_code=400, detail="请提供 config_id 或 data")
    try:
        return test_connection(config_id=config_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
