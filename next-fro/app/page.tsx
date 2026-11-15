import Dashboard from "@/components/dashboard/Dashboard";
import { WorkspaceShell } from "@/components/layout/WorkspaceShell";

export default function HomePage() {
  return (
    <WorkspaceShell>
      <Dashboard />
    </WorkspaceShell>
  );
}
