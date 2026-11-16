"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError } from "@/lib/api/client";
import { completeBooleanTask, updateNumericTask } from "@/services/tasks.service";
import { useDailyCheckin } from "@/hooks/useDailyCheckin";
import type { DailyTask } from "@/types/task";

const statusLabels = {
  PENDING: "待完成", IN_PROGRESS: "进行中", COMPLETED: "已完成",
  OVERDUE: "已逾期", ENDED: "已停止",
};

function TodayTaskRow({ task, onChanged }: { task: DailyTask; onChanged: () => void }) {
  const router = useRouter();
  const [quantity, setQuantity] = useState(String(task.actual_quantity));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const rolledOver = task.is_rolled_over || !!task.has_rollover || task.rollover_out_quantity > 0;
  const canCheckin = task.plan_status === "ACTIVE" && !rolledOver &&
    ["PENDING", "IN_PROGRESS", "OVERDUE"].includes(task.status);
  const daily = useDailyCheckin(task.id, task.task_type === "NUMERIC" && canCheckin);
  const label = task.task_type === "NUMERIC" && ["PENDING", "IN_PROGRESS"].includes(task.display_status)
    ? "未完成" : statusLabels[task.display_status];

  async function checkin(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !canCheckin || (task.task_type === "NUMERIC" && daily.state !== "available")) return;
    const text = quantity.trim();
    const value = Number(text);
    if (task.task_type === "NUMERIC" && (!/^\d+$/.test(text) || !Number.isSafeInteger(value))) {
      setError("请输入安全范围内的非负整数");
      return;
    }
    setBusy(true);
    setError("");
    try {
      if (task.task_type === "BOOLEAN") await completeBooleanTask(task.id);
      else await updateNumericTask(task.id, value);
      daily.markDone();
      onChanged();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        router.replace("/login");
      } else {
        setError(err instanceof Error ? err.message : "打卡失败，请重试");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="workspace-task-item dashboard-task" data-status={task.display_status}>
      <div className="dashboard-task-main">
        <p className="workspace-task-title">{task.content || task.step_name}</p>
        <p className="workspace-task-meta">{task.step_name} · {task.task_date}</p>
        {task.task_type === "NUMERIC" && <p className="workspace-task-quantity">累计完成 {task.actual_quantity} / 目标 {task.effective_target_quantity ?? task.target_quantity ?? 0}</p>}
        {rolledOver && <p className="workspace-rollover-label">已发生顺延</p>}
        {error && <p role="alert" className="dashboard-checkin-error">{error}</p>}
      </div>
      <div className="dashboard-task-actions">
        <span className="workspace-task-status" data-status={task.display_status}>{label}</span>
        {canCheckin && daily.state !== "done" && <form className="dashboard-checkin" onSubmit={(event) => void checkin(event)}>
          {task.task_type === "NUMERIC" && <input aria-label={`${task.content || task.step_name}累计完成数量`} type="text" inputMode="numeric" value={quantity} onChange={(event) => setQuantity(event.target.value)} disabled={busy || daily.state !== "available"} />}
          <button type="submit" disabled={busy || (task.task_type === "NUMERIC" && daily.state !== "available")}>{busy ? "保存中…" : daily.state === "loading" ? "正在确认…" : "打卡"}</button>
          {daily.state === "error" && task.task_type === "NUMERIC" && <button type="button" onClick={daily.retry}>确认失败，重试</button>}
        </form>}
        {!rolledOver && (daily.state === "done" || task.status === "COMPLETED") && <span className="checkin-success-text">坚持就是胜利</span>}
      </div>
    </li>
  );
}

export function TodayTaskList({ tasks, onChanged }: { tasks: DailyTask[]; onChanged: () => void }) {
  if (!tasks.length) return <p className="workspace-empty-state">今天暂无安排的任务</p>;
  return <ul className="workspace-task-list">{tasks.map((task) => <TodayTaskRow key={task.id} task={task} onChanged={onChanged} />)}</ul>;
}
