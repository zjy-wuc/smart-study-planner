declare global {
  interface Window {
    __SSP_RUNTIME_CONFIG__?: {
      apiBaseUrl?: string;
    };
  }
}

/**
 * 解析后端 API 基础地址。
 *
 * 优先读取部署时注入的 public/runtime-config.js，
 * 这样更换后端地址不需要重新构建前端。
 */
export function resolveApiBaseUrl(): string {
  if (typeof window !== "undefined") {
    const runtime = window.__SSP_RUNTIME_CONFIG__?.apiBaseUrl;
    if (runtime) return runtime;
  }
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

export const API_BASE_URL = resolveApiBaseUrl();