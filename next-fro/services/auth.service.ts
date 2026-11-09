import { apiFetch } from "@/lib/api/client";
import type {
  ApiResponse,
  RegisterData,
  RegisterRequest,
} from "@/types/auth";

// 调用后端 POST /users 注册用户
export function registerUser(payload: RegisterRequest) {
  return apiFetch<ApiResponse<RegisterData>>("/users", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
