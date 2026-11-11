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

const API_BASE_URL = "http://127.0.0.1:8000";

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


// 统一 API 请求入口
export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {

  // 记录第一次请求使用的 Token
  const originalToken = getAccessToken();

  // 第一次请求
  let response = await sendRequest(
    path,
    options,
    originalToken,
  );

  let body = await response.json();

  // 只有 Access Token 确认过期，才尝试刷新
  const accessExpired =
    response.status === 401 &&
    body?.detail?.code === "ACCESS_EXPIRED";

  if (accessExpired) {
    const currentToken = getAccessToken();

    let newAccessToken: string | null = null;

    // 情况一：
    // 当前 Token 已经和第一次请求时不同
    // 说明其他请求可能已经完成了刷新
    if (
      originalToken &&
      currentToken &&
      originalToken !== currentToken
    ) {
      newAccessToken = currentToken;
    } else {
      // 情况二：
      // 还没有其他请求完成刷新，执行或等待刷新任务
      newAccessToken = await refreshAccessToken();
    }

    if (newAccessToken) {
      // 使用新 Token 重试一次
      response = await sendRequest(
        path,
        options,
        newAccessToken,
      );

      body = await response.json();

    } else {
      // 刷新失败，清理双 Token
      removeTokenPair();
    }
  }

  // 最终响应仍然失败，就抛出错误
  if (!response.ok) {
    throw new Error(
      body?.message ??
      body?.detail?.message ??
      `请求失败（${response.status}）`,
    );
  }

  return body as T;
}