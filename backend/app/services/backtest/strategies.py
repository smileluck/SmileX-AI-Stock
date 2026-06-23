"""策略工厂：生成每日交易信号。

不复用 stock.py 中的 _preselect_*（它们调实时 API），
而是从 stock_daily 表查询并复刻相同的筛选逻辑，再委托 stock.py 的
_apply_hard_filters / _score_recommendation_candidate 完成估值过滤和打分。
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from app.database import get_connection
from app.services.backtest import data_loader
from app.services.stock import (
    _apply_hard_filters,
    _score_recommendation_candidate,
    _parse_float,
)

logger = logging.getLogger(__name__)


# 各策略的候选股初筛条件
_STRATEGY_FILTERS = {
    "morning": {"change_pct_min": 9.5, "change_pct_max": 20.0, "rank_by": "amount"},
    "midday": {"change_pct_min": 2.0, "change_pct_max": 7.0, "rank_by": "main_net_inflow"},
    "afternoon": {"change_pct_min": 0.0, "change_pct_max": 9.5, "rank_by": "main_net_inflow"},
}


def list_strategies() -> list[dict]:
    """返回策略枚举 + 默认参数，供前端表单使用。"""
    return [
        {
            "type": "morning",
            "label": "早盘（昨日涨停延续）",
            "description": "前一日涨幅 ≥9.5% 且成交额 TOP80，再经硬过滤+多因子打分。",
            "experimental": True,
            "default_params": {"topN": 5, "stop_loss": -0.07, "take_profit": 0.15},
        },
        {
            "type": "midday",
            "label": "午盘（上午强势+主力流入）",
            "description": "前一日涨幅 2-7% 且主力净流入为正，按主力净流入 TOP80。",
            "experimental": False,
            "default_params": {"topN": 5, "stop_loss": -0.07, "take_profit": 0.15},
        },
        {
            "type": "afternoon",
            "label": "尾盘（主力净流入）",
            "description": "前一日主力净流入 TOP30，过滤涨停/ST。",
            "experimental": False,
            "default_params": {"topN": 5, "stop_loss": -0.07, "take_profit": 0.15},
        },
        {
            "type": "custom_factor",
            "label": "自定义因子",
            "description": "用户配置主力流入/涨幅/换手率/PE 等因子权重，多因子加权打分。",
            "experimental": False,
            "default_params": {
                "topN": 5,
                "stop_loss": -0.07,
                "take_profit": 0.15,
                "factors": {
                    "main_net_inflow_pct": 0.3,
                    "change_pct": 0.2,
                    "turnover_rate": 0.2,
                    "neg_pe": 0.3,
                },
            },
        },
    ]


def generate_signals(
    strategy_type: str,
    decision_day: str,
    board: str = "main",
    top_n: int = 80,
    custom_factors: dict[str, float] | None = None,
) -> list[dict]:
    """生成 decision_day 的买入信号候选列表。

    Args:
        strategy_type: morning/midday/afternoon/custom_factor
        decision_day: 信号决策日（T-1），即"前一日"
        board: 股票池范围（同 data_loader.load_daily_panel）
        top_n: 初筛 TOP N
        custom_factors: 仅 custom_factor 用，{factor_name: weight}

    Returns:
        list[dict]，每个 dict 至少含 code/name/change_pct/main_net_inflow/turnover_rate/pe_ttm/score。
    """
    panel = data_loader.load_daily_panel(decision_day, board=board)
    if panel.empty:
        return []

    # 仅保留主板（_apply_hard_filters 也会过滤，但初筛先收紧）
    if board == "main":
        panel = panel[panel["code"].astype(str).str.startswith(("60", "00"))]

    # ---- Step 1: 基础过滤（ST/停牌/无成交）----
    panel = panel[panel["name"].astype(str).str.upper().str.contains("ST") == False]
    panel = panel[panel["amount"].notna() & (panel["amount"] > 0)]
    panel = panel[panel["main_net_inflow"].notna()]

    # ---- Step 2: 各策略特有过滤 ----
    if strategy_type in _STRATEGY_FILTERS:
        f = _STRATEGY_FILTERS[strategy_type]
        chg = panel["change_pct"]
        panel = panel[(chg >= f["change_pct_min"]) & (chg <= f["change_pct_max"])]
        if strategy_type in ("midday", "afternoon"):
            panel = panel[panel["main_net_inflow"] > 0]
        panel = panel.sort_values(f["rank_by"], ascending=False).head(top_n)
    elif strategy_type == "custom_factor":
        panel = _apply_custom_factor_filter(panel, custom_factors or {})
        panel = panel.sort_values("custom_score", ascending=False).head(top_n)
    else:
        return []

    if panel.empty:
        return []

    # ---- Step 3: 复用 _apply_hard_filters 做 PE/累计涨幅/连板过滤 ----
    candidates_input = [
        {
            "code": str(r["code"]),
            "name": str(r["name"]),
            "change_pct": _parse_float(r["change_pct"]),
            "main_net_inflow": _parse_float(r["main_net_inflow"]),
            "main_inflow_pct": _parse_float(r.get("main_net_inflow_pct")),
            "turnover_rate": _parse_float(r["turnover_rate"]),
            "amount": _parse_float(r["amount"]),
        }
        for _, r in panel.iterrows()
    ]
    passed, _rejected = _apply_hard_filters(
        candidates_input, trade_date=decision_day, phase=strategy_type, zt_codes=None,
    )
    if not passed:
        return []

    # ---- Step 4: 复用 _score_recommendation_candidate 打分 ----
    scored = []
    for item in passed:
        try:
            scored_item = _score_recommendation_candidate(item, phase=strategy_type)
            if strategy_type == "custom_factor":
                # 自定义因子模式下，用 custom_score 覆盖 quant_score
                code = scored_item.get("code")
                matched = panel[panel["code"].astype(str) == str(code)]
                if not matched.empty:
                    scored_item["quant_score"] = float(matched.iloc[0]["custom_score"])
            scored.append(scored_item)
        except Exception:
            logger.debug("score failed for %s", item.get("code"), exc_info=True)
            continue

    if not scored:
        return []

    scored.sort(key=lambda x: x.get("quant_score", 0), reverse=True)
    return scored


def _apply_custom_factor_filter(panel: pd.DataFrame, factors: dict[str, float]) -> pd.DataFrame:
    """对 panel 应用自定义因子加权打分，返回带 custom_score 列的 DataFrame。

    支持因子：
      main_net_inflow_pct: 主力净流入百分比
      change_pct: 涨幅
      turnover_rate: 换手率（适中得分高）
      neg_pe: PE 越低得分越高（亏损按 0 分）
    """
    df = panel.copy()
    for col in ("main_net_inflow_pct", "change_pct", "turnover_rate", "pe_ttm"):
        if col not in df.columns:
            df[col] = 0.0

    # 各因子归一化到 [0,1]
    def _norm(s: pd.Series, reverse: bool = False) -> pd.Series:
        s = pd.to_numeric(s, errors="coerce").fillna(0)
        if s.max() == s.min():
            return pd.Series([0.5] * len(s), index=s.index)
        n = (s - s.min()) / (s.max() - s.min())
        return 1 - n if reverse else n

    df["_s_inflow_pct"] = _norm(df["main_net_inflow_pct"])
    df["_s_change"] = _norm(df["change_pct"])
    # 换手率：3-15% 之间最优
    df["_s_turnover"] = 1 - (df["turnover_rate"].fillna(0) - 9).abs() / 15
    df["_s_turnover"] = df["_s_turnover"].clip(0, 1)
    # PE：越低越好（亏损按 0）
    df["_s_pe"] = _norm(df["pe_ttm"], reverse=True)

    w = factors or {}
    df["custom_score"] = (
        w.get("main_net_inflow_pct", 0) * df["_s_inflow_pct"]
        + w.get("change_pct", 0) * df["_s_change"]
        + w.get("turnover_rate", 0) * df["_s_turnover"]
        + w.get("neg_pe", 0) * df["_s_pe"]
    )
    return df
