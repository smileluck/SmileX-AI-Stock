import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from smilex.fetcher import daily_history
from smilex.indicators import all_indicators

st.set_page_config(page_title="个股分析", layout="wide")
st.header("个股分析")

code = st.text_input("输入股票代码", value="000001", max_chars=6)

if code:
    try:
        df = daily_history(code, start_date="20240101")
        if df.empty:
            st.warning("未找到该股票数据")
        else:
            df = all_indicators(df)

            fig = make_subplots(
                rows=3, cols=1, shared_xaxes=True,
                row_heights=[0.6, 0.2, 0.2],
                subplot_titles=["K线 + 均线", "成交量", "MACD"],
            )

            fig.add_trace(go.Candlestick(
                x=df["date"], open=df["open"], high=df["high"],
                low=df["low"], close=df["close"], name="K线",
                increasing_line_color="red", decreasing_line_color="green",
            ), row=1, col=1)

            for col_name, color in [("ma5", "yellow"), ("ma10", "blue"), ("ma20", "purple"), ("ma60", "gray")]:
                if col_name in df.columns:
                    fig.add_trace(go.Scatter(
                        x=df["date"], y=df[col_name], name=col_name.upper(),
                        line=dict(color=color, width=1),
                    ), row=1, col=1)

            fig.add_trace(go.Bar(
                x=df["date"], y=df["volume"], name="成交量",
                marker_color="rgba(100,100,200,0.5)",
            ), row=2, col=1)

            if "macd_dif" in df.columns:
                fig.add_trace(go.Scatter(
                    x=df["date"], y=df["macd_dif"], name="DIF",
                    line=dict(color="blue", width=1),
                ), row=3, col=1)
                fig.add_trace(go.Scatter(
                    x=df["date"], y=df["macd_dea"], name="DEA",
                    line=dict(color="orange", width=1),
                ), row=3, col=1)
            if "macd_hist" in df.columns:
                colors = ["red" if v >= 0 else "green" for v in df["macd_hist"].fillna(0)]
                fig.add_trace(go.Bar(
                    x=df["date"], y=df["macd_hist"], name="MACD柱",
                    marker_color=colors,
                ), row=3, col=1)

            fig.update_layout(height=800, xaxis_rangeslider_visible=False)
            for r in [1, 2, 3]:
                fig.update_xaxes(type="category", row=r, col=1)

            st.plotly_chart(fig, use_container_width=True)

            latest = df.iloc[-1]
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("最新价", f"{latest['close']:.2f}")
            c2.metric("涨跌幅", f"{latest.get('change_pct', 0):.2f}%")
            c3.metric("成交量", f"{latest.get('volume', 0):.0f}")
            if "rsi14" in latest.index:
                c4.metric("RSI(14)", f"{latest['rsi14']:.1f}")

    except Exception as e:
        st.error(f"加载失败: {e}")
