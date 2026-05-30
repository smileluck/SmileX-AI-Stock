import streamlit as st
import plotly.graph_objects as go

from smilex.store import query_index, query_market_stats, query_ai_analysis, init_db
from smilex.config import AI_INDICES

init_db()
st.set_page_config(page_title="大盘概览", layout="wide")
st.header("大盘概览")

INDICES = AI_INDICES

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

# ── AI 市场评估 ──
st.divider()
st.subheader("AI 市场评估（近3个月）")

latest_eval = query_ai_analysis(analysis_type="evaluation", limit=1)
if not latest_eval.empty:
    row = latest_eval.iloc[0]
    st.markdown(row["content"])
    st.caption(f"评估时间：{row['created_at']}  |  模型：{row['model']}")
else:
    st.info("暂无AI市场评估，点击下方按钮生成")

if st.button("生成3个月市场评估", key="gen_eval"):
    with st.spinner("AI正在分析市场数据，请稍候..."):
        try:
            from smilex.ai import evaluate_market
            from smilex.store import save_ai_analysis
            from smilex.config import AI_API_KEY

            if not AI_API_KEY:
                st.error("请先配置 AI API Key（设置环境变量 SMILEX_AI_API_KEY）")
            else:
                result = evaluate_market()
                save_ai_analysis(
                    analysis_type="evaluation",
                    content=result["evaluation"],
                    model=result.get("model", ""),
                )
                st.markdown(result["evaluation"])
                st.caption(f"评估时间：{result['created_at']}  |  模型：{result['model']}")
                st.rerun()
        except Exception as e:
            st.error(f"AI分析失败：{e}")

# ── AI 每日收盘分析 ──
st.divider()
st.subheader("AI 每日收盘分析")

latest_daily = query_ai_analysis(analysis_type="daily_summary", limit=1)
if not latest_daily.empty:
    row = latest_daily.iloc[0]
    col_sum, col_pred = st.columns(2)
    with col_sum:
        st.markdown("#### 今日总结")
        st.markdown(row["summary"])
    with col_pred:
        st.markdown("#### 明日预测")
        st.markdown(row["prediction"])
    st.caption(f"分析时间：{row['created_at']}  |  模型：{row['model']}")
else:
    st.info("暂无AI每日分析（每日收盘后自动生成，也可在系统设置中手动触发）")
