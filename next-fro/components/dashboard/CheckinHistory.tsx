"use client";

import { messages } from "@/messages";

import { useState } from "react";
import { getTaskRecords } from "@/services/tasks.service";
import type { DailyTask, StudyRecord } from "@/types/task";

function HistoryItem({ task }: { task: DailyTask }) {
  const [open, setOpen] = useState(false);
  const [records, setRecords] = useState<StudyRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function toggle() {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    setLoading(true);
    setError("");
    try {
      setRecords(await getTaskRecords(task.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : messages.history.loadFailed);
    } finally {
      setLoading(false);
    }
  }

  return (
    <li className="dashboard-history-item">
      <div className="dashboard-history-heading">
        <span>{task.content || task.step_name} <small>· {task.step_name}</small></span>
        <button type="button" className="workspace-text-link" onClick={() => void toggle()} aria-expanded={open}>
          {open ? messages.history.collapse : messages.history.view}
        </button>
      </div>
      {open && (loading ? <p role="status">{messages.history.loadingCompact}</p> : error ? <p role="alert">{messages.history.collapseRetry(error)}</p> : records.length === 0 ? <p>{messages.history.emptyRecords}</p> : (
        <ul className="dashboard-history-records">{records.map((record) => (
          <li key={record.id}>{record.event_type === "BOOLEAN_COMPLETE" ? messages.tasks.booleanCheckin : messages.tasks.recordedTotal(record.recorded_value ?? 0)} <span>{record.recorded_at}</span></li>
        ))}</ul>
      ))}
    </li>
  );
}

export function CheckinHistory({ tasks }: { tasks: DailyTask[] }) {
  return (
    <section className="workspace-panel dashboard-history" aria-labelledby="history-heading">
      <div className="workspace-section-heading"><div className="workspace-section-title"><div><h2 id="history-heading">{messages.navigation.history}</h2><p>{messages.history.todayDescription}</p></div></div></div>
      {tasks.length === 0 ? <p className="workspace-empty-state">{messages.history.emptyToday}</p> : <ul>{tasks.map((task) => <HistoryItem key={task.id} task={task} />)}</ul>}
    </section>
  );
}
