import axios, { AxiosHeaders, type AxiosRequestConfig } from "axios";
import { messages } from "@/messages";
import {
  authEpoch,
  refreshAccessToken,
  sameAuthEpoch,
} from "@/lib/auth/coordinator";
import { clearAccessToken, getAccessToken, getAuthGeneration } from "@/lib/auth/token";
import type { ValidationIssue } from "@/types/api";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type BackendError = {
  detail?: string | { code?: string; message?: string } | ValidationIssue[];
  message?: string;
  data?: unknown;
};
type AuthConfig = AxiosRequestConfig & {
  skipAuthRefresh?: boolean;
  retried?: boolean;
  tokenUsed?: string | null;
  epoch?: string | null;
  userActivity?: boolean;
};

function sessionMismatch(): ApiError {
  return new ApiError("登录状态已变化，请重试", 409, [], "SESSION_MISMATCH");
}

function clearIfCurrent(epoch: string | null, usedToken: string | null): void {
  // 旧请求的错误不能清掉切换账号或同代际刷新后取得的新 Token。
  if (sameAuthEpoch(epoch) && getAccessToken() === usedToken) clearAccessToken();
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public validationIssues: ValidationIssue[] = [],
    public code?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function apiError(status: number, body: BackendError | undefined): ApiError {
  const detail = body?.detail;
  const issues = Array.isArray(detail)
    ? detail
    : Array.isArray(body?.data) && status === 422
      ? (body.data as ValidationIssue[])
      : [];
  const message =
    typeof detail === "string"
      ? detail
      : !Array.isArray(detail) && detail?.message
        ? detail.message
        : issues.length
          ? issues.map((issue) => issue.msg).join("；")
          : (body?.message ?? messages.common.httpRequestFailed(status));
  return new ApiError(
    message,
    status,
    issues,
    !Array.isArray(detail) && typeof detail === "object"
      ? detail?.code
      : undefined,
  );
}

const refreshClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000,
  withCredentials: true,
});
export const httpClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 20000,
  withCredentials: true,
});

async function requestRefresh(): Promise<string> {
  try {
    const response = await refreshClient.post("/auth/refresh", null, {
      headers: { "X-CSRF-Protection": "1" },
    });
    const token = response.data?.data?.access_token;
    if (typeof token !== "string" || !token)
      throw new ApiError(
        messages.auth.sessionExpired,
        401,
        [],
        "REFRESH_INVALID",
      );
    return token;
  } catch (error) {
    if (axios.isAxiosError(error))
      throw apiError(error.response?.status ?? 0, error.response?.data);
    throw error;
  }
}

export async function restoreAccessToken(): Promise<string> {
  return refreshAccessToken(getAccessToken(), requestRefresh);
}

httpClient.interceptors.request.use((config) => {
  const auth = config as AuthConfig;
  const currentEpoch = authEpoch();
  if (auth.epoch !== undefined && auth.epoch !== currentEpoch) throw sessionMismatch();
  auth.epoch = currentEpoch;
  auth.tokenUsed = getAccessToken();
  config.headers = AxiosHeaders.from(config.headers);
  if (auth.tokenUsed)
    config.headers.set("Authorization", `Bearer ${auth.tokenUsed}`);
  else config.headers.delete("Authorization");
  if (
    config.method &&
    !["get", "head", "options"].includes(config.method.toLowerCase())
  )
    config.headers.set("X-CSRF-Protection", "1");
  if (auth.userActivity) config.headers.set("X-User-Activity", "1");
  return config;
});

httpClient.interceptors.response.use(
  (response) => {
    const config = response.config as AuthConfig;
    if (!sameAuthEpoch(config.epoch ?? null)) throw sessionMismatch();
    return response;
  },
  async (error: unknown) => {
    if (!axios.isAxiosError(error)) throw error;
    const config = error.config as AuthConfig | undefined;
    const status = error.response?.status ?? 0;
    const parsed = apiError(status, error.response?.data);
    if (config && !sameAuthEpoch(config.epoch ?? null)) throw sessionMismatch();
    if (
      status === 401 &&
      parsed.code === "ACCESS_EXPIRED" &&
      config &&
      !config.retried &&
      !config.skipAuthRefresh
    ) {
      config.retried = true;
      try {
        const token = await refreshAccessToken(
          config.tokenUsed ?? null,
          requestRefresh,
        );
        if (!sameAuthEpoch(config.epoch ?? null)) throw sessionMismatch();
        config.headers = AxiosHeaders.from(
          config.headers as Record<string, string>,
        );
        config.headers.set("Authorization", `Bearer ${token}`);
        return await httpClient.request(config);
      } catch (refreshError) {
        if (
          refreshError instanceof ApiError &&
          [
            "REFRESH_INVALID",
            "SESSION_REVOKED",
            "SESSION_EXPIRED",
            "ACCOUNT_DISABLED",
          ].includes(refreshError.code ?? "")
        )
          clearIfCurrent(config.epoch ?? null, config.tokenUsed ?? null);
        throw refreshError;
      }
    }
    if (
      [401, 403].includes(status) &&
      !config?.skipAuthRefresh &&
      [
        "SESSION_REVOKED",
        "SESSION_EXPIRED",
        "ACCOUNT_DISABLED",
        "INVALID_TOKEN",
      ].includes(parsed.code ?? "")
    )
      clearIfCurrent(config?.epoch ?? null, config?.tokenUsed ?? null);
    throw parsed;
  },
);

