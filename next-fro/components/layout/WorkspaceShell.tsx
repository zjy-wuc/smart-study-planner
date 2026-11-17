"use client";

import { messages } from "@/messages";

import {
  createContext,
  Fragment,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { getAccessToken } from "@/lib/auth/token";
import { ScrollPositionManager } from "@/components/common/ScrollPositionManager";

import {
  WorkspaceIcon,
  type WorkspaceIconName,
} from "@/components/ui/WorkspaceIcon";

import "@/components/css/Workspace.css";


type WorkspaceSearchContextValue = {
  search: string;
  setSearch: (value: string) => void;
};

const WorkspaceSearchContext =
  createContext<WorkspaceSearchContextValue | null>(null);


export function useWorkspaceSearch() {
  const context = useContext(WorkspaceSearchContext);

  if (!context) {
    throw new Error(
      messages.navigation.searchContextError,
    );
  }

  return context;
}


const navigation: {
  href: string;
  label: string;
  icon: WorkspaceIconName;
}[] = [
  { href: "/", label: messages.navigation.home, icon: "home" },
  { href: "/plans", label: messages.navigation.plans, icon: "calendar" },
  { href: "/task/today", label: messages.navigation.today, icon: "tasks" },
  { href: "/history", label: messages.navigation.history, icon: "book" },

  // V2.1 新增：学习统计中心
  { href: "/statistics", label: messages.navigation.statistics, icon: "calendar" },

  { href: "/profile", label: messages.navigation.profile, icon: "user" },
];


export function WorkspaceShell({
  children,
}: {
  children: ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();

  const [authChecked, setAuthChecked] = useState(false);
  const [search, setSearch] = useState("");


  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }

    setAuthChecked(true);
  }, [router]);


  if (!authChecked) {
    return (
      <p role="status">{messages.auth.checkingSession}</p>
    );
  }


  return (
    <WorkspaceSearchContext.Provider
      value={{ search, setSearch }}
    >
      <ScrollPositionManager />
      <div className="workspace-app">
        <header className="workspace-header">
          <div className="workspace-brand">
            <span className="workspace-brand-icon">
              <WorkspaceIcon name="book" />
            </span>

            <strong>{messages.common.appName}</strong>

            <span className="workspace-brand-tagline">{messages.navigation.tagline}</span>
          </div>

          <div>
            {pathname === "/" && (
              <div className="workspace-search-field">
                <WorkspaceIcon name="search" />

                <input
                  type="search"
                  aria-label={messages.navigation.searchLabel}
                  placeholder={messages.navigation.searchPlaceholder}
                  value={search}
                  onChange={(event) =>
                    setSearch(event.target.value)
                  }
                  className="workspace-search"
                />
              </div>
            )}
          </div>
        </header>


        <div className="workspace-layout">
          <aside className="workspace-sidebar">
            <nav
              aria-label={messages.navigation.mainLabel}
              className="workspace-nav"
            >
              <div className="workspace-sidebar-label">{messages.navigation.spaceLabel}</div>

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

                        <div className="workspace-sidebar-label">{messages.navigation.accountLabel}</div>
                      </>
                    )}

                    <Link
                      href={item.href}
                      aria-current={
                        active ? "page" : undefined
                      }
                      className="workspace-nav-link"
                    >
                      <WorkspaceIcon name={item.icon} />
                      {item.label}
                    </Link>
                  </Fragment>
                );
              })}
            </nav>

            <p className="workspace-sidebar-note">{messages.navigation.mottoFirstLine}<br />{messages.navigation.mottoSecondLine}<span aria-hidden="true">✦</span>
            </p>
          </aside>

          <main className="workspace-main">
            {children}
          </main>
        </div>
      </div>
    </WorkspaceSearchContext.Provider>
  );
}
