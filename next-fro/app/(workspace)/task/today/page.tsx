
"use client";

import Link from "next/link";

import { useDashboardData } from "@/hooks/useDashboardData";
import { TodayTaskList } from "@/components/dashboard/TodayTaskList";


export default function TodayTasksPage() {
  const {
    tasks,
    tasksError,
    loading,
    reload,
  } = useDashboardData();

  return (
    <section className="workspace-page space-y-5">
      <div className="workspace-page-heading flex items-center justify-between">
        <h1 className="text-2xl font-bold">
          今日任务
        </h1>

        <button type="button" onClick={reload} className="workspace-button workspace-button--secondary">
          刷新
        </button>
      </div>

      {loading ? (
        <p>正在加载今日任务...</p>
      ) : tasksError ? (
        <p role="alert" className="text-red-600">
          {tasksError}
        </p>
      ) : (
        <div className="workspace-panel rounded-xl border bg-white p-5">
          <TodayTaskList tasks={tasks} />
        </div>
      )}

      <Link href="/" className="workspace-text-link text-blue-700">
        返回首页
      </Link>
    </section>
  );
}
