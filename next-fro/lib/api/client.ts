import { messages } from "@/messages";
import {
  getAccessToken,
  getRefreshToken,
  setTokenPair,
  removeTokenPair,
} from "@/lib/auth/token";

import type {
  ApiResponse,
  TokenPair,
} from "@/types/auth";

import type { ValidationIssue } from "@/types/api";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

// 携带 HTTP 状态码的请求错误，便于调用方按状态处理

export class ApiError extends Error {
  status: number;
  validationIssues: ValidationIssue[];

  constructor(
    message: string,
    status: number,
    validationIssues: ValidationIssue[] = [],
  ) {
    super(message);

    this.name = "ApiError";
    this.status = status;
    this.validationIssues = validationIssues;
  }
}

// 保存当前正在进行的刷新任务
// 多个请求可以共享同一个 Promise
let refreshPromise: Promise<string | null> | null = null;


// 刷新 Access Token
async function refreshAccessToken(): Promise<string | null> {
  // 如果已经有刷新任务，就直接等待它
  if (refreshPromise) {
    return refreshPromise;
  }

  refreshPromise = (async () => {
    const refreshToken = getRefreshToken();

    if (!refreshToken) {
      return null;
    }

    try {
      // 注意：这里直接使用 fetch
      // 不能再调用 apiFetch，否则可能产生递归刷新
      const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          refresh_token: refreshToken,
        }),
      });

      const body: ApiResponse<TokenPair> = await response.json();

      if (
        !response.ok ||
        !body.data?.access_token ||
        !body.data?.refresh_token
      ) {
        return null;
      }

      // 保存后端返回的新 Token Pair
      setTokenPair(
        body.data.access_token,
        body.data.refresh_token,
      );

      return body.data.access_token;

    } catch {
      return null;
    }
  })();

  try {
    return await refreshPromise;
  } finally {
    refreshPromise = null;
  }
}


// 发送一次 HTTP 请求
async function sendRequest(
  path: string,
  options: RequestInit,
  token: string | null,
): Promise<Response> {
  const headers = new Headers(options.headers);

  // 没有指定 Content-Type 时，默认使用 JSON
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  // 有 Access Token 才设置 Authorization
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  return fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  });
}


// API 请求的额外配置，用于控制是否跳过刷新
// 默认不跳过刷新
export interface ApiFetchOptions extends RequestInit {
  skipAuthRefresh?: boolean;
}

// 返回原始 Response，供 SSE 等非 JSON 接口复用同一套双 Token 刷新逻辑。
export async function authenticatedFetch(
  path: string,
  options: ApiFetchOptions = {},
): Promise<Response> {
  const originalToken = getAccessToken();
  const { skipAuthRefresh = false, ...requestOptions } = options;
  let response = await sendRequest(path, requestOptions, originalToken);

  let errorBody: unknown = null;
  if (response.status === 401) {
    try {
      errorBody = await response.clone().json();
    } catch {
      errorBody = null;
    }
  }

  const accessExpired =
    response.status === 401 &&
    (errorBody as { detail?: { code?: string } } | null)?.detail?.code === "ACCESS_EXPIRED";

  if (!accessExpired || skipAuthRefresh) return response;

  const currentToken = getAccessToken();
  const newAccessToken =
    originalToken && currentToken && originalToken !== currentToken
      ? currentToken
      : await refreshAccessToken();

  if (!newAccessToken) {
    removeTokenPair();
    return response;
  }

  response = await sendRequest(path, requestOptions, newAccessToken);
  return response;
}



// 统一 API 请求入口
export async function apiFetch<T>(
  path: string,
  options: ApiFetchOptions = {},
): Promise<T> {

  const response = await authenticatedFetch(path, options);
  const body = await response.json();

  // 最终响应仍然失败，就抛出错误
  
if (!response.ok) {
  const validationIssues: ValidationIssue[] =
    response.status === 422 && Array.isArray(body?.data)
      ? body.data
      : [];

  const message =
    typeof body?.message === "string"
      ? body.message
      : typeof body?.detail === "string"
        ? body.detail
        : typeof body?.detail?.message === "string"
          ? body.detail.message
          : messages.common.httpRequestFailed(response.status);

  throw new ApiError(
    message,
    response.status,
    validationIssues,
  );
}

  return body as T;
}
