"use client";

import { messages } from "@/messages";
import { ReminderNotice } from
  "@/components/reminders/ReminderNotice";


import {
  createContext,
  Fragment,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import Link from "next/link";
import { Menu, X } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";

import { getAccessToken } from "@/lib/auth/token";
import { ScrollPositionManager } from "@/components/common/ScrollPositionManager";

import {
  WorkspaceIcon,
  type WorkspaceIconName,
} from "@/components/ui/WorkspaceIcon";

import "@/components/css/Workspace.css";
import "@/components/css/WorkspaceRefresh.css";

import {
  ReminderSettingsProvider,
} from "@/components/reminders/ReminderSettingsProvider";


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
  { href: "/", label: messages.navigation.workspace, icon: "home" },
  { href: "/task/today", label: messages.navigation.today, icon: "tasks" },
  { href: "/focus", label: messages.navigation.focus, icon: "timer" },
  { href: "/plans", label: messages.navigation.plans, icon: "calendar" },
  { href: "/knowledge", label: messages.knowledge.title, icon: "book" },
  { href: "/history", label: messages.navigation.history, icon: "book" },

  // V2.1 新增：学习统计中心
  { href: "/statistics", label: messages.navigation.statistics, icon: "calendar" },

  { href: "/reminders", label: messages.navigation.reminders, icon: "bell" },
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
  const [navigationOpen, setNavigationOpen] = useState(false);
  const section = pathname.split("/").filter(Boolean)[0] ?? "home";
  const currentPage = navigation.find((item) =>
    pathname === item.href || (item.href !== "/" && pathname.startsWith(`${item.href}/`)),
  );


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
  <ReminderSettingsProvider>
    <WorkspaceSearchContext.Provider
      value={{ search, setSearch }}
    >
      <ScrollPositionManager />
    

<ReminderNotice />


      <div className="workspace-app workspace-refresh" data-home={pathname === "/"} data-section={section}>
        <header className="workspace-header">
          <div className="workspace-breadcrumb">
            <button
              type="button"
              className="workspace-menu-toggle"
              aria-label={messages.navigation.toggleMenu}
              aria-controls="workspace-navigation"
              aria-expanded={navigationOpen}
              onClick={() => setNavigationOpen((open) => !open)}
            >
              {navigationOpen ? <X size={20} /> : <Menu size={20} />}
            </button>
            <WorkspaceIcon name="home" />
            <span aria-hidden="true">/</span>
            <strong>{currentPage?.label}</strong>
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
          <aside
            className={`workspace-sidebar${navigationOpen ? " is-open" : ""}`}
            id="workspace-navigation"
            onKeyDown={(event) => {
              if (event.key === "Escape") setNavigationOpen(false);
            }}
          >
            <Link href="/" className="workspace-brand" onClick={() => setNavigationOpen(false)}>
              <span className="workspace-brand-icon"><WorkspaceIcon name="book" /></span>
              <span><strong>{messages.common.appName}</strong><small>{messages.navigation.tagline}</small></span>
            </Link>
            <nav
              aria-label={messages.navigation.mainLabel}
              className="workspace-nav"
            >
              <div className="workspace-sidebar-label">{messages.navigation.dailyGroup}</div>

              {navigation.map((item) => {
                const active =
                  pathname === item.href ||
                  (
                    item.href !== "/" &&
                    pathname.startsWith(`${item.href}/`)
                  );

                return (
                  <Fragment key={item.href}>
                    {item.href === "/history" && (
                      <div className="workspace-sidebar-label workspace-review-label">{messages.navigation.reviewGroup}</div>
                    )}
                    {item.href === "/reminders" && (
                      <>
                        <div className="workspace-nav-divider" />

                        <div className="workspace-sidebar-label">{messages.navigation.accountLabel}</div>
                      </>
                    )}

                    <Link
                      href={item.href}
                      onClick={() => setNavigationOpen(false)}
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
  </ReminderSettingsProvider>
);
}
