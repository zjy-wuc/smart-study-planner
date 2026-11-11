/**
 * 保存、读取、删除双 Token
 */

const ACCESS_TOKEN_KEY = "access_token";
const REFRESH_TOKEN_KEY = "refresh_token";

// 保存 Access Token
export function setAccessToken(token: string) {
  localStorage.setItem(ACCESS_TOKEN_KEY, token);
}

// 获取 Access Token
export function getAccessToken() {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

// 删除 Access Token
export function removeAccessToken() {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
}

// 保存 Refresh Token
export function setRefreshToken(token: string) {
  localStorage.setItem(REFRESH_TOKEN_KEY, token);
}

// 获取 Refresh Token
export function getRefreshToken() {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

// 删除 Refresh Token
export function removeRefreshToken() {
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

// 同时保存双 Token
export function setTokenPair(
  accessToken: string,
  refreshToken: string,
) {
  setAccessToken(accessToken);
  setRefreshToken(refreshToken);
}

// 同时清理双 Token
export function removeTokenPair() {
  removeAccessToken();
  removeRefreshToken();
}
