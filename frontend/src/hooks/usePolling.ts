import { useEffect, useRef } from "react";

/**
 * 轻量轮询 hook。挂载时立即跑一次 fetcher，并按 intervalMs 重复调用。
 * 卸载、interval 改变、enabled=false 时自动清除定时器。
 *
 * 适合 Dashboard/News/Scheduler 这种「定时刷新整页」的场景。
 * 任务态启停（success/failed 后停下）的复杂轮询请保留页面内的 startPolling/stopPolling 写法。
 */
export function usePolling(
  fetcher: () => void | Promise<unknown>,
  intervalMs: number,
  enabled: boolean = true,
) {
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  useEffect(() => {
    if (!enabled || intervalMs <= 0) return;
    fetcherRef.current();
    const timer = setInterval(() => {
      fetcherRef.current();
    }, intervalMs);
    return () => clearInterval(timer);
  }, [intervalMs, enabled]);
}
