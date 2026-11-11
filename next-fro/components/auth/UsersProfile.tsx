"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { getCurrentUser,
        logoutAllSessions,
         logoutUser  
 } from "@/services/auth.service";

import type { User } from "@/types/auth";

import {
  ApiError,
} from "@/lib/api/client";

import {
  removeTokenPair,
} from "@/lib/auth/token";



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
  if (error instanceof ApiError && error.status === 401) {
    removeTokenPair();
    router.replace("/login");
    return;
  }

  setMessage(
    error instanceof Error
      ? error.message
      : "获取用户信息失败",
  );
}
    }

    loadUser();//执行函数
  }, [router]);//在挂载时执行一次，获取当前登录用户的信息

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


// 退出当前账号的全部登录会话
async function handleLogoutAll() {
  try {
    await logoutAllSessions();

    router.replace("/login");
  } catch {
    

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
      <button onClick={handleLogoutAll}>
  退出全部设备
</button>
    </main>
  );
}




