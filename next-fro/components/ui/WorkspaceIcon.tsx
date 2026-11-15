import type { ReactNode } from "react";

export type WorkspaceIconName =
  | "book"
  | "home"
  | "calendar"
  | "tasks"
  | "user"
  | "search"
  | "refresh"
  | "steps"
  | "arrow"
  | "plus";

const paths: Record<WorkspaceIconName, ReactNode> = {
  book: <path d="M12 6C9 3.5 5.5 3.5 3 5v13c3-1.5 6-1.5 9 1.5M12 6c3-2.5 6.5-2.5 9-1v13c-3-1.5-6-1.5-9 1.5M12 6v13.5" />,
  home: <><path d="m3 10 9-7 9 7v10H3z" /><path d="M9 20v-7h6v7" /></>,
  calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M7 3v4M17 3v4M3 10h18M8 14h2M14 14h2" /></>,
  tasks: <><rect x="4" y="3" width="16" height="18" rx="2" /><path d="m8 9 1 1 2-2M14 9h3m-9 6 1 1 2-2M14 15h3" /></>,
  user: <><circle cx="12" cy="7.5" r="3.5" /><path d="M5 21v-2a7 7 0 0 1 14 0v2z" /></>,
  search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></>,
  refresh: <><path d="M20 7v5h-5M4 17v-5h5" /><path d="M6 6a8 8 0 0 1 14 6M18 18a8 8 0 0 1-14-6" /></>,
  steps: <><rect x="3" y="3" width="7" height="6" rx="1.5" /><rect x="14" y="15" width="7" height="6" rx="1.5" /><path d="M6.5 9v9H14M10 6h7.5v9" /></>,
  arrow: <path d="m9 5 7 7-7 7" />,
  plus: <path d="M12 5v14M5 12h14" />,
};

/** 仅用于展示，沿用个人中心的线性图标风格。 */
export function WorkspaceIcon({ name }: { name: WorkspaceIconName }) {
  return (
    <svg
      className="workspace-icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}