export interface ApiFetchOptions extends RequestInit {
  skipAuthRefresh?: boolean;
  userActivity?: boolean;
}

export async function apiFetch<T>(
  path: string,
  options: ApiFetchOptions = {},
): Promise<T> {
  const { skipAuthRefresh, userActivity, ...request } = options;
  const headers = AxiosHeaders.from(
    request.headers as Record<string, string> | undefined,
  );
  if (typeof request.body === "string" && !headers.has("Content-Type"))
    headers.set("Content-Type", "application/json");
  const method = request.method ?? "GET";
  const activeRequest =
    userActivity ??
    (method !== "GET" &&
      ["/plans", "/tasks", "/notes", "/focus", "/ai/practices"].some(
        (prefix) => path === prefix || path.startsWith(`${prefix}/`),
      ) &&
      path !== "/focus/sync");
  const response = await httpClient.request<T>({
    url: path,
    method,
    headers,
    data: request.body,
    signal: request.signal ?? undefined,
    skipAuthRefresh,
    userActivity: activeRequest,
    epoch: authEpoch(),
  } as AuthConfig);
  return response.data;
}

function guardSseResponse(response: Response, epoch: string | null, generation: number): Response {
  if (!response.body || !response.headers.get("Content-Type")?.startsWith("text/event-stream"))
    return response;
  const reader = response.body.getReader();
  const current = () => sameAuthEpoch(epoch) && getAuthGeneration() === generation;
  const body = new ReadableStream<Uint8Array>({
    async pull(controller) {
      try {
        if (!current()) throw sessionMismatch();
        const chunk = await reader.read();
        if (!current()) throw sessionMismatch();
        if (chunk.done) controller.close();
        else controller.enqueue(chunk.value);
      } catch (error) {
        void reader.cancel().catch(() => {});
        controller.error(error);
      }
    },
    cancel(reason) { return reader.cancel(reason); },
  }, { highWaterMark: 0 });
  const guarded = new Response(body, {
    status: response.status,
    statusText: response.statusText,
    headers: response.headers,
  });
  sseSessionChecks.set(guarded, current);
  return guarded;
}

const sseSessionChecks = new WeakMap<Response, () => boolean>();

export function assertSseSession(response: Response): void {
  // 解码后、交给组件前再检查一次，防止已缓冲的旧事件写入新账号界面。
  if (sseSessionChecks.get(response)?.() === false) throw sessionMismatch();
}

// 流式响应仍交给 ReadableStream；只在收到 HTTP 401 且尚未开始读流时重试。
export async function authenticatedFetch(
  path: string,
  options: ApiFetchOptions = {},
): Promise<Response> {
  const { skipAuthRefresh = false, userActivity = false, ...request } = options;
  const epoch = authEpoch();
  const generation = getAuthGeneration();
  const original = getAccessToken();
  async function send(token: string | null) {
    if (!sameAuthEpoch(epoch) || getAuthGeneration() !== generation)
      throw sessionMismatch();
    const headers = new Headers(request.headers);
    if (token) headers.set("Authorization", `Bearer ${token}`);
    else headers.delete("Authorization");
    if (
      request.method &&
      !["GET", "HEAD", "OPTIONS"].includes(request.method.toUpperCase())
    )
      headers.set("X-CSRF-Protection", "1");
    if (userActivity) headers.set("X-User-Activity", "1");
    if (
      request.body &&
      !(request.body instanceof FormData) &&
      !headers.has("Content-Type")
    )
      headers.set("Content-Type", "application/json");
    return fetch(`${API_BASE_URL}${path}`, {
      ...request,
      headers,
      credentials: "include",
    });
  }
  let response = await send(original);
  if (!sameAuthEpoch(epoch) || getAuthGeneration() !== generation) throw sessionMismatch();
  if (skipAuthRefresh || ![401, 403].includes(response.status))
    return guardSseResponse(response, epoch, generation);
  const body = await response
    .clone()
    .json()
    .catch(() => null);
  if (!sameAuthEpoch(epoch) || getAuthGeneration() !== generation) throw sessionMismatch();
  if (
    [401, 403].includes(response.status) &&
    [
      "SESSION_REVOKED",
      "SESSION_EXPIRED",
      "ACCOUNT_DISABLED",
      "INVALID_TOKEN",
    ].includes(body?.detail?.code)
  )
    clearIfCurrent(epoch, original);
  if (response.status !== 401 || body?.detail?.code !== "ACCESS_EXPIRED")
    return guardSseResponse(response, epoch, generation);
  let token: string;
  try {
    token = await refreshAccessToken(original, requestRefresh);
  } catch (error) {
    if (
      error instanceof ApiError &&
      [
        "REFRESH_INVALID",
        "SESSION_REVOKED",
        "SESSION_EXPIRED",
        "ACCOUNT_DISABLED",
      ].includes(error.code ?? "")
    )
      clearIfCurrent(epoch, original);
    throw error;
  }
  if (!sameAuthEpoch(epoch) || getAuthGeneration() !== generation) throw sessionMismatch();
  response = await send(token);
  if (!sameAuthEpoch(epoch) || getAuthGeneration() !== generation) throw sessionMismatch();
  return guardSseResponse(response, epoch, generation);
}
