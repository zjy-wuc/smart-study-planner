
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  createContext,
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

const navigation = [
  { href: "/", label: "首页" },
  { href: "/plans", label: "我的计划" },
  { href: "/tasks/today", label: "今日任务" },
  { href: "/profile", label: "个人中心" },
];

export function WorkspaceShell({
  children,
}: {
  children: ReactNode;
}) {
  const pathname = usePathname();

  const [search, setSearch] = useState("");

  return (
    <WorkspaceSearchContext.Provider
      value={{ search, setSearch }}
    >
      <div className="flex min-h-screen flex-col bg-slate-50 text-slate-900">
        <header className="flex min-h-16 items-center justify-between gap-4 border-b border-slate-200 bg-white px-6">
          <Link href="/" className="font-semibold text-blue-700">
            学习计划管理系统
          </Link>

          <div className="flex items-center gap-4">
            {pathname === "/" && (
              <input
                type="search"
                aria-label="搜索学习计划"
                placeholder="搜索计划名称..."
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                className="w-48 rounded-lg border border-slate-300 px-3 py-2 sm:w-64"
              />
            )}

            <Link href="/profile" className="font-medium">
              个人中心
            </Link>
          </div>
        </header>

        <div className="flex flex-1">
          <aside className="w-48 shrink-0 border-r border-slate-200 bg-white p-4 sm:w-56">
            <nav aria-label="主导航" className="space-y-2">
              {navigation.map((item) => {
                const active =
                  pathname === item.href ||
                  (
                    item.href !== "/" &&
                    pathname.startsWith(`${item.href}/`)
                  );

                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    className={[
                      "block rounded-lg px-3 py-3",
                      active
                        ? "bg-blue-50 font-medium text-blue-700"
                        : "text-slate-700 hover:bg-slate-100",
                    ].join(" ")}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </nav>
          </aside>

          <main className="min-w-0 flex-1 p-5 sm:p-8">
            {children}
          </main>
        </div>
      </div>
    </WorkspaceSearchContext.Provider>
  );
}
