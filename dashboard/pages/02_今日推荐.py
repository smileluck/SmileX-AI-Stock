import streamlit as st
from smilex.scanner import daily_scan

st.set_page_config(page_title="今日推荐", layout="wide")
st.header("今日推荐股票")

if st.button("运行选股扫描", type="primary"):
    with st.spinner("正在扫描全市场，请稍候..."):
        results = daily_scan()
    if results.empty:
        st.warning("今日未找到符合条件的股票")
    else:
        st.success(f"共筛选出 {len(results)} 只推荐股票")

        st.dataframe(
            results[["code", "name", "price", "change_pct", "volume_ratio", "score", "reasons"]],
            use_container_width=True,
            column_config={
                "code": "代码",
                "name": "名称",
                "price": st.column_config.NumberColumn("价格", format="%.2f"),
                "change_pct": st.column_config.NumberColumn("涨跌幅%", format="%.2f"),
                "volume_ratio": st.column_config.NumberColumn("量比", format="%.2f"),
                "score": st.column_config.NumberColumn("得分"),
                "reasons": "推荐理由",
            },
        )

        st.download_button(
            "下载推荐结果 (CSV)",
            data=results.to_csv(index=False).encode("utf-8-sig"),
            file_name="stock_recommend_today.csv",
            mime="text/csv",
        )
else:
    st.info("点击上方按钮运行选股扫描（每日收盘后运行效果最佳）")
