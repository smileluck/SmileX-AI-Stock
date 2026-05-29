import os
import streamlit as st
import pandas as pd

from smilex.config import HISTORY_DIR

st.set_page_config(page_title="历史推荐", layout="wide")
st.header("历史推荐追踪")

os.makedirs(HISTORY_DIR, exist_ok=True)

history_files = [f for f in os.listdir(HISTORY_DIR) if f.startswith("scan_") and f.endswith(".csv")]

if history_files:
    history_files.sort(reverse=True)
    selected = st.selectbox("选择日期", history_files)
    df = pd.read_csv(os.path.join(HISTORY_DIR, selected))
    st.dataframe(df, use_container_width=True)
else:
    st.info("暂无历史推荐记录。运行选股扫描后结果会自动保存。")
