import streamlit as st
import plotly.graph_objects as go

from smilex.fetcher import index_daily, realtime_quote

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
            df = index_daily(code, start_date="20250101")
            if not df.empty:
                latest = df.iloc[-1]
                change = ((latest["close"] - df.iloc[-2]["close"]) / df.iloc[-2]["close"] * 100
                          if len(df) > 1 else 0)
                st.metric(label=name, value=f"{latest['close']:.2f}", delta=f"{change:.2f}%")

                fig = go.Figure()
                fig.add_trace(go.Scatter(x=df["date"], y=df["close"], name=name))
                fig.update_layout(height=300, margin=dict(l=0, r=0, t=20, b=0))
                st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.error(f"加载{name}数据失败: {e}")

st.subheader("A股市场概况")
quote = realtime_quote()
if not quote.empty:
    total = len(quote)
    up_count = len(quote[quote["涨跌幅"] > 0])
    down_count = len(quote[quote["涨跌幅"] < 0])
    flat_count = total - up_count - down_count

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("上涨", f"{up_count} 只")
    c2.metric("下跌", f"{down_count} 只")
    c3.metric("平盘", f"{flat_count} 只")
    c4.metric("总股票数", f"{total} 只")

    limit_up = len(quote[quote["涨跌幅"] >= 9.9])
    limit_down = len(quote[quote["涨跌幅"] <= -9.9])
    c1.metric("涨停", f"{limit_up} 只")
    c2.metric("跌停", f"{limit_down} 只")
