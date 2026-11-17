"use client";

import { messages } from "@/messages";

import Link from "next/link";

import { useTodayTasks } from "@/hooks/useTodayTasks";
import { TaskActionCard } from "@/components/tasks/TaskActionCard";
import { WorkspaceIcon } from "@/components/ui/WorkspaceIcon";


export default function TodayTasksPage() {
  const {
    tasks,
    loading,
    error,
    reload,
  } = useTodayTasks();

  return (
    <div className="workspace-page">
      <div className="workspace-page-heading">
        <div>
          <h1 className="text-2xl font-bold">{messages.navigation.today}</h1>

          <p className="mt-2 text-slate-500">{messages.tasks.todayDescription}</p>
        </div>

        <button
          type="button"
          onClick={reload}
          disabled={loading}
          className="workspace-button workspace-button--secondary"
        >
          <WorkspaceIcon name="refresh" />{messages.tasks.refresh}</button>
      </div>

      {loading ? (
        <p role="status" className="workspace-loading">{messages.tasks.loadingToday}</p>
      ) : error ? (
        <div role="alert" className="workspace-feedback workspace-feedback--error">
          <p className="text-red-700">{messages.tasks.fetchError(error)}
          </p>

          <button
            type="button"
            onClick={reload}
            className="workspace-text-link"
          >{messages.common.tryAgain}</button>
        </div>
      ) : tasks.length === 0 ? (
        <div className="workspace-empty-state">
          <p>{messages.tasks.emptyToday}</p>

          <Link
            href="/plans"
            className="workspace-text-link"
          >{messages.plans.viewMyPlans}</Link>
        </div>
      ) : (
        <div className="workspace-task-cards">
          <p className="workspace-summary-note">{messages.tasks.todayCount(tasks.length)}</p>

          {tasks.map((task) => (
            <TaskActionCard
              key={task.id}
              task={task}
              onChanged={reload}
            />
          ))}
        </div>
      )}

      <Link href="/" className="workspace-text-link workspace-back-link">{messages.navigation.backHome}</Link>
    </div>
  );
}
