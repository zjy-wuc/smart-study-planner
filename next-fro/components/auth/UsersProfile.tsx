"use client";

import { messages } from "@/messages";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { getCurrentUser, logoutAllSessions, logoutUser } from "@/services/auth.service";
import { ApiError } from "@/lib/api/client";
import { removeTokenPair } from "@/lib/auth/token";
import type { User } from "@/types/auth";
import { WorkspaceIcon as Icon } from "@/components/ui/WorkspaceIcon";
import { ScrollPositionManager } from "@/components/common/ScrollPositionManager";
import { LandscapeScene } from "@/components/common/LandscapeScene";
import "@/components/css/Profile.css";

export default function UserProfile() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [message, setMessage] = useState(messages.profile.loading);
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
        setMessage(error instanceof TypeError ? messages.profile.serverUnavailable : error instanceof Error ? error.message : messages.profile.loadFailed);
      }
    }
    loadUser();
  }, [router]);

  async function handleLogout(all: boolean) {
    if (all && !window.confirm(messages.profile.logoutAllConfirm)) return;
    setLoggingOut(true);
    try {
      if (all) await logoutAllSessions();
      else await logoutUser();
    } catch {
      // 服务不可用时也清理本地登录状态。
    } finally {
      setLoggingOut(false);
      router.replace("/login");
    }
  }

  const displayName = user?.nickname || user?.username || messages.profile.defaultName;
  const avatar = Array.from(displayName)[0] || messages.profile.defaultAvatar;

  return (
    <div className="profile-app">
      <ScrollPositionManager />
      <header className="profile-header">
        <div className="profile-brand">
          <span className="profile-brand-icon"><Icon name="book" /></span>
          <strong>{messages.common.appName}</strong>
          <span className="profile-brand-tagline">{messages.navigation.tagline}</span>
        </div>
        <div className="profile-header-user">
          <span className="profile-avatar-small">{avatar}</span>
          <span className="profile-header-name" title={user ? displayName : messages.navigation.profile}>
            {user ? displayName : messages.navigation.profile}
          </span>
        </div>
      </header>
      <div className="profile-layout">
        <aside className="profile-sidebar">
          <nav aria-label={messages.navigation.mainLabel}>
            <div className="profile-sidebar-label">{messages.navigation.spaceLabel}</div>
            <Link className="profile-nav-item" href="/">
              <Icon name="home" />{messages.navigation.home}</Link>
            <Link className="profile-nav-item" href="/plans">
              <Icon name="calendar" />{messages.navigation.plans}</Link>
            <Link className="profile-nav-item" href="/task/today">
              <Icon name="tasks" />{messages.navigation.today}</Link>
            <Link className="profile-nav-item" href="/history">
              <Icon name="book" />{messages.navigation.history}</Link>
            <Link className="profile-nav-item" href="/statistics">
              <Icon name="calendar" />{messages.navigation.statistics}</Link>
            <div className="profile-nav-divider" />
            <div className="profile-sidebar-label">{messages.navigation.accountLabel}</div>
            <Link
  className="profile-nav-item"
  href="/reminders"
>
  <Icon name="bell" />
  {messages.navigation.reminders}
</Link>
            <Link className="profile-nav-item profile-nav-active" href="/profile" aria-current="page">
              <Icon name="user" />{messages.navigation.profile}</Link>
          </nav>
          <div className="profile-sidebar-note">{messages.navigation.mottoFirstLine}<br />{messages.navigation.mottoSecondLine}<span aria-hidden="true">✦</span>
          </div>
        </aside>
        <main className="profile-main">
          <LandscapeScene variant="ocean" />
          <div className="profile-heading">
            <h1>{messages.navigation.profile}</h1>
            <p>{messages.profile.subtitle}</p>
          </div>
          <section className="profile-banner" aria-label={messages.profile.overviewLabel}>
            <div className="profile-avatar">{avatar}</div>
            <div className="profile-welcome">
              <span>{messages.profile.welcome}</span>
              <h2>{user ? displayName : messages.profile.yourSpace}</h2>
              <p>{messages.profile.bannerMotto}</p>
            </div>
          </section>
          {message && <p className="profile-status" role="status">{message}</p>}
          <div className="profile-cards">
            <section className="profile-card">
              <div className="profile-card-title">
                <span className="profile-card-icon"><Icon name="user" /></span>
                <div><h2>{messages.profile.basicInfo}</h2><p>{messages.profile.accountInfo}</p></div>
              </div>
              <dl className="profile-details">
                <div><dt>{messages.auth.username}</dt><dd>{user?.username ?? "—"}</dd></div>
                <div><dt>{messages.auth.nickname}</dt><dd>{user ? user.nickname || messages.profile.notSet : "—"}</dd></div>
                <div><dt>{messages.profile.userId}</dt><dd>{user?.id ?? "—"}</dd></div>
              </dl>
            </section>
            <section className="profile-card">
              <div className="profile-card-title">
                <span className="profile-card-icon"><Icon name="shield" /></span>
                <div><h2>{messages.profile.security}</h2><p>{messages.profile.sessionDescription}</p></div>
              </div>
              <div className="profile-actions">
                <button type="button" onClick={() => handleLogout(false)} disabled={loggingOut}>
                  <span className="profile-action-icon"><Icon name="screen" /></span>
                  <span><strong>{messages.profile.logoutCurrent}</strong><small>{messages.profile.logoutCurrentDescription}</small></span>
                  <span className="profile-arrow" aria-hidden="true">›</span>
                </button>
                <button type="button" onClick={() => handleLogout(true)} disabled={loggingOut}>
                  <span className="profile-action-icon"><Icon name="power" /></span>
                  <span><strong>{messages.profile.logoutAll}</strong><small>{messages.profile.logoutAllDescription}</small></span>
                  <span className="profile-arrow" aria-hidden="true">›</span>
                </button>
              </div>
            </section>
          </div>
          <p className="profile-bottom">{messages.profile.footerMotto}<span>✦</span></p>
        </main>
      </div>
    </div>
  );
}
