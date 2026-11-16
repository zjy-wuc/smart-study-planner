
"use client";

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
          <h1 className="text-2xl font-bold">
            今日任务
          </h1>

          <p className="mt-2 text-slate-500">
            记录实际完成情况，合理安排未完成任务
          </p>
        </div>

        <button
          type="button"
          onClick={reload}
          disabled={loading}
          className="workspace-button workspace-button--secondary"
        >
          <WorkspaceIcon name="refresh" />
          刷新任务
        </button>
      </div>

      {loading ? (
        <p role="status" className="workspace-loading">正在获取今日任务...</p>
      ) : error ? (
        <div role="alert" className="workspace-feedback workspace-feedback--error">
          <p className="text-red-700">
            获取任务失败：{error}
          </p>

          <button
            type="button"
            onClick={reload}
            className="workspace-text-link"
          >
            重新尝试
          </button>
        </div>
      ) : tasks.length === 0 ? (
        <div className="workspace-empty-state">
          <p>今天没有需要展示的任务。</p>

          <Link
            href="/plans"
            className="workspace-text-link"
          >
            查看我的学习计划
          </Link>
        </div>
      ) : (
        <div className="workspace-task-cards">
          <p className="workspace-summary-note">
            今天共 {tasks.length} 条任务
          </p>

          {tasks.map((task) => (
            <TaskActionCard
              key={task.id}
              task={task}
              onChanged={reload}
            />
          ))}
        </div>
      )}

      <Link href="/" className="workspace-text-link workspace-back-link">
        返回首页
      </Link>
    </div>
  );
}
