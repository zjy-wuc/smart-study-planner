import { apiFetch } from "@/lib/api/client";
import { announceAuthChange, authEpoch, sameAuthEpoch, withAuthLock } from "@/lib/auth/coordinator";
import { clearAccessToken, getAuthGeneration, setAccessToken } from "@/lib/auth/token";
import type {
  ApiResponse,
  EmailChangeRequest,
  EmailCodePurpose,
  EmailLoginRequest,
  LoginRequest,
  LoginResponse,
  LoginSession,
  PasswordChangeRequest,
  PasswordResetRequest,
  RegisterRequest,
  SessionListResponse,
  User,
} from "@/types/auth";

function rememberLogin(
  result: ApiResponse<LoginResponse>,
): ApiResponse<LoginResponse> & { authEpoch: string } {
  const epoch = announceAuthChange("login");
  setAccessToken(result.data.access_token, epoch);
  return { ...result, authEpoch: epoch };
}

export function sendEmailCode(email: string, purpose: EmailCodePurpose) {
  return apiFetch<ApiResponse<null>>("/auth/email-code", {
    method: "POST",
    body: JSON.stringify({ email, purpose }),
    skipAuthRefresh:
      purpose !== "CHANGE_EMAIL_OLD" && purpose !== "CHANGE_EMAIL_NEW",
  });
}

export function registerUser(payload: RegisterRequest) {
  return withAuthLock(async () =>
    rememberLogin(
      await apiFetch<ApiResponse<LoginResponse>>("/users", {
        method: "POST",
        body: JSON.stringify(payload),
        skipAuthRefresh: true,
      }),
    ),
  );
}

export function loginUser(data: LoginRequest) {
  return withAuthLock(async () => {
    const form = new URLSearchParams({
      username: data.username,
      password: data.password,
    });
    return rememberLogin(
      await apiFetch<ApiResponse<LoginResponse>>("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: form,
        skipAuthRefresh: true,
      }),
    );
  });
}

export function loginWithEmail(data: EmailLoginRequest) {
  return withAuthLock(async () =>
    rememberLogin(
      await apiFetch<ApiResponse<LoginResponse>>("/auth/login/email", {
        method: "POST",
        body: JSON.stringify(data),
        skipAuthRefresh: true,
      }),
    ),
  );
}

export function getCurrentUser() {
  return apiFetch<ApiResponse<User>>("/users/me");
}

export function resetPassword(data: PasswordResetRequest) {
  return withAuthLock(() =>
    apiFetch<ApiResponse<null>>("/auth/password/reset", {
      method: "POST",
      body: JSON.stringify(data),
      skipAuthRefresh: true,
    }),
  );
}

export function changePassword(data: PasswordChangeRequest) {
  return apiFetch<ApiResponse<null>>("/auth/password/change", {
    method: "POST",
    body: JSON.stringify(data),
    userActivity: true,
  });
}

export function changeEmail(data: EmailChangeRequest) {
  return apiFetch<ApiResponse<User>>("/auth/email/change", {
    method: "POST",
    body: JSON.stringify(data),
    userActivity: true,
  });
}

export function updateNickname(id: number, nickname: string) {
  return apiFetch<ApiResponse<null>>(`/users/${id}`, {
    method: "PUT",
    body: JSON.stringify({ nickname }),
    userActivity: true,
  });
}

export function uploadAvatar(file: File) {
  const form = new FormData();
  form.set("file", file);
  return apiFetch<ApiResponse<{ avatar_url: string }>>("/users/me/avatar", {
    method: "POST",
    body: form,
    userActivity: true,
  });
}

export function deleteAvatar() {
  return apiFetch<ApiResponse<{ avatar_url: null }>>("/users/me/avatar", {
    method: "DELETE",
    userActivity: true,
  });
}

export function listSessions(page = 1, pageSize = 20) {
  return apiFetch<ApiResponse<SessionListResponse>>(
    `/auth/sessions?page=${page}&page_size=${pageSize}`,
  );
}

export function currentSession() {
  return apiFetch<ApiResponse<LoginSession>>("/auth/sessions/current");
}

export function revokeSession(familyId: string, password: string) {
  return apiFetch<ApiResponse<null>>(`/auth/sessions/${familyId}/revoke`, {
    method: "POST",
    body: JSON.stringify({ password }),
    userActivity: true,
  });
}

export function revokeOtherSessions(password: string) {
  return apiFetch<ApiResponse<{ revoked_count: number }>>(
    "/auth/sessions/revoke-others",
    {
      method: "POST",
      body: JSON.stringify({ password }),
      userActivity: true,
    },
  );
}

export function logoutUser() {
  return withCurrentSessionLock(async () => {
    const result = await apiFetch<ApiResponse<{ session_revoked: boolean }>>(
      "/auth/logout",
      { method: "POST", skipAuthRefresh: true },
    );
    if (result.data.session_revoked) {
      clearAccessToken();
      announceAuthChange("logout");
    }
    return result;
  });
}

export function logoutAllSessions(password: string) {
  return withCurrentSessionLock(async () => {
    const result = await apiFetch<ApiResponse<{ revoked_count: number }>>(
      "/auth/logout-all",
      {
        method: "POST",
        body: JSON.stringify({ password }),
        userActivity: true,
        skipAuthRefresh: true,
      },
    );
    clearAccessToken();
    announceAuthChange("logout");
    return result;
  });
}

async function withCurrentSessionLock<T>(work: () => Promise<T>): Promise<T> {
  const epoch = authEpoch();
  const generation = getAuthGeneration();
  // 可能需要的 Access 刷新先在锁外完成；锁内请求禁止隐式刷新。
  await getCurrentUser();
  if (!sameAuthEpoch(epoch) || getAuthGeneration() !== generation)
    throw new Error("登录状态已变化，请重试");
  return withAuthLock(async () => {
    if (!sameAuthEpoch(epoch) || getAuthGeneration() !== generation)
      throw new Error("登录状态已变化，请重试");
    return work();
  });
}
