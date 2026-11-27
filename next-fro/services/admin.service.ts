import { apiFetch, ApiError } from "@/lib/api/client";
import type { ApiResponse } from "@/types/api";
import type {
  AdminAction,
  AdminDashboard,
  AdminUser,
  AdminUserDetail,
  AIConfig,
  AIStatistics,
  AuditLog,
  PageResult,
  UserAction,
  UserActionResult,
} from "@/types/admin";

async function adminRequest<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  try {
    return (await apiFetch<ApiResponse<T>>(path, options)).data;
  } catch (error) {
    if (
      typeof window !== "undefined" &&
      error instanceof ApiError &&
      error.code === "ADMIN_REQUIRED"
    ) {
      window.dispatchEvent(new Event("admin-permission-revoked"));
    }
    throw error;
  }
}
const params = (input: Record<string, string | number | undefined>) => {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(input))
    if (value !== undefined && value !== "") search.set(key, String(value));
  return search.toString();
};
export const getAdminDashboard = () =>
  adminRequest<AdminDashboard>("/admin/dashboard");
export const getAdminUsers = (query: {
  page: number;
  page_size: number;
  keyword?: string;
  status?: "ACTIVE" | "DISABLED";
}) => adminRequest<PageResult<AdminUser>>(`/admin/users?${params(query)}`);
export const getAdminUser = (id: number) =>
  adminRequest<AdminUserDetail>(`/admin/users/${id}`);
export const actOnAdminUser = (
  id: number,
  action: UserAction,
  reason: string,
) =>
  adminRequest<UserActionResult>(
    `/admin/users/${id}/${{ BAN_USER: "ban", UNBAN_USER: "unban", REVOKE_SESSIONS: "revoke-sessions" }[action]}`,
    { method: "POST", body: JSON.stringify({ reason }) },
  );
export const getAdminAIStatistics = () =>
  adminRequest<AIStatistics>("/admin/ai/statistics");
export const getAdminAIConfig = () =>
  adminRequest<AIConfig>("/admin/ai/config");
export const updateAdminAIConfig = (
  body: Partial<
    Pick<AIConfig, "enabled" | "user_daily_limit" | "global_daily_limit">
  > & { reason: string },
) =>
  adminRequest<AIConfig>("/admin/ai/config", {
    method: "PATCH",
    body: JSON.stringify(body),
  });
export const getAdminAudit = (query: {
  page: number;
  page_size: number;
  action?: AdminAction;
}) => adminRequest<PageResult<AuditLog>>(`/admin/audit-logs?${params(query)}`);
