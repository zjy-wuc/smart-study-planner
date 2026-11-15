
import { Suspense, type ReactNode } from "react";

import { WorkspaceShell } from
  "@/components/layout/WorkspaceShell";

export default function WorkspaceLayout({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <Suspense
      fallback={
        <div role="status" className="p-6">
          正在加载工作台...
        </div>
      }
    >
      <WorkspaceShell>
        {children}
      </WorkspaceShell>
    </Suspense>
  );
}
