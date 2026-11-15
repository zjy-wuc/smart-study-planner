
"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getAccessToken } from "@/lib/auth/token";
import { WorkspaceIcon, type WorkspaceIconName } from "@/components/ui/WorkspaceIcon";
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

          <div>
            {pathname === "/" && (
              <div className="workspace-search-field">
                <WorkspaceIcon name="search" />
              <input
                type="search"
                aria-label="搜索学习计划"
                placeholder="搜索计划名称..."
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                className="workspace-search"
              />
              </div>
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
