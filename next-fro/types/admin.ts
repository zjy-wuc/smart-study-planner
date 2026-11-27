export type PageResult<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};
export type AdminUser = {
  id: number;
  username: string;
  nickname: string | null;
  email: string;
  role: "USER" | "ADMIN";
  is_active: boolean;
  created_at: string;
  avatar_url: string | null;
};
export type AdminUserDetail = AdminUser & {
  updated_at: string;
  email_verified_at: string | null;
  statistics: {
    active_plan_count: number;
    note_count: number;
    today_ai_requests: number;
    active_session_count: number;
  };
};
export type AdminAction =
  | "BAN_USER"
  | "UNBAN_USER"
  | "REVOKE_SESSIONS"
  | "UPDATE_AI_CONFIG";
export type UserAction = Exclude<AdminAction, "UPDATE_AI_CONFIG">;
export type UserActionResult = {
  user_id: number;
  is_active: boolean;
  revoked_session_count: number;
  revoked_token_count: number;
  changed: boolean;
};
export type AdminDashboard = {
  as_of_date: string;
  overview: {
    total_users: number;
    enabled_users: number;
    disabled_users: number;
    new_users_today: number;
    learning_active_users_today: number;
    total_checkins: number;
    today_checkins: number;
    total_plans: number;
    active_plans: number;
    total_notes: number;
    today_ai_requests: number;
  };
  daily_trend: {
    date: string;
    new_user_count: number;
    active_user_count: number;
    checkin_count: number;
  }[];
  plan_status_distribution: { DRAFT: number; ACTIVE: number; ENDED: number };
};
export type AIConfig = {
  id: number;
  enabled: boolean;
  user_daily_limit: number;
  global_daily_limit: number;
  effective_enabled: boolean;
  effective_user_daily_limit: number;
  effective_global_daily_limit: number;
  hard_user_daily_limit: number;
  hard_global_daily_limit: number;
  user_concurrency: number;
  global_concurrency: number;
  user_rate_limit: number;
  rate_window_seconds: number;
  model_configured: boolean;
  updated_at: string;
  changed?: boolean;
};
export type AIStatistics = {
  as_of_date: string;
  overview: {
    today_used: number;
    today_remaining: number;
    today_success: number;
    today_failed: number;
    today_cancelled: number;
    current_active: number;
  };
  config: {
    enabled: boolean;
    configured_enabled: boolean;
    user_daily_limit: number;
    global_daily_limit: number;
    user_concurrency: number;
    global_concurrency: number;
    model_configured: boolean;
  };
  daily_trend: { date: string; request_count: number }[];
  status_distribution: Record<string, number>;
  operation_distribution: Record<string, number>;
};
export type AuditLog = {
  id: number;
  admin_id: number;
  admin_username: string | null;
  action: AdminAction;
  target_type: "USER" | "AI_CONFIG";
  target_id: number;
  before_data: Record<string, unknown> | null;
  after_data: Record<string, unknown> | null;
  reason: string;
  created_at: string;
};
