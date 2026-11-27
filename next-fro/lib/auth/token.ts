// Access Token 只存在当前标签页的运行内存中；服务端渲染不读写此变量。
let accessToken: string | null = null;
let tokenEpoch: string | null = null;
let clearedEpoch: string | null | undefined;
let generation = 0;
const listeners = new Set<() => void>();
export const AUTH_EPOCH_KEY = "ssp-auth-epoch";

export function readAuthEpoch(): string | null {
  return typeof window === "undefined" ? null : localStorage.getItem(AUTH_EPOCH_KEY);
}

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return tokenEpoch === readAuthEpoch() ? accessToken : null;
}

export function getAuthGeneration(): number {
  return generation;
}

export function setAccessToken(token: string, epoch = readAuthEpoch()): void {
  if (typeof window === "undefined") return;
  if (epoch !== readAuthEpoch()) throw new Error("登录状态已变化，请重试");
  accessToken = token;
  tokenEpoch = epoch;
  clearedEpoch = undefined;
  listeners.forEach((listener) => listener());
}

export function clearAccessToken(): void {
  accessToken = null;
  tokenEpoch = null;
  try { clearedEpoch = readAuthEpoch(); }
  catch { clearedEpoch = undefined; }
  generation += 1;
  listeners.forEach((listener) => listener());
}

export function acceptBroadcastToken(token: string, epoch: string | null): void {
  // 只更新已经属于同一代际的本地会话；退出后的迟到消息不能复活它。
  if (accessToken && tokenEpoch === epoch && clearedEpoch !== epoch && readAuthEpoch() === epoch)
    setAccessToken(token, epoch);
}

export function subscribeAuth(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function clearLegacyTokens(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
}
