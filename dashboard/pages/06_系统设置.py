import os
import json
import streamlit as st
import pandas as pd

from smilex.scheduler import (
    load_config, start_scheduler, stop_scheduler,
    get_next_run_time, get_scan_history, run_daily_job,
    start_news_sync, stop_news_sync,
    start_market_sync, stop_market_sync,
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

# ── 新闻同步 ──
st.divider()
st.subheader("新闻同步")

news_cfg = load_config()
news_enabled = news_cfg.get("news_sync_enabled", False)
news_interval = news_cfg.get("news_sync_interval", 30)

scheduler = st.session_state.get("_scheduler")
is_news_running = (
    scheduler is not None
    and scheduler.running
    and scheduler.get_job("news_sync") is not None
)

news_interval = st.number_input(
    "同步间隔（秒）", min_value=10, max_value=300, value=news_interval,
)

col_start_news, col_stop_news, col_manual_news = st.columns(3)

with col_start_news:
    if st.button("启动新闻同步", type="primary", disabled=is_news_running):
        try:
            start_news_sync(st.session_state, news_interval)
            st.success(f"新闻同步已启动，每 {news_interval} 秒同步一次")
            st.rerun()
        except Exception as e:
            st.error(f"启动失败：{e}")

with col_stop_news:
    if st.button("停止新闻同步", disabled=not is_news_running):
        stop_news_sync(st.session_state)
        st.success("新闻同步已停止")
        st.rerun()

with col_manual_news:
    if st.button("立即同步一次新闻"):
        with st.spinner("正在同步新闻..."):
            try:
                from smilex.news_sync import sync_all_news
                sync_all_news()
                st.success("新闻同步完成")
            except Exception as e:
                st.error(f"同步失败：{e}")

if is_news_running:
    st.success(f"新闻同步运行中 | 间隔: {news_interval} 秒")
else:
    st.info("新闻同步未启动")

# ── 大盘同步 ──
st.divider()
st.subheader("大盘同步")

market_cfg = load_config()
market_interval = market_cfg.get("market_sync_interval", 60)

is_market_running = (
    scheduler is not None
    and scheduler.running
    and scheduler.get_job("market_sync") is not None
)

market_interval = st.number_input(
    "同步间隔（秒）", min_value=30, max_value=300,
    value=market_interval, key="market_interval",
)

col_start_m, col_stop_m, col_manual_m = st.columns(3)

with col_start_m:
    if st.button("启动大盘同步", type="primary", disabled=is_market_running):
        try:
            start_market_sync(st.session_state, market_interval)
            st.success(f"大盘同步已启动，每 {market_interval} 秒同步一次")
            st.rerun()
        except Exception as e:
            st.error(f"启动失败：{e}")

with col_stop_m:
    if st.button("停止大盘同步", disabled=not is_market_running):
        stop_market_sync(st.session_state)
        st.success("大盘同步已停止")
        st.rerun()

with col_manual_m:
    if st.button("立即同步一次大盘"):
        with st.spinner("正在同步大盘数据..."):
            try:
                from smilex.scheduler import sync_market_overview
                sync_market_overview()
                st.success("大盘同步完成")
            except Exception as e:
                st.error(f"同步失败：{e}")

if is_market_running:
    st.success(f"大盘同步运行中 | 间隔: {market_interval} 秒")
else:
    st.info("大盘同步未启动")

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
