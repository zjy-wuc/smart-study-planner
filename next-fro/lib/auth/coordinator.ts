import { AUTH_EPOCH_KEY, acceptBroadcastToken, getAccessToken, getAuthGeneration, readAuthEpoch, setAccessToken } from "./token";

const channelName = "ssp-auth-v2";
const refreshVersionKey = "ssp-auth-refresh-version";
const uncertainRefreshKey = "ssp-auth-uncertain-refresh";
let refreshPromise: Promise<string> | null = null;
let refreshEpoch: string | null = null;
let refreshGeneration = 0;
let channel: BroadcastChannel | null = null;

function refreshVersion(epoch: string | null): number {
  const stored = localStorage.getItem(refreshVersionKey);
  if (!stored) return 0;
  try {
    const value = JSON.parse(stored) as { epoch?: string | null; version?: number };
    return value.epoch === epoch && Number.isInteger(value.version) ? value.version! : 0;
  } catch { return 0; }
}

function advanceRefreshVersion(epoch: string | null): number {
  // Web Lock 内递增；迟到的旧广播不能覆盖后一次刷新的 Token。
  const version = refreshVersion(epoch) + 1;
  localStorage.setItem(refreshVersionKey, JSON.stringify({ epoch, version }));
  return version;
}

function getChannel(): BroadcastChannel | null {
  if (
    typeof window === "undefined" ||
    typeof window.BroadcastChannel !== "function"
  )
    return null;
  if (!channel) channel = new BroadcastChannel(channelName);
  return channel;
}

export function authEpoch(): string | null {
  return readAuthEpoch();
}

export function sameAuthEpoch(epoch: string | null): boolean {
  return authEpoch() === epoch;
}

export function announceAuthChange(type: "login" | "logout"): string {
  const epoch = `${type}:${crypto.randomUUID()}`;
  localStorage.setItem(AUTH_EPOCH_KEY, epoch);
  getChannel()?.postMessage({ type, epoch });
  return epoch;
}

export function onAuthMessage(
  listener: (type: "login" | "logout") => void,
): () => void {
  const bus = getChannel();
  let notifiedEpoch: string | null = null;
  const notify = (type: "login" | "logout", epoch: string) => {
    if (epoch !== authEpoch() || notifiedEpoch === epoch) return;
    notifiedEpoch = epoch;
    listener(type);
  };
  const receive = (event: MessageEvent) => {
    const message = event.data;
    try {
      if (message?.epoch !== authEpoch()) return;
      if (message.type === "token" && typeof message.token === "string" &&
          message.version === refreshVersion(message.epoch))
        acceptBroadcastToken(message.token, message.epoch);
      if (message.type === "login" || message.type === "logout")
        notify(message.type, message.epoch);
    } catch { /* 存储不可用时不接受无法核对代际的消息。 */ }
  };
  const storage = (event: StorageEvent) => {
    if (event.key !== AUTH_EPOCH_KEY || !event.newValue) return;
    try { notify(event.newValue.startsWith("logout:") ? "logout" : "login", event.newValue); }
    catch { /* 同上：无法核对共享代际时忽略消息。 */ }
  };
  bus?.addEventListener("message", receive);
  if (typeof window !== "undefined" && typeof window.addEventListener === "function")
    window.addEventListener("storage", storage);
  return () => {
    bus?.removeEventListener("message", receive);
    if (typeof window !== "undefined" && typeof window.removeEventListener === "function")
      window.removeEventListener("storage", storage);
  };
}

export async function withAuthLock<T>(work: () => Promise<T>): Promise<T> {
  authEpoch(); // 共享存储不可用时，在修改 Cookie 前失败。
  if (typeof navigator === "undefined" || !navigator.locks?.request) {
    throw new Error(
      "当前浏览器无法安全协调多标签页认证，请使用支持 Web Locks 的浏览器",
    );
  }
  return navigator.locks.request(channelName, { mode: "exclusive" }, work);
}

export function refreshAccessToken(
  usedToken: string | null,
  requestRefresh: () => Promise<string>,
): Promise<string> {
  const epoch = authEpoch();
  const generation = getAuthGeneration();
  const seenVersion = refreshVersion(epoch);
  if (
    refreshPromise &&
    refreshEpoch === epoch &&
    refreshGeneration === generation
  )
    return refreshPromise;
  const pending = withAuthLock(async () => {
    if (!sameAuthEpoch(epoch) || getAuthGeneration() !== generation)
      throw new Error("登录状态已变化，请重试");
    const newer = getAccessToken();
    if (newer && newer !== usedToken) return newer;
    // 广播可能晚于获锁；已有别的标签页刷新成功时，等待其消息而非再次轮换 Cookie。
    if (refreshVersion(epoch) !== seenVersion)
      throw new Error("登录状态已变化，请重试");
    // 超时后 Cookie 可能已经轮换，不能再次发送 Refresh Token。
    if (localStorage.getItem(uncertainRefreshKey) === JSON.stringify(epoch))
      throw new Error("刷新结果不确定，请重新登录");
    let token: string;
    try {
      token = await requestRefresh();
    } catch (error) {
      const status = error && typeof error === "object" && "status" in error
        ? (error as { status: unknown }).status : undefined;
      if (typeof status !== "number" || status === 0 || status >= 500)
        localStorage.setItem(uncertainRefreshKey, JSON.stringify(epoch));
      throw error;
    }
    if (!sameAuthEpoch(epoch) || getAuthGeneration() !== generation)
      throw new Error("登录状态已变化，请重试");
    const version = advanceRefreshVersion(epoch);
    setAccessToken(token, epoch);
    getChannel()?.postMessage({ type: "token", token, epoch, version });
    return token;
  });
  const tracked = pending.finally(() => {
    if (refreshPromise === tracked) refreshPromise = null;
  });
  refreshPromise = tracked;
  refreshEpoch = epoch;
  refreshGeneration = generation;
  return tracked;
}
