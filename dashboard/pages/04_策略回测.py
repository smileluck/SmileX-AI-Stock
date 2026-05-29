import streamlit as st
import plotly.graph_objects as go

from smilex.fetcher import daily_history
from smilex.backtest import run as run_backtest

st.set_page_config(page_title="策略回测", layout="wide")
st.header("策略回测")

col1, col2, col3 = st.columns(3)
with col1:
    code = st.text_input("股票代码", value="510300")
with col2:
    start_date = st.text_input("开始日期", value="20230101")
with col3:
    cash = st.number_input("初始资金", value=100000, step=10000)

col1, col2 = st.columns(2)
with col1:
    short_period = st.number_input("短周期均线", value=5, min_value=2, max_value=30)
with col2:
    long_period = st.number_input("长周期均线", value=20, min_value=10, max_value=120)

if st.button("运行回测", type="primary"):
    with st.spinner("正在回测..."):
        try:
            df = daily_history(code, start_date=start_date)
            if df.empty:
                st.warning("未找到该股票数据")
            else:
                result = run_backtest(df, short_period=short_period,
                                      long_period=long_period, cash=cash)

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("总收益率", f"{result['total_return']}%")
                c2.metric("年化收益率", f"{result['annual_return']}%")
                c3.metric("最大回撤", f"{result['max_drawdown']}%")
                c4.metric("胜率", f"{result['win_rate']}%")

                c1, c2, c3 = st.columns(3)
                c1.metric("初始资金", f"{result['start_value']:,.0f}")
                c2.metric("最终资金", f"{result['end_value']:,.0f}")
                c3.metric("交易次数", f"{result['trade_count']}")

                if result["equity_curve"]:
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(y=result["equity_curve"], name="资金曲线"))
                    fig.update_layout(title="资金曲线", height=400)
                    st.plotly_chart(fig, use_container_width=True)

                if result["trades"]:
                    import pandas as pd
                    st.subheader("交易明细")
                    st.dataframe(pd.DataFrame(result["trades"]), use_container_width=True)

        except Exception as e:
            st.error(f"回测失败: {e}")
