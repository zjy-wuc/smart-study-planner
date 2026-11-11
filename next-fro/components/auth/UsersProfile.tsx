"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { getCurrentUser } from "@/services/auth.service";
import { logoutUser } from "@/services/auth.service";
import type { User } from "@/types/auth";

export default function UserProfile() {
  const router = useRouter();

  const [user, setUser] = useState<User | null>(null);
  const [message, setMessage] = useState("正在获取用户信息...");
//在挂载时执行一次，获取当前登录用户的信息
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

    loadUser();//执行函数
  }, []);//在挂载时执行一次，获取当前登录用户的信息

  // 退出登录
  async function handleLogout() {
  try {
    await logoutUser();
  } catch {
    // 即使后端请求失败，也允许用户退出当前页面
  } finally {
    router.replace("/login");
  }
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