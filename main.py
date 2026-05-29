"""SmileX A股量化选股系统 — 一键启动

运行方式:
    uv run python main.py

启动 Streamlit 看板，浏览器访问 http://localhost:8501
定时任务在看板「系统设置」页面中控制启停。
"""

import os
import sys
import signal
import subprocess
import time

sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")
sys.stderr.reconfigure(line_buffering=True, encoding="utf-8")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from smilex.config import DASHBOARD_PORT, DASHBOARD_HOST

streamlit_proc = None


def start_streamlit() -> subprocess.Popen:
    dashboard = os.path.join(os.path.dirname(__file__), "dashboard", "app.py")
    return subprocess.Popen(
        [
            sys.executable, "-m", "streamlit", "run", dashboard,
            "--server.headless", "true",
            "--server.port", str(DASHBOARD_PORT),
            "--server.address", DASHBOARD_HOST,
        ],
        stdout=sys.stdout, stderr=sys.stderr,
    )


def shutdown(signum=None, frame=None):
    if streamlit_proc:
        streamlit_proc.terminate()
        streamlit_proc.wait(timeout=5)
    sys.exit(0)


def main():
    global streamlit_proc

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    streamlit_proc = start_streamlit()
    print(f"SmileX 看板已启动: http://localhost:{DASHBOARD_PORT}")

    try:
        while True:
            if streamlit_proc.poll() is not None:
                print("[看板] 进程退出，5秒后重启...")
                time.sleep(5)
                streamlit_proc = start_streamlit()
            time.sleep(5)
    except KeyboardInterrupt:
        shutdown()


if __name__ == "__main__":
    main()
