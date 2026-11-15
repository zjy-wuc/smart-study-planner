
"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getAccessToken } from "@/lib/auth/token";
import "@/components/css/Workspace.css";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  createContext,
  Fragment,
  useContext,
  useState,
  type ReactNode,
} from "react";

type WorkspaceSearchContextValue = {
  search: string;
  setSearch: (value: string) => void;
};

const WorkspaceSearchContext =
  createContext<WorkspaceSearchContextValue | null>(null);

export function useWorkspaceSearch() {
  const context = useContext(WorkspaceSearchContext);

  if (!context) {
    throw new Error("必须在 WorkspaceShell 内使用搜索状态");
  }

  return context;
}

type WorkspaceIconName = "book" | "home" | "calendar" | "tasks" | "user";

function WorkspaceIcon({ name }: { name: WorkspaceIconName }) {
  const paths: Record<WorkspaceIconName, ReactNode> = {
    book: <><path d="M12 6C9 3.5 5.5 3.5 3 5v13c3-1.5 6-1.5 9 1.5M12 6c3-2.5 6.5-2.5 9-1v13c-3-1.5-6-1.5-9 1.5M12 6v13.5" /></>,
    home: <><path d="m3 10 9-7 9 7v10H3z" /><path d="M9 20v-7h6v7" /></>,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M7 3v4M17 3v4M3 10h18M8 14h2M14 14h2" /></>,
    tasks: <><rect x="4" y="3" width="16" height="18" rx="2" /><path d="m8 9 1 1 2-2M14 9h3m-9 6 1 1 2-2M14 15h3" /></>,
    user: <><circle cx="12" cy="7.5" r="3.5" /><path d="M5 21v-2a7 7 0 0 1 14 0v2z" /></>,
  };

  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {paths[name]}
    </svg>
  );
}

const navigation: { href: string; label: string; icon: WorkspaceIconName }[] = [
  { href: "/", label: "首页", icon: "home" },
  { href: "/plans", label: "我的计划", icon: "calendar" },
  { href: "/task/today", label: "今日任务", icon: "tasks" },
  { href: "/profile", label: "个人中心", icon: "user" },
];

export function WorkspaceShell({
  children,
}: {
  children: ReactNode;
}) {
    const router = useRouter();
const [authChecked, setAuthChecked] = useState(false);

useEffect(() => {
  if (!getAccessToken()) {
    router.replace("/login");
    
    return;
  }

  setAuthChecked(true);
}, [router]);
  const pathname = usePathname();

  const [search, setSearch] = useState("");
if (!authChecked) {
  return <p role="status">正在检查登录状态...</p>;
}
  return (
    <WorkspaceSearchContext.Provider
      value={{ search, setSearch }}
    >
      <div className="workspace-app">
        <header className="workspace-header">
          <div className="workspace-brand">
            <span className="workspace-brand-icon"><WorkspaceIcon name="book" /></span>
            <strong>学习计划管理系统</strong>
            <span className="workspace-brand-tagline">让学习更有计划</span>
          </div>

          <div className="flex items-center gap-4">
            {pathname === "/" && (
              <input
                type="search"
                aria-label="搜索学习计划"
                placeholder="搜索计划名称..."
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                className="workspace-search"
              />
            )}

          </div>
        </header>

        <div className="workspace-layout">
          <aside className="workspace-sidebar">
            <nav aria-label="主导航" className="workspace-nav">
              <div className="workspace-sidebar-label">学习空间</div>
              {navigation.map((item) => {
                const active =
                  pathname === item.href ||
                  (
                    item.href !== "/" &&
                    pathname.startsWith(`${item.href}/`)
                  );

                return (
                  <Fragment key={item.href}>
                    {item.href === "/profile" && (
                      <>
                        <div className="workspace-nav-divider" />
                        <div className="workspace-sidebar-label">账户</div>
                      </>
                    )}
                    <Link
                      href={item.href}
                      aria-current={active ? "page" : undefined}
                      className="workspace-nav-link"
                    >
                      <WorkspaceIcon name={item.icon} />
                      {item.label}
                    </Link>
                  </Fragment>
                );
              })}
            </nav>
            <p className="workspace-sidebar-note">每一天的努力，<br />都在带你靠近目标。<span aria-hidden="true">✦</span></p>
          </aside>

          <main className="workspace-main">
            {children}
          </main>
        </div>
      </div>
    </WorkspaceSearchContext.Provider>
  );
}
