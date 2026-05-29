import streamlit as st

from smilex.consult import ths, em, xq

st.set_page_config(page_title="资讯查询", layout="wide")
st.header("资讯查询")

tab_ths, tab_em, tab_xq = st.tabs(["同花顺", "东方财富", "雪球"])

# ─── 同花顺 ───
with tab_ths:
    st.subheader("同花顺 — 板块与评级")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("获取概念板块", key="ths_concept"):
            with st.spinner("加载中..."):
                df = ths.concept_boards()
            if not df.empty:
                st.dataframe(df.head(30), use_container_width=True)
            else:
                st.warning("获取失败")

    with col2:
        if st.button("获取行业板块", key="ths_industry"):
            with st.spinner("加载中..."):
                df = ths.industry_boards()
            if not df.empty:
                st.dataframe(df.head(30), use_container_width=True)
            else:
                st.warning("获取失败")

    st.divider()
    code_ths = st.text_input("查询个股评级（股票代码）", value="000001", key="ths_code")
    if st.button("查询同花顺评级", key="ths_rating"):
        with st.spinner("加载中..."):
            df = ths.stock_rating(code_ths)
        if not df.empty:
            st.dataframe(df, use_container_width=True)
        else:
            st.warning("未找到该股票评级数据")

# ─── 东方财富 ───
with tab_em:
    st.subheader("东方财富 — 资金与龙虎榜")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("北向资金流向", key="em_north"):
            with st.spinner("加载中..."):
                df = em.north_flow()
            if not df.empty:
                st.dataframe(df.head(20), use_container_width=True)
            else:
                st.warning("获取失败")

    with col2:
        if st.button("龙虎榜（最近交易日）", key="em_lhb"):
            with st.spinner("加载中..."):
                df = em.dragon_tiger()
            if not df.empty:
                st.dataframe(df.head(30), use_container_width=True)
            else:
                st.warning("获取失败")

    st.divider()
    code_em = st.text_input("查询个股资金流向（股票代码）", value="000001", key="em_code")
    if st.button("查询资金流向", key="em_flow"):
        with st.spinner("加载中..."):
            df = em.capital_flow(code_em)
        if not df.empty:
            st.dataframe(df.head(30), use_container_width=True)
        else:
            st.warning("未找到该股票资金数据")

# ─── 雪球 ───
with tab_xq:
    st.subheader("雪球 — 热度排行")

    rank_type = st.selectbox("排行类型", ["deal", "follow", "tweet"],
                              format_func=lambda x: {"deal": "交易排行", "follow": "关注排行", "tweet": "讨论排行"}[x])

    if st.button("获取雪球热度排行", key="xq_hot"):
        with st.spinner("加载中..."):
            df = xq.hot_stocks(rank_type)
        if not df.empty:
            st.dataframe(df.head(30), use_container_width=True)
        else:
            st.warning("获取失败（雪球反爬较严，部分接口可能不稳定）")

    st.divider()
    st.caption("数据来源：同花顺 10jqka.com.cn / 东方财富 eastmoney.com / 雪球 xueqiu.com")
