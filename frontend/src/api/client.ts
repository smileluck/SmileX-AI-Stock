import axios from "axios";
import type { AxiosError, InternalAxiosRequestConfig } from "axios";

const SLOW_REQUEST_MS = 3000;

const client = axios.create({
  baseURL: "http://127.0.0.1:8801/api/v1",
  timeout: 30000,
});

// 请求耗时埋点：>3s 在 console.warn 提示，便于排查后端慢接口。
// 不在拦截器里做全局错误 toast：现有页面已各自处理错误，全局 toast 会与页内提示重复。
// 业务方需要全局错误提示时，请在调用处自行 message.error。
type RequestConfigWithMeta = InternalAxiosRequestConfig & { _startedAt?: number };

client.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  (config as RequestConfigWithMeta)._startedAt = performance.now();
  return config;
});

client.interceptors.response.use(
  (response) => {
    const cfg = response.config as RequestConfigWithMeta;
    if (cfg._startedAt != null) {
      const dur = performance.now() - cfg._startedAt;
      if (dur > SLOW_REQUEST_MS) {
        console.warn(`[api slow] ${cfg.method?.toUpperCase()} ${cfg.url} ${dur.toFixed(0)}ms`);
      }
    }
    return response;
  },
  (error: AxiosError) => {
    const cfg = error.config as RequestConfigWithMeta | undefined;
    const url = cfg?.url || "";
    const method = cfg?.method?.toUpperCase() || "";
    const status = error.response?.status;
    const dur = cfg?._startedAt != null ? performance.now() - cfg._startedAt : null;
    console.error(`[api fail] ${method} ${url} status=${status} dur=${dur?.toFixed(0) ?? "?"}ms`, error.message);
    return Promise.reject(error);
  },
);

export default client;
