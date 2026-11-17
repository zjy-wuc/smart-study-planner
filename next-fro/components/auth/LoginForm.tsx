"use client";

import { messages } from "@/messages";

import { useLayoutEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { loginUser } from "@/services/auth.service";
import type { LoginRequest } from "@/types/auth";
import { setTokenPair } from "@/lib/auth/token";
import Link from "next/link";
import "@/components/css/LoginForm.css";

export default function LoginForm() {
  const router = useRouter();

  const [formData, setFormData] = useState<LoginRequest>({
    username: "",
    password: "",
  });

  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  useLayoutEffect(() => {
    return () => {
      setMessage((current) => current === messages.auth.loginSuccess ? "" : current);
    };
  }, []);

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
setMessage(messages.auth.loginSuccess);

// 4. 跳转到首页
router.replace("/");

  
} catch (error) {
  setMessage(
    error instanceof Error
      ? error.message
      : messages.auth.loginFailed
  );
} finally {
  setLoading(false);
}
  }

  return (
    <form onSubmit={handleSubmit} className="login-form">
      <div className="login-formHeading">
        <svg className="login-book" viewBox="0 0 64 52" fill="none" aria-hidden="true">
          <path d="M32 11C23 3 12 3 4 8v36c9-5 19-4 28 3m0-36c9-8 20-8 28-3v36c-9-5-19-4-28 3m0-36v36" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <h1>{messages.common.appName}</h1>
      </div>

      <div className="login-field">
        <label htmlFor="login-username">{messages.auth.username}</label>
        <input
          id="login-username"
          name="username"
          autoComplete="username"
          placeholder={messages.auth.usernamePlaceholder}
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

      <div className="login-field">
        <label htmlFor="login-password">{messages.auth.password}</label>
        <input
          id="login-password"
          name="password"
          autoComplete="current-password"
          placeholder={messages.auth.passwordPlaceholder}
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

      {message && (
        <p
          className={message === messages.auth.loginSuccess ? "login-message login-message-success" : "login-message"}
          role={message === messages.auth.loginSuccess ? "status" : "alert"}
        >
          {message}
        </p>
      )}
      <button className="login-submit" type="submit" disabled={loading}>
        {loading ? messages.auth.loggingIn : messages.auth.login}
      </button>
      <p className="login-register"><Link href="/register">{messages.auth.newUser}</Link></p>
      <p className="login-motto">{messages.auth.motto}</p>
    </form>
  );
}
