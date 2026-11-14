"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { getCurrentUser, logoutAllSessions, logoutUser } from "@/services/auth.service";
import { ApiError } from "@/lib/api/client";
import { removeTokenPair } from "@/lib/auth/token";
import type { User } from "@/types/auth";
import "@/components/css/Profile.css";

function Icon({ name }: { name: "book" | "home" | "calendar" | "user" | "shield" | "screen" | "power" }) {
  const paths: Record<typeof name, React.ReactNode> = {
    book: <><path d="M12 6C9 3.5 5.5 3.5 3 5v13c3-1.5 6-1.5 9 1.5M12 6c3-2.5 6.5-2.5 9-1v13c-3-1.5-6-1.5-9 1.5M12 6v13.5" /></>,
    home: <><path d="m3 10 9-7 9 7v10H3z" /><path d="M9 20v-7h6v7" /></>,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M7 3v4M17 3v4M3 10h18M8 14h2M14 14h2" /></>,
    user: <><circle cx="12" cy="7.5" r="3.5" /><path d="M5 21v-2a7 7 0 0 1 14 0v2z" /></>,
    shield: <><path d="M12 3 20 6v5c0 5-3.5 8-8 10-4.5-2-8-5-8-10V6z" /><path d="m9 12 2 2 4-4" /></>,
    screen: <><rect x="3" y="4" width="18" height="13" rx="1.5" /><path d="M8 21h8M12 17v4" /></>,
    power: <><path d="M12 2v10M7 5a9 9 0 1 0 10 0" /></>,
  };
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

export default function UserProfile() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [message, setMessage] = useState("正在获取用户信息...");
  const [loggingOut, setLoggingOut] = useState(false);

  useEffect(() => {
    async function loadUser() {
      try {
        const result = await getCurrentUser();
        setUser(result.data);
        setMessage("");
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
          removeTokenPair();
          router.replace("/login");
          return;
        }
        setMessage(error instanceof TypeError ? "无法连接服务器，请检查后端服务是否启动。" : error instanceof Error ? error.message : "获取用户信息失败");
      }
    }
    loadUser();
  }, [router]);

  async function handleLogout(all: boolean) {
    if (all && !window.confirm("确定退出该账号在所有设备上的登录吗？")) return;
    setLoggingOut(true);
    try {
      if (all) await logoutAllSessions();
      else await logoutUser();
    } catch {
      // 服务不可用时也清理本地登录状态。
    } finally {
      router.replace("/login");
    }
  }

  const displayName = user?.nickname || user?.username || "学习者";
  const avatar = Array.from(displayName)[0] || "学";

  return (
    <div className="profile-app">
      <header className="profile-header">
        <div className="profile-brand"><span className="profile-brand-icon"><Icon name="book" /></span><strong>学习计划管理系统</strong><span className="profile-brand-tagline">让学习更有计划</span></div>
        <div className="profile-header-user"><span className="profile-avatar-small">{avatar}</span><span>{user ? displayName : "个人中心"}</span></div>
      </header>
      <div className="profile-layout">
        <aside className="profile-sidebar" aria-label="主导航">
          <div className="profile-sidebar-label">学习空间</div>
          <Link className="profile-nav-item" href="/"><Icon name="home" />首页</Link>
          <span className="profile-nav-item profile-nav-disabled"><Icon name="calendar" />学习计划 <small>即将上线</small></span>
          <div className="profile-nav-divider" />
          <div className="profile-sidebar-label">账户</div>
          <span className="profile-nav-item profile-nav-active" aria-current="page"><Icon name="user" />个人中心</span>
          <div className="profile-sidebar-note">每一天的努力，<br />都在带你靠近目标。<span>✦</span></div>
        </aside>
        <main className="profile-main">
          <div className="profile-heading"><div><p>MY ACCOUNT</p><h1>个人中心</h1><span>管理你的账户信息和登录状态</span></div></div>
          <section className="profile-banner" aria-label="个人资料概览">
            <div className="profile-avatar">{avatar}</div>
            <div className="profile-welcome"><span>欢迎回来</span><h2>{user ? displayName : "你的学习空间"}</h2><p>每一步，都算数。</p></div>
          </section>
          {message && <p className="profile-status" role="status">{message}</p>}
          <div className="profile-cards">
            <section className="profile-card">
              <div className="profile-card-title"><span className="profile-card-icon"><Icon name="user" /></span><div><h2>基本资料</h2><p>你的账户信息</p></div></div>
              <dl className="profile-details">
                <div><dt>用户名</dt><dd>{user?.username ?? "—"}</dd></div>
                <div><dt>昵称</dt><dd>{user ? user.nickname || "未设置" : "—"}</dd></div>
                <div><dt>用户 ID</dt><dd>{user?.id ?? "—"}</dd></div>
              </dl>
            </section>
            <section className="profile-card">
              <div className="profile-card-title"><span className="profile-card-icon"><Icon name="shield" /></span><div><h2>账户安全</h2><p>管理你的登录状态</p></div></div>
              <div className="profile-actions">
                <button type="button" onClick={() => handleLogout(false)} disabled={loggingOut}><span className="profile-action-icon"><Icon name="screen" /></span><span><strong>退出当前设备</strong><small>仅退出此设备上的登录</small></span><span className="profile-arrow">›</span></button>
                <button type="button" onClick={() => handleLogout(true)} disabled={loggingOut}><span className="profile-action-icon"><Icon name="power" /></span><span><strong>退出全部设备</strong><small>退出所有设备上的登录</small></span><span className="profile-arrow">›</span></button>
              </div>
            </section>
          </div>
          <p className="profile-bottom">专注当下，慢慢成长 <span>✦</span></p>
        </main>
      </div>
    </div>
  );
}
