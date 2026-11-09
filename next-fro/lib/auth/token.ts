const ACCESS_TOKEN_KEY = "access_token";

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