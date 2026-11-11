import { apiFetch } from "@/lib/api/client";
import { getRefreshToken, removeTokenPair } from "@/lib/auth/token";
import type {
  ApiResponse,
  RegisterData,
  RegisterRequest,
  LoginRequest,
  LoginResponse,
  RefreshRequest,
  User,
} from "@/types/auth";



// 调用后端 POST /users 注册用户
export function registerUser(payload: RegisterRequest) {
  return apiFetch<ApiResponse<RegisterData>>("/users", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// 调用后端 POST /auth/login 登录用户
export async function loginUser(
  data: LoginRequest
): Promise<ApiResponse<LoginResponse>> {
  const formData = new URLSearchParams();// 构建表单数据,因为login接口接受URL类型的数据，用了OAuth2PasswordRequestForm格式接收

  formData.append("username", data.username);
  formData.append("password", data.password);

  return apiFetch<ApiResponse<LoginResponse>>(
    "/auth/login",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: formData,
    }
  );
}


// 获取当前登录用户的信息
export async function getCurrentUser(): Promise<ApiResponse<User>> {
  return apiFetch<ApiResponse<User>>("/users/me");
}



// 调用后端 POST /auth/logout 退出当前会话
export async function logoutUser(): Promise<void> {
  const refreshToken = getRefreshToken();

  try {
    // 有 Refresh Token 才请求后端撤销会话
    if (refreshToken) {
      await apiFetch<ApiResponse<null>>(
        "/auth/logout",
        {
          method: "POST",
          body: JSON.stringify({
            refresh_token: refreshToken,
          } satisfies RefreshRequest),
        },
      );
    }
  } finally {
    // 无论后端请求成功还是失败，都清理本地双 Token
    removeTokenPair();
  }
}