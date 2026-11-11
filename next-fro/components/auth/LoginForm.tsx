
"use client";

import { useState } from "react";
import { loginUser } from "@/services/auth.service";
import type { LoginRequest } from "@/types/auth";
import { setTokenPair } from "@/lib/auth/token";

export default function LoginForm() {
  const [formData, setFormData] = useState<LoginRequest>({
    username: "",
    password: "",
  });

  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(
    event: React.FormEvent<HTMLFormElement>
  ) {
    event.preventDefault();

    setLoading(true);
    setMessage("");

    try {
  const result = await loginUser(formData);
// 1. 获取后端返回的双 Token
const accessToken = result.data.access_token;
const refreshToken = result.data.refresh_token;

// 2. 同时保存双 Token
setTokenPair(accessToken, refreshToken);

// 3. 更新页面提示
setMessage("登录成功！");

  
} catch (error) {
  setMessage(
    error instanceof Error
      ? error.message
      : "登录失败"
  );
} finally {
  setLoading(false);
}
  }

  return (
    <form onSubmit={handleSubmit}>
      <h2>用户登录</h2>

      <div>
        <label>用户名</label>
        <input
          value={formData.username}
          onChange={(event) =>
            setFormData({
              ...formData,
              username: event.target.value,
            })
          }
          required
        />
      </div>

      <div>
        <label>密码</label>
        <input
          type="password"
          value={formData.password}
          onChange={(event) =>
            setFormData({
              ...formData,
              password: event.target.value,
            })
          }
          required
        />
      </div>

      <button type="submit" disabled={loading}>
        {loading ? "登录中..." : "登录"}
      </button>

      {message && <p>{message}</p>}
    </form>
  );
}
