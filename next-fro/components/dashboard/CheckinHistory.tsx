"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError } from "@/lib/api/client";
import { getTaskRecords } from "@/services/tasks.service";
import type { DailyTask, StudyRecord } from "@/types/task";

function HistoryItem({ task }: { task: DailyTask }) {
  const router = useRouter();
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
      if (err instanceof ApiError && err.status === 401) router.replace("/login");
      else setError(err instanceof Error ? err.message : "历史记录加载失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <li className="dashboard-history-item">
      <div className="dashboard-history-heading">
        <span>{task.content || task.step_name} <small>· {task.step_name}</small></span>
        <button type="button" className="workspace-text-link" onClick={() => void toggle()} aria-expanded={open}>
          {open ? "收起历史" : "查看历史"}
        </button>
      </div>
      {open && (loading ? <p role="status">正在加载历史…</p> : error ? <p role="alert">{error}，请收起后重试。</p> : records.length === 0 ? <p>暂无打卡记录</p> : (
        <ul className="dashboard-history-records">{records.map((record) => (
          <li key={record.id}>{record.event_type === "BOOLEAN_COMPLETE" ? "完成打卡" : `累计完成 ${record.recorded_value ?? 0}`} <span>{record.recorded_at}</span></li>
        ))}</ul>
      ))}
    </li>
  );
}

export function CheckinHistory({ tasks }: { tasks: DailyTask[] }) {
  return (
    <section className="workspace-panel dashboard-history" aria-labelledby="history-heading">
      <div className="workspace-section-heading"><div className="workspace-section-title"><div><h2 id="history-heading">打卡历史</h2><p>查看今日任务的打卡记录</p></div></div></div>
      {tasks.length === 0 ? <p className="workspace-empty-state">今天暂无任务记录</p> : <ul>{tasks.map((task) => <HistoryItem key={task.id} task={task} />)}</ul>}
    </section>
  );
}
