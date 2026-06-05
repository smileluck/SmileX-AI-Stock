<!-- last-updated: 2026-06-05 -->
# Service 层示例

## 用途

展示 Service 层函数的设计模式：数据获取、错误处理、日志记录。

## 核心原则

- 纯函数，不使用类
- 返回 dict（由 Router 的 response_model 序列化）
- 使用 `logging.getLogger(__name__)` 记录日志
- 数据库操作使用 `try/finally` 确保连接关闭

## 示例

```python
import logging
from datetime import datetime

import akshare as ak
import pandas as pd

logger = logging.getLogger(__name__)

CN_INDEX_NAMES = {
    "sh000001": "上证指数",
    "sz399001": "深证成指",
    "sz399006": "创业板指",
}


def _parse_float(val) -> float | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def get_market_overview() -> dict:
    return {
        "cn_main": _get_cn_indices(),
        "international": _get_global_indices(),
        "fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def get_market_history(days: int = 30) -> dict:
    cutoff = pd.Timestamp.now() - pd.Timedelta(days=days)
    cutoff_str = cutoff.strftime("%Y-%m-%d")
    results = []
    for code, name in CN_INDEX_NAMES.items():
        try:
            df = ak.stock_zh_index_daily(symbol=code)
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
            df = df[df["date"] >= cutoff_str].sort_values("date")
            records = df.to_dict("records")
            if records:
                results.append({"code": code, "name": name, "records": records})
        except Exception:
            logger.warning("Failed to fetch history for %s", code, exc_info=True)
    return {
        "indices": results,
        "fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
```

## 关键点

- `_parse_float` 是内部辅助函数，处理 pandas NaN 和 None
- `fetch_time` 统一使用 `strftime("%Y-%m-%d %H:%M:%S")` 格式
- 异常不向上抛出，使用 `logger.warning` + `exc_info=True` 记录
- akshare 调用放在 try/except 中，避免单条数据失败阻断整体

## 真实参考文件

- `app/services/market.py` — 大盘行情服务
- `app/services/sector.py` — 板块服务（含数据库操作）
