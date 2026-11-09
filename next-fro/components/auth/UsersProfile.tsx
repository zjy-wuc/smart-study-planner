"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { getCurrentUser } from "@/services/auth.service";
import { removeAccessToken } from "@/lib/auth/token";

import type { User } from "@/types/auth";

export default function UserProfile() {
  const router = useRouter();

  const [user, setUser] = useState<User | null>(null);
  const [message, setMessage] = useState("正在获取用户信息...");

  useEffect(() => {
    async function loadUser() {
      try {
        const result = await getCurrentUser();

        setUser(result.data);
        setMessage("获取用户信息成功");
      } catch (error) {
        setMessage(
          error instanceof Error
            ? error.message
            : "获取用户信息失败"
        );
      }
    }

    loadUser();
  }, []);

  // 退出登录
  function handleLogout() {
    removeAccessToken();

    router.replace("/login");
  }

  return (
    <main>
      <h2>当前用户信息</h2>

      <p>{message}</p>

      {user && (
        <div>
          <p>用户 ID：{user.id}</p>
          <p>用户名：{user.username}</p>
          <p>昵称：{user.nickname}</p>
        </div>
      )}

      <button onClick={handleLogout}>
        退出登录
      </button>
    </main>
  );
}