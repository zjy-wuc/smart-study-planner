//给多个页面套上统一的工作区布局，让不同页面共享相同的外层结构。
import type { ReactNode } from "react";

import { WorkspaceShell } from "@/components/layout/WorkspaceShell";

export default function WorkspaceLayout({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <WorkspaceShell>
      {children}
    </WorkspaceShell>
  );
}
