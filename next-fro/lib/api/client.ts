const API_BASE_URL = "http://127.0.0.1:8000";

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  const body = await response.json();

  // 后端返回非 2xx 时抛出错误，交给调用方 catch
  if (!response.ok) {
    throw new Error(body?.message ?? `请求失败（${response.status}）`);
  }

  return body as T;
}
