
"use client";

import Link from "next/link";

import { useTodayTasks } from "@/hooks/useTodayTasks";
import { TaskActionCard } from "@/components/tasks/TaskActionCard";


export default function TodayTasksPage() {
  const {
    tasks,
    loading,
    error,
    reload,
  } = useTodayTasks();

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
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
          className="rounded border px-4 py-2 disabled:opacity-50"
        >
          刷新任务
        </button>
      </div>

      {loading ? (
        <p role="status">正在获取今日任务...</p>
      ) : error ? (
        <div role="alert" className="space-y-3">
          <p className="text-red-700">
            获取任务失败：{error}
          </p>

          <button
            type="button"
            onClick={reload}
            className="text-blue-700"
          >
            重新尝试
          </button>
        </div>
      ) : tasks.length === 0 ? (
        <div className="rounded border bg-white p-6">
          <p>今天没有需要展示的任务。</p>

          <Link
            href="/plans"
            className="mt-3 inline-block text-blue-700"
          >
            查看我的学习计划
          </Link>
        </div>
      ) : (
        <div className="space-y-4">
          <p className="text-sm text-slate-500">
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

      <Link href="/" className="inline-block text-blue-700">
        返回首页
      </Link>
    </div>
  );
}
