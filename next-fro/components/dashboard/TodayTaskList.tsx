"use client";

import { messages } from "@/messages";

import { useState } from "react";
import { completeBooleanTask, updateNumericTask } from "@/services/tasks.service";
import { useDailyCheckin } from "@/hooks/useDailyCheckin";
import type { DailyTask } from "@/types/task";
import type { Plan } from "@/types/plan";
import { BookOpen, Check, ListTodo } from "lucide-react";

const statusLabels = {
  PENDING: messages.tasks.statusPending, IN_PROGRESS: messages.common.statusActive, COMPLETED: messages.tasks.statusCompleted,
  OVERDUE: messages.tasks.statusOverdue, ENDED: messages.tasks.statusStopped,
};

function TodayTaskRow({ task, planName, onChanged }: { task: DailyTask; planName?: string; onChanged: () => void }) {
  const completionQuantity = task.effective_target_quantity ?? task.target_quantity ?? task.actual_quantity;
  const [quantity, setQuantity] = useState(String(completionQuantity));
  const [quantityEdited, setQuantityEdited] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const rolledOver = task.is_rolled_over || !!task.has_rollover || task.rollover_out_quantity > 0;
  const canCheckin = task.plan_status === "ACTIVE" && !rolledOver &&
    ["PENDING", "IN_PROGRESS", "OVERDUE"].includes(task.status);
  const daily = useDailyCheckin(task.id, task.task_type === "NUMERIC" && canCheckin);
  const label = task.task_type === "NUMERIC" && ["PENDING", "IN_PROGRESS"].includes(task.display_status)
    ? messages.tasks.statusIncomplete : statusLabels[task.display_status];

  async function checkin(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !canCheckin) return;
    const text = quantity.trim();
    const value = Number(text);
    if (task.task_type === "NUMERIC" && (!/^\d+$/.test(text) || !Number.isSafeInteger(value))) {
      setError(messages.tasks.invalidSafeQuantity);
      return;
    }
    setBusy(true);
    setError("");
    try {
      if (task.task_type === "BOOLEAN") await completeBooleanTask(task.id);
      else await updateNumericTask(task.id, value);
      if (task.task_type === "NUMERIC") {
        daily.markDone();
        setQuantity(String(completionQuantity));
        setQuantityEdited(false);
      }
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : messages.tasks.checkinFailed);
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="workspace-task-item dashboard-task" data-status={task.display_status}>
      <span className="dashboard-task-icon" aria-hidden="true">
        {task.status === "COMPLETED" && !rolledOver ? <Check size={18} /> : task.task_type === "NUMERIC" ? <BookOpen size={18} /> : <ListTodo size={18} />}
      </span>
      <div className="dashboard-task-main">
        <p className="workspace-task-title">{task.content || task.step_name}</p>
        <p className="workspace-task-meta">{planName && <>{planName} / </>}{task.step_name} · {task.task_date}</p>
        {task.task_type === "NUMERIC" && <p className="workspace-task-quantity">{messages.tasks.quantitySummary(task.actual_quantity, task.effective_target_quantity ?? task.target_quantity ?? 0)}</p>}
        {rolledOver && <p className="workspace-rollover-label">{messages.tasks.rolledOver}</p>}
        {error && <p role="alert" className="dashboard-checkin-error">{error}</p>}
      </div>
      <div className="dashboard-task-actions">
        <span className="workspace-task-status" data-status={task.display_status}>{label}</span>
        {task.task_type === "NUMERIC" && canCheckin && daily.state === "done" && <span className="checkin-success-text">{messages.tasks.todayRecorded}</span>}
        {canCheckin && <form className="dashboard-checkin" onSubmit={(event) => void checkin(event)}>
          {task.task_type === "NUMERIC" && <><label className="dashboard-checkin-label" htmlFor={`dashboard-progress-${task.id}`}>{messages.tasks.cumulativeQuantityLabel}</label><input id={`dashboard-progress-${task.id}`} aria-label={messages.tasks.quantityLabel(task.content || task.step_name)} title={messages.tasks.numericCheckinHint} type="text" inputMode="numeric" value={quantity} onChange={(event) => { setQuantity(event.target.value); setQuantityEdited(true); }} disabled={busy} /></>}
          <button type="submit" disabled={busy}>{busy ? messages.common.savingCompact : task.task_type === "NUMERIC" && !quantityEdited ? messages.tasks.completeAll : messages.tasks.checkin}</button>
        </form>}
        {!rolledOver && task.status === "COMPLETED" && <span className="checkin-success-text">{messages.tasks.encouragement}</span>}
      </div>
    </li>
  );
}

export function TodayTaskList({ tasks, plans, onChanged }: { tasks: DailyTask[]; plans: Plan[]; onChanged: () => void }) {
  if (!tasks.length) return <p className="workspace-empty-state">{messages.tasks.noScheduledToday}</p>;
  return <ul className="workspace-task-list">{tasks.map((task) => <TodayTaskRow key={task.id} task={task} planName={plans.find((plan) => plan.id === task.plan_id)?.name} onChanged={onChanged} />)}</ul>;
}
