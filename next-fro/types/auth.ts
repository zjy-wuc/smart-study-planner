export interface ApiResponse<T> {
  code: number;
  message: string;
  data: T;
}

export interface User {
  id: number;
  username: string;
  nickname: string | null;
  email: string;
  avatar_url: string | null;
  email_verified_at: string;
  is_active: boolean;
}

export interface AccessTokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface LoginResponse extends AccessTokenResponse {
  user: User;
}

export interface RegisterRequest {
  username: string;
  email: string;
  code: string;
  password: string;
  nickname?: string | null;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface EmailLoginRequest {
  email: string;
  code: string;
}

export type EmailCodePurpose =
  | "REGISTER"
  | "LOGIN"
  | "RESET_PASSWORD"
  | "CHANGE_EMAIL_OLD"
  | "CHANGE_EMAIL_NEW";

export interface PasswordResetRequest {
  email: string;
  code: string;
  new_password: string;
}

export interface PasswordChangeRequest {
  old_password: string;
  new_password: string;
}

export interface EmailChangeRequest {
  password: string;
  old_email_code: string;
  new_email: string;
  new_email_code: string;
}

export interface LoginSession {
  family_id: string;
  device_name: string;
  is_current: boolean;
  created_at: string;
  last_activity_at: string;
  absolute_expires_at: string;
}

export interface SessionListResponse {
  items: LoginSession[];
  total: number;
  page: number;
  page_size: number;
}
