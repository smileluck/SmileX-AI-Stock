import streamlit as st
from dataclasses import fields as dataclass_fields
from smilex.scanner import daily_scan
from smilex.strategies import list_strategies, get_strategy

st.set_page_config(page_title="今日推荐", layout="wide")
st.header("今日推荐股票")

strategies = list_strategies()
strategy_options = {s["display_name"]: s["name"] for s in strategies}
selected_display = st.selectbox("选择选股策略", options=list(strategy_options.keys()))
strategy_name = strategy_options[selected_display]

strategy = get_strategy(strategy_name)
st.caption(f"{strategy.metadata.description}")

with st.expander("策略参数调整"):
    user_params = {}
    params = strategy.params
    for f in dataclass_fields(params):
        val = getattr(params, f.name)
        if isinstance(val, bool):
            user_params[f.name] = st.checkbox(f.name, value=val)
        elif isinstance(val, int):
            user_params[f.name] = st.number_input(f.name, value=val)
        elif isinstance(val, float):
            user_params[f.name] = st.number_input(f.name, value=val, format="%.2f")

if st.button("运行选股扫描", type="primary"):
    with st.spinner(f"正在使用「{selected_display}」策略扫描全市场，请稍候..."):
        results = daily_scan(strategy_name=strategy_name, **user_params)
    if results.empty:
        st.warning("今日未找到符合条件的股票")
    else:
        st.success(f"共筛选出 {len(results)} 只推荐股票 (策略: {selected_display})")

        display_cols = ["code", "name", "price", "change_pct", "volume_ratio", "score", "reasons"]
        if "strategy" in results.columns:
            display_cols.append("strategy")

        st.dataframe(
            results[display_cols],
            use_container_width=True,
            column_config={
                "code": "代码",
                "name": "名称",
                "price": st.column_config.NumberColumn("价格", format="%.2f"),
                "change_pct": st.column_config.NumberColumn("涨跌幅%", format="%.2f"),
                "volume_ratio": st.column_config.NumberColumn("量比", format="%.2f"),
                "score": st.column_config.NumberColumn("得分"),
                "reasons": "推荐理由",
                "strategy": "策略",
            },
        )

        st.download_button(
            "下载推荐结果 (CSV)",
            data=results.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"stock_recommend_{strategy_name}.csv",
            mime="text/csv",
        )
else:
    st.info("选择策略后点击上方按钮运行选股扫描（每日收盘后运行效果最佳）")
