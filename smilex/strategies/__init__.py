import json
import os
from dataclasses import fields

from smilex.strategies.base import BaseStrategy, StrategyMetadata, StrategyParams
from smilex.strategies.trend_following import TrendFollowingStrategy
from smilex.strategies.mean_reversion import MeanReversionStrategy
from smilex.strategies.momentum import MomentumStrategy
from smilex.strategies.breakout import BreakoutStrategy
from smilex.strategies.value_technical import ValueTechnicalStrategy
from smilex.strategies.multi_factor import MultiFactorStrategy
from smilex.strategies.etf_rotation import ETFRotationStrategy
from smilex.strategies.sector_rotation import SectorRotationStrategy

_REGISTRY: dict[str, type[BaseStrategy]] = {}

_CONFIG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "strategies_config",
)


def _register(cls: type[BaseStrategy]) -> None:
    instance = cls()
    _REGISTRY[instance.metadata.name] = cls


_register(TrendFollowingStrategy)
_register(MeanReversionStrategy)
_register(MomentumStrategy)
_register(BreakoutStrategy)
_register(ValueTechnicalStrategy)
_register(MultiFactorStrategy)
_register(ETFRotationStrategy)
_register(SectorRotationStrategy)


def get_strategy(name: str, **params) -> BaseStrategy:
    cls = _REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"Unknown strategy: {name}. Available: {list(_REGISTRY.keys())}")

    # Try loading saved config first
    config = _load_config_file(name)
    if config:
        instance = cls()
        saved_params = config.get("params", {})
        for f in fields(instance.params):
            if f.name in saved_params:
                setattr(instance.params, f.name, saved_params[f.name])
        if params:
            instance.update_params(**params)
        return instance

    instance = cls()
    if params:
        instance.update_params(**params)
    return instance


def list_strategies() -> list[dict]:
    result = []
    for name, cls in _REGISTRY.items():
        meta = cls().metadata
        result.append({
            "name": meta.name,
            "display_name": meta.display_name,
            "description": meta.description,
            "category": meta.category,
        })
    return result


def all_strategy_names() -> list[str]:
    return list(_REGISTRY.keys())


def save_strategy_config(name: str, config: dict) -> None:
    os.makedirs(_CONFIG_DIR, exist_ok=True)
    path = os.path.join(_CONFIG_DIR, f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def reset_strategy_config(name: str) -> bool:
    path = os.path.join(_CONFIG_DIR, f"{name}.json")
    if os.path.exists(path):
        os.remove(path)
        return True
    return False


def _load_config_file(name: str) -> dict | None:
    path = os.path.join(_CONFIG_DIR, f"{name}.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None
