import os
import json
import streamlit as st
import pandas as pd

from smilex.scheduler import (
    load_config, start_scheduler, stop_scheduler,
    get_next_run_time, get_scan_history, run_daily_job,
)
from smilex.config import HISTORY_DIR

st.set_page_config(page_title="系统设置", layout="wide")
st.header("系统设置")

# ── 定时任务 ──
st.subheader("定时任务")

cfg = load_config()

col1, col2 = st.columns(2)
with col1:
    scan_hour = st.number_input("扫描时间（时）", min_value=0, max_value=23,
                                 value=cfg.get("hour", 15))
with col2:
    scan_minute = st.number_input("扫描时间（分）", min_value=0, max_value=59,
                                   value=cfg.get("minute", 30))

is_running = st.session_state.get("_scheduler") is not None and st.session_state["_scheduler"].running

col_start, col_stop, col_manual = st.columns(3)

with col_start:
    if st.button("启动定时任务", type="primary", disabled=is_running):
        try:
            start_scheduler(st.session_state, scan_hour, scan_minute)
            st.success(f"定时任务已启动，每日 {scan_hour:02d}:{scan_minute:02d} 执行选股扫描")
            st.rerun()
        except Exception as e:
            st.error(f"启动失败：{e}")

with col_stop:
    if st.button("停止定时任务", disabled=not is_running):
        stop_scheduler(st.session_state)
        st.success("定时任务已停止")
        st.rerun()

with col_manual:
    if st.button("立即执行一次"):
        with st.spinner("正在执行选股扫描，请稍候..."):
            try:
                run_daily_job()
                st.success("执行完成，结果已保存")
            except Exception as e:
                st.error(f"执行失败：{e}")

# ── 运行状态 ──
st.divider()
st.subheader("运行状态")

if is_running:
    st.success(f"调度器运行中 | 下次执行: {get_next_run_time(st.session_state)}")
else:
    st.info("调度器未启动")

st.write(f"当前配置: 每日 `{cfg.get('hour', 15):02d}:{cfg.get('minute', 30):02d}` 执行")

# ── 扫描历史 ──
st.divider()
st.subheader("扫描历史")

history = get_scan_history()
if history:
    selected = st.selectbox("选择日期", history,
                             format_func=lambda x: x.replace("scan_", "").replace(".csv", ""))
    filepath = os.path.join(HISTORY_DIR, selected)
    df = pd.read_csv(filepath)
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.download_button(
        "下载 CSV",
        data=df.to_csv(index=False).encode("utf-8-sig"),
        file_name=selected,
        mime="text/csv",
    )
else:
    st.info("暂无扫描记录，点击「立即执行一次」开始")

# ── 通知记录 ──
st.divider()
st.subheader("通知记录")

log_file = os.path.join(HISTORY_DIR, "notifications.jsonl")
if os.path.exists(log_file):
    logs = []
    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                logs.append(json.loads(line))
    if logs:
        logs.reverse()
        for log in logs[:20]:
            with st.expander(f"{log['title']} — {log['time']}"):
                st.text(log["message"])
    else:
        st.info("暂无通知记录")
else:
    st.info("暂无通知记录")
