import streamlit as st

st.set_page_config(page_title="SmileX A股量化选股", layout="wide")

st.title("SmileX A股量化选股系统")
st.sidebar.success("请从上方选择功能页面")

st.markdown("""
### 欢迎使用 SmileX A股量化选股系统

功能模块：
- **大盘概览** — 三大指数走势、市场情绪
- **今日推荐** — 每日选股扫描结果
- **个股分析** — K线图 + 技术指标叠加
- **策略回测** — 双均线策略回测
- **历史推荐** — 过往推荐追踪
- **资讯查询** — 同花顺/东方财富/雪球三站聚合

---
*请在顶部导航栏选择页面，或通过侧边栏切换*
""")
