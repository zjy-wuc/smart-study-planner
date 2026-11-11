// 后端统一响应结构
export interface ApiResponse<T> {
  code: number;
  message: string;
  data: T;
  detail?: {
    code?: string;
    message?: string;
  };
}
// 注册请求体
export interface RegisterRequest {
  username: string;
  password: string;
  nickname: string;
}

// 注册成功后返回的用户信息
export interface RegisterData {
  id: number;
  username: string;
  nickname: string;
}






 // 用户登录请求数据
 
export interface LoginRequest {
  username: string;
  password: string;
}


 
export interface LoginResponse extends TokenPair {
  user: User;
}

// 当前登录用户信息（GET /users/me 返回）
export interface User {
  id: number;
  username: string;
  nickname: string | null;
}




//用户登录成功返回的数据
 
export interface LoginResponse extends TokenPair {
  user: User;
}


// 双 Token 响应数据
export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

// Refresh Token 请求体
export interface RefreshRequest {
  refresh_token: string;
}