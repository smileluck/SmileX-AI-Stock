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
            else:
                st.warning(f"{name}暂无数据")
        except Exception as e:
            st.error(f"加载{name}数据失败: {e}")

st.subheader("A股市场概况")

try:
    quote = realtime_quote()
    if not quote.empty:
        col_name = "涨跌幅"
        if col_name not in quote.columns:
            # 尝试找到涨跌幅列
            candidates = [c for c in quote.columns if "涨跌" in c]
            if candidates:
                col_name = candidates[0]

        total = len(quote)
        up_count = len(quote[quote[col_name] > 0])
        down_count = len(quote[quote[col_name] < 0])
        flat_count = total - up_count - down_count

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("上涨", f"{up_count} 只")
        c2.metric("下跌", f"{down_count} 只")
        c3.metric("平盘", f"{flat_count} 只")
        c4.metric("总股票数", f"{total} 只")

        limit_up = len(quote[quote[col_name] >= 9.9])
        limit_down = len(quote[quote[col_name] <= -9.9])
        c1.metric("涨停", f"{limit_up} 只")
        c2.metric("跌停", f"{limit_down} 只")
except Exception as e:
    st.error(f"获取实时行情失败: {e}")
