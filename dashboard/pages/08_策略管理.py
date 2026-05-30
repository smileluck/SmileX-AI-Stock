import streamlit as st
import json
from dataclasses import fields as dataclass_fields

from smilex.strategies import (
    list_strategies, get_strategy,
    save_strategy_config, reset_strategy_config,
)

st.set_page_config(page_title="策略管理", layout="wide")
st.header("策略管理")

strategies = list_strategies()
strategy_options = {s["display_name"]: s["name"] for s in strategies}
selected_display = st.selectbox("选择策略", options=list(strategy_options.keys()))
strategy_name = strategy_options[selected_display]

strategy = get_strategy(strategy_name)

# Show strategy info
c1, c2 = st.columns([1, 2])
with c1:
    st.subheader("策略信息")
    st.markdown(f"**名称**: {strategy.metadata.display_name}")
    st.markdown(f"**分类**: {strategy.metadata.category}")
    st.markdown(f"**描述**: {strategy.metadata.description}")
    st.markdown(f"**版本**: {strategy.metadata.version}")
    st.markdown(f"**所需指标**: {', '.join(strategy.required_indicators)}")

with c2:
    with st.expander("查看配置文件 (JSON)"):
        st.json(strategy.to_config())

# Parameter editing
st.divider()
st.subheader("参数编辑")

params = strategy.params
edited_params = {}
param_cols = st.columns(min(len(dataclass_fields(params)), 4))
for idx, f in enumerate(dataclass_fields(params)):
    val = getattr(params, f.name)
    with param_cols[idx % len(param_cols)]:
        if isinstance(val, bool):
            edited_params[f.name] = st.checkbox(f.name, value=val, key=f"mg_{f.name}")
        elif isinstance(val, int):
            edited_params[f.name] = st.number_input(f.name, value=val, key=f"mg_{f.name}")
        elif isinstance(val, float):
            edited_params[f.name] = st.number_input(f.name, value=val, format="%.4f", key=f"mg_{f.name}")

col1, col2 = st.columns(2)
with col1:
    if st.button("保存配置", type="primary"):
        config = strategy.to_config()
        config["params"] = edited_params
        save_strategy_config(strategy_name, config)
        st.success(f"「{selected_display}」策略配置已保存")

with col2:
    if st.button("恢复默认"):
        if reset_strategy_config(strategy_name):
            st.success(f"「{selected_display}」策略配置已恢复默认")
        else:
            st.info("当前使用的是默认配置，无需恢复")

# Strategy overview table
st.divider()
st.subheader("所有策略概览")
overview_data = []
for s in strategies:
    strat = get_strategy(s["name"])
    overview_data.append({
        "名称": s["display_name"],
        "分类": s["category"],
        "描述": s["description"],
        "参数数量": len(dataclass_fields(strat.params)),
    })
st.dataframe(overview_data, use_container_width=True, hide_index=True)
