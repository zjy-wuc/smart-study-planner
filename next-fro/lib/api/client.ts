import { getAccessToken } from "@/lib/auth/token";

const API_BASE_URL = "http://127.0.0.1:8000";

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  // 获取本地保存的 Access Token
  const token = getAccessToken();

  
  const headers = {
    "Content-Type": "application/json",

    // 有 Token 才添加 Authorization
    ...(token
      ? { Authorization: `Bearer ${token}` }
      : {}),

    // 保留调用者自己传入的请求头,不能用默认的json请求头覆盖
    ...options.headers,
  };

  
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  });

  const body = await response.json();

  // 处理 HTTP 错误
  if (!response.ok) {
    throw new Error(body?.message ?? `请求失败（${response.status}）`);
  }

  return body as T;
}