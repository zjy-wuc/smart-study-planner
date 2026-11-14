
"use client";

import { useState } from "react";//保存输入内容
import { loginUser, registerUser } from "@/services/auth.service";
import { setTokenPair } from "@/lib/auth/token";
import type { RegisterRequest } from "@/types/auth";
import Link from "next/link";
import { useRouter } from "next/navigation";

export default function RegisterForm() {
  const router = useRouter();
  const [formData, setFormData] = useState<RegisterRequest>({
    username: "",
    password: "",
    nickname: "",
  });

  const [message, setMessage] = useState("");
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);
  const [registered, setRegistered] = useState(false);

  async function handleSubmit(
    event: React.FormEvent<HTMLFormElement>
  ) {
    event.preventDefault();//阻止表单默认提交行为

    setLoading(true);
    setSuccess(false);
    setMessage("");//清空上一次提示信息

    try {
      await registerUser(formData);
      setRegistered(true);

      try {
        const result = await loginUser({
          username: formData.username,
          password: formData.password,
        });
        setTokenPair(result.data.access_token, result.data.refresh_token);
        setSuccess(true);
        setMessage("注册成功，正在进入个人中心...");
        router.replace("/profile");
      } catch {
        setMessage("注册成功，但自动登录失败，请点击下方返回登录。");
      }
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "注册失败"
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
        <h1>学习计划管理系统</h1>
      </div>

      <div className="login-field">
        <label htmlFor="register-username">用户名</label>
        <input
          id="register-username"
          name="username"
          autoComplete="username"
          placeholder="请输入用户名"
          value={formData.username}//输入框显示的内容
          onChange={(event) =>//监听用户输入
            setFormData({
              ...formData,
              username: event.target.value,
            })
          }
          required
        />
      </div>

      <div className="login-field">
        <label htmlFor="register-password">密码</label>
        <input
          id="register-password"
          name="password"
          autoComplete="new-password"
          placeholder="请输入密码"
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

      <div className="login-field">
        <label htmlFor="register-nickname">昵称</label>
        <input
          id="register-nickname"
          name="nickname"
          autoComplete="nickname"
          placeholder="请输入昵称"
          value={formData.nickname}
          onChange={(event) =>
            setFormData({
              ...formData,
              nickname: event.target.value,
            })
          }
          required
        />
      </div>

      {message && <p className={success ? "login-message login-message-success" : "login-message"} role={success ? "status" : "alert"}>{message}</p>}
      <button className="login-submit" type="submit" disabled={loading || registered}>
        {loading ? "注册中..." : registered ? "注册成功" : "注册"}
      </button>

      <p className="login-register">已有账号？ <Link href="/login">返回登录</Link></p>
    </form>
  );
}
