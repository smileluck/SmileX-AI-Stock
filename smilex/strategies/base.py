from abc import ABC, abstractmethod
from dataclasses import dataclass, fields
from typing import Any

import pandas as pd


@dataclass
class StrategyMetadata:
    name: str
    display_name: str
    description: str
    category: str
    version: str = "1.0"


@dataclass
class StrategyParams:
    pass


class BaseStrategy(ABC):

    def __init__(self, params: StrategyParams | None = None):
        self._params = params or self._default_params()

    @property
    @abstractmethod
    def metadata(self) -> StrategyMetadata: ...

    @property
    def _params_cls(self) -> type[StrategyParams]:
        return StrategyParams

    def _default_params(self) -> StrategyParams:
        return self._params_cls()

    @property
    def params(self) -> StrategyParams:
        return self._params

    def update_params(self, **kwargs) -> None:
        for k, v in kwargs.items():
            if hasattr(self._params, k):
                setattr(self._params, k, v)

    @property
    def required_indicators(self) -> list[str]:
        return ["ma", "macd", "rsi", "bollinger", "kdj", "volume_ratio"]

    @abstractmethod
    def evaluate(self, stock_data: pd.Series) -> tuple[int, list[str]]:
        ...

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        ...

    @property
    @abstractmethod
    def backtest_class(self) -> type: ...

    def to_config(self) -> dict:
        return {
            "name": self.metadata.name,
            "display_name": self.metadata.display_name,
            "description": self.metadata.description,
            "category": self.metadata.category,
            "params": {f.name: getattr(self._params, f.name) for f in fields(self._params)},
        }
