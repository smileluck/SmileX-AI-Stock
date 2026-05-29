import streamlit as st
import plotly.graph_objects as go

from smilex.store import query_index, query_market_stats, init_db

init_db()
st.set_page_config(page_title="大盘概览", layout="wide")
st.header("大盘概览")

INDICES = {
    "上证指数": "000001",
    "深证成指": "399001",
    "创业板指": "399006",
}

col1, col2, col3 = st.columns(3)

for i, (name, code) in enumerate(INDICES.items()):
    col = [col1, col2, col3][i]
    with col:
        try:
            df = query_index(code, start_date="2025-01-01")
            if not df.empty:
                latest = df.iloc[-1]
                change = ((latest["close"] - df.iloc[-2]["close"]) / df.iloc[-2]["close"] * 100
                          if len(df) > 1 else 0)
                st.metric(label=name, value=f"{latest['close']:.2f}", delta=f"{change:.2f}%")

                fig = go.Figure()
                fig.add_trace(go.Scatter(x=df["date"], y=df["close"], name=name))
                fig.update_layout(height=300, margin=dict(l=0, r=0, t=20, b=0))
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning(f"{name}暂无数据（请先在系统设置中开启大盘同步）")
        except Exception as e:
            st.error(f"加载{name}数据失败: {e}")

st.subheader("A股市场概况")

try:
    stats = query_market_stats()
    if not stats.empty:
        row = stats.iloc[0]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("上涨", f"{int(row['up_count'])} 只")
        c2.metric("下跌", f"{int(row['down_count'])} 只")
        c3.metric("平盘", f"{int(row['flat_count'])} 只")
        c4.metric("总股票数", f"{int(row['total'])} 只")

        c1.metric("涨停", f"{int(row['limit_up'])} 只")
        c2.metric("跌停", f"{int(row['limit_down'])} 只")
        st.caption(f"数据更新时间：{row['snapshot_time']}")
    else:
        st.info("暂无市场统计数据（请先在系统设置中开启大盘同步）")
except Exception as e:
    st.error(f"加载市场数据失败: {e}")
