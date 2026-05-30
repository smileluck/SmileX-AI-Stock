import streamlit as st

from smilex.consult import ths, em, xq
from smilex.news_sync import get_latest_news

st.set_page_config(page_title="资讯查询", layout="wide")
st.header("资讯查询")

# ─── 新闻快讯 ───
st.subheader("新闻快讯")

SOURCE_LABELS = {
    "eastmoney_flash": "东方财富",
    "cls_telegraph": "财联社",
    "cctv_news": "新闻联播",
}

tab_all, tab_em, tab_cls, tab_cctv = st.tabs(
    ["全部新闻", "东方财富快讯", "财联社快讯", "新闻联播"]
)

LIMIT = 100


@st.cache_data(ttl=120, show_spinner=False)
def _load_news(source: str, limit: int):
    return get_latest_news(source=source, limit=limit)


def _render_news_cards(news_list: list[dict]):
    if not news_list:
        st.info("暂无新闻数据，请在系统设置中启动新闻同步或点击下方手动刷新")
        return
    for item in news_list:
        title = item.get("title", "")
        content = item.get("content", "")
        url = item.get("url", "")
        pub_time = item.get("publish_time", "")
        source = item.get("source", "")
        source_label = SOURCE_LABELS.get(source, source)
        summary = content[:200] + "..." if len(content) > 200 else content

        with st.container():
            if url and url.startswith("http"):
                st.markdown(f"**[{title}]({url})**")
            else:
                st.markdown(f"**{title}**")
            st.caption(f"`{source_label}`  |  {pub_time}")
            if summary:
                st.markdown(f">{summary}")
            st.divider()


with tab_all:
    if st.button("刷新", key="refresh_all"):
        _load_news.clear()
        st.rerun()
    news = _load_news(source="", limit=LIMIT)
    _render_news_cards(news)

with tab_em:
    if st.button("刷新", key="refresh_em"):
        _load_news.clear()
        st.rerun()
    news = _load_news(source="eastmoney_flash", limit=LIMIT)
    _render_news_cards(news)

with tab_cls:
    if st.button("刷新", key="refresh_cls"):
        _load_news.clear()
        st.rerun()
    news = _load_news(source="cls_telegraph", limit=LIMIT)
    _render_news_cards(news)

with tab_cctv:
    if st.button("刷新", key="refresh_cctv"):
        _load_news.clear()
        st.rerun()
    news = _load_news(source="cctv_news", limit=LIMIT)
    _render_news_cards(news)

# ─── 原有资讯查询 ───
st.divider()
st.subheader("板块与资金数据")

tab_ths, tab_em_data, tab_xq = st.tabs(["同花顺", "东方财富", "雪球"])

# ─── 同花顺 ───
with tab_ths:
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
with tab_em_data:
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
    rank_type = st.selectbox("排行类型", ["deal", "follow", "tweet"],
                              format_func=lambda x: {"deal": "交易排行", "follow": "关注排行", "tweet": "讨论排行"}[x])

    if st.button("获取雪球热度排行", key="xq_hot"):
        with st.spinner("加载中..."):
            df = xq.hot_stocks(rank_type)
        if not df.empty:
            st.dataframe(df.head(30), use_container_width=True)
        else:
            st.warning("获取失败（雪球反爬较严，部分接口可能不稳定）")

st.caption("数据来源：东方财富 eastmoney.com / 财联社 cls.cn / 央视 cctv.com / 同花顺 10jqka.com.cn / 雪球 xueqiu.com")
