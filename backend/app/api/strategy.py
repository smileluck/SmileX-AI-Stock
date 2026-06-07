from fastapi import APIRouter, HTTPException

from app.models.strategy import (
    STRATEGY_TYPES,
    StrategyCreateRequest,
    StrategyUpdateRequest,
    StrategyListResponse,
    StrategyItem,
    StrategyTestRequest,
    StrategyTypeInfo,
)
from app.services.strategy import (
    list_strategies,
    get_strategy,
    create_strategy,
    update_strategy,
    delete_strategy,
    toggle_strategy,
    duplicate_strategy,
    run_strategy_test,
)

router = APIRouter(prefix="/strategy", tags=["strategy"])


@router.get("/types")
def get_strategy_types():
    return [StrategyTypeInfo(key=k, **v) for k, v in STRATEGY_TYPES.items()]


@router.get("/list", response_model=StrategyListResponse)
def api_list_strategies(type: str | None = None, is_enabled: bool | None = None):
    items, total = list_strategies(type, is_enabled)
    return StrategyListResponse(items=[StrategyItem(**i) for i in items], total=total)


@router.get("/{strategy_id}", response_model=StrategyItem)
def api_get_strategy(strategy_id: int):
    item = get_strategy(strategy_id)
    if not item:
        raise HTTPException(404, "策略不存在")
    return StrategyItem(**item)


@router.post("", response_model=StrategyItem)
def api_create_strategy(req: StrategyCreateRequest):
    data = req.model_dump()
    item = create_strategy(data)
    return StrategyItem(**item)


@router.put("/{strategy_id}", response_model=StrategyItem)
def api_update_strategy(strategy_id: int, req: StrategyUpdateRequest):
    data = req.model_dump(exclude_none=True)
    item = update_strategy(strategy_id, data)
    if not item:
        raise HTTPException(404, "策略不存在")
    return StrategyItem(**item)


@router.delete("/{strategy_id}")
def api_delete_strategy(strategy_id: int):
    ok = delete_strategy(strategy_id)
    if not ok:
        item = get_strategy(strategy_id)
        if item and item["is_default"]:
            raise HTTPException(400, "默认策略不可删除，可禁用")
        raise HTTPException(404, "策略不存在")
    return {"success": True}


@router.put("/{strategy_id}/toggle", response_model=StrategyItem)
def api_toggle_strategy(strategy_id: int):
    item = toggle_strategy(strategy_id)
    if not item:
        raise HTTPException(404, "策略不存在")
    return StrategyItem(**item)


@router.post("/{strategy_id}/duplicate", response_model=StrategyItem)
def api_duplicate_strategy(strategy_id: int):
    item = duplicate_strategy(strategy_id)
    if not item:
        raise HTTPException(404, "策略不存在")
    return StrategyItem(**item)


@router.post("/{strategy_id}/test")
def api_test_strategy(strategy_id: int, req: StrategyTestRequest):
    try:
        result = run_strategy_test(strategy_id, req.test_input)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"result": result}
