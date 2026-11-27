"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard,
  Users,
  Sparkles,
  ScrollText,
  ArrowLeft,
  LogOut,
  Menu,
  X,
  BookOpen,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { getCurrentUser, logoutUser } from "@/services/auth.service";
import { ApiError } from "@/lib/api/client";
import { messages } from "@/messages";
import "@/components/css/Admin.css";

const m = messages.admin;
const links = [
  { href: "/admin", label: m.overview, icon: LayoutDashboard },
  { href: "/admin/users", label: m.users, icon: Users },
  { href: "/admin/ai", label: m.ai, icon: Sparkles },
  { href: "/admin/audit", label: m.audit, icon: ScrollText },
];

export function AdminShell({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [verifiedUserId, setVerifiedUserId] = useState<number | null>(null);
  const [denied, setDenied] = useState(false);
  const [error, setError] = useState("");
  const [navOpen, setNavOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    if (auth.status === "unauthenticated") router.replace("/login");
  }, [auth.status, router]);

  useEffect(() => {
    if (auth.status !== "authenticated" || !auth.user) return;
    let live = true;
    queueMicrotask(() => {
      if (live) {
        setVerifiedUserId(null);
        setDenied(false);
        setError("");
      }
    });
    void getCurrentUser()
      .then(({ data }) => {
        if (!live) return;
        auth.updateUser(data);
        if (data.role !== "ADMIN") {
          if (auth.user?.role === "ADMIN")
            router.replace("/?admin_access=revoked");
          else setDenied(true);
        } else setVerifiedUserId(data.id);
      })
      .catch((err: unknown) => {
        if (!live) return;
        if (err instanceof ApiError && err.code === "ADMIN_REQUIRED")
          router.replace("/?admin_access=revoked");
        else
          setError(
            err instanceof Error
              ? err.message
              : messages.common.operationFailedRetry,
          );
      });
    return () => {
      live = false;
    };
    // 只在进入管理空间、切换账号或主动重试时向服务端核对身份。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auth.status, auth.user?.id, revision, router]);

  useEffect(() => {
    const revoked = () => {
      setVerifiedUserId(null);
      router.replace("/?admin_access=revoked");
    };
    window.addEventListener("admin-permission-revoked", revoked);
    return () =>
      window.removeEventListener("admin-permission-revoked", revoked);
  }, [router]);

  async function logout() {
    setMenuOpen(false);
    try {
      const result = await logoutUser();
      if (!result.data.session_revoked)
        throw new Error(messages.profile.logoutUnconfirmed);
      auth.clear();
      router.replace("/login");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : messages.common.operationFailedRetry,
      );
    }
  }

  if (auth.status === "temporary-error")
    return (
      <div className="admin-gate" role="alert">
        <p>{messages.auth.restoreFailed}</p>
        <p>{messages.auth.restoreLoginHint}</p>
        <button onClick={auth.retry}>{m.retry}</button>
        <Link href="/login">{messages.auth.backToLogin}</Link>
      </div>
    );
  if (auth.status !== "authenticated" || !auth.user)
    return (
      <div className="admin-gate" role="status">
        {messages.auth.checkingSession}
      </div>
    );
  if (denied)
    return (
      <div className="admin-gate">
        <strong>403 · {m.forbidden}</strong>
        <p>{m.forbiddenHelp}</p>
        <Link href="/">{m.back}</Link>
      </div>
    );
  if (error)
    return (
      <div className="admin-gate" role="alert">
        <p>{error}</p>
        <button onClick={() => setRevision((value) => value + 1)}>
          {m.retry}
        </button>
        <Link href="/">{m.back}</Link>
      </div>
    );
  if (verifiedUserId !== auth.user.id || auth.user.role !== "ADMIN")
    return (
      <div className="admin-gate" role="status">
        {m.loading}
      </div>
    );

  const current = links.find((link) => link.href === pathname) ?? links[0];
  return (
    <div className="admin-shell">
      <aside className={`admin-sidebar${navOpen ? " is-open" : ""}`}>
        <Link
          href="/admin"
          className="admin-brand"
          onClick={() => setNavOpen(false)}
        >
          <span className="admin-brand-mark">
            <BookOpen size={21} />
          </span>
          <span>{m.brand}</span>
        </Link>
        <nav aria-label={m.brand}>
          {links.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              aria-current={pathname === href ? "page" : undefined}
              onClick={() => setNavOpen(false)}
            >
              <Icon size={18} />
              {label}
            </Link>
          ))}
        </nav>
        <Link className="admin-back" href="/">
          <ArrowLeft size={17} />
          {m.back}
        </Link>
      </aside>
      <div className="admin-body">
        <header className="admin-header">
          <button
            className="admin-menu-toggle"
            aria-label={messages.navigation.toggleMenu}
            onClick={() => setNavOpen((open) => !open)}
          >
            {navOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
          <div className="admin-crumb">
            <Link href="/admin">{m.brand}</Link>
            <span>/</span>
            <strong>{current.label}</strong>
          </div>
          <div className="admin-account">
            <button
              onClick={() => setMenuOpen((open) => !open)}
              aria-expanded={menuOpen}
            >
              <span className="admin-avatar">
                {auth.user.nickname?.[0] ?? auth.user.username[0]}
              </span>
              <span>{auth.user.username}</span>
              <b>{m.badge}</b>
            </button>
            {menuOpen && (
              <button className="admin-logout" onClick={() => void logout()}>
                <LogOut size={16} />
                {m.logout}
              </button>
            )}
          </div>
        </header>
        <main className="admin-main">{children}</main>
      </div>
    </div>
  );
}
