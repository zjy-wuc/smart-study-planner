"use client";

import Link from "next/link";
import { messages } from "@/messages";
import { SaveSuccessDialog } from "@/components/ui/SaveSuccessDialog";

import { useEffect, useState, useSyncExternalStore } from "react";
import { Ellipsis, RefreshCw, Trash2 } from "lucide-react";

import {
  listPlanTasks,
  getTask,
  updateFutureTask,
  deleteTask,
  getTaskRecords,
} from "@/services/tasks.service";

import { ApiError } from "@/lib/api/client";
import { getBusinessToday } from "@/lib/plans/business-date";
import { isSettledNumericTask } from "@/lib/tasks/today-presentation";

import type { PlanStatus } from "@/types/plan";
import type {
  PlanTask,
  DailyTask,
  StudyRecord,
  ActiveTaskUpdate,
} from "@/types/task";
import "@/components/css/PlanTasks.css";

type Props = {
  planId: number;
  planStatus: PlanStatus;
};

function errorText(error: unknown): string {
  if (
    error instanceof ApiError &&
    error.validationIssues.length > 0
  ) {
    return error.validationIssues
      .map((issue) => issue.msg)
      .join("；");
  }

  return error instanceof Error
    ? error.message
    : messages.common.operationFailedRetry;
}

const statusNames = {
  PENDING: messages.tasks.statusPending,
  IN_PROGRESS: messages.common.statusActive,
  COMPLETED: messages.tasks.statusCompleted,
  OVERDUE: messages.tasks.statusOverdue,
  ENDED: messages.tasks.statusStopped,
};

export function PlanTasksPanel({
  planId,
  planStatus,
}: Props) {

  const [tasks, setTasks] = useState<PlanTask[]>([]);
  const today = useSyncExternalStore(() => () => {}, getBusinessToday, () => null);

  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);

  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);

  // 编辑未来任务
  const [editing, setEditing] = useState<DailyTask | null>(null);
  const [editText, setEditText] = useState("");

  // 查看历史
  const [historyTaskId, setHistoryTaskId] =
    useState<number | null>(null);
  const [records, setRecords] = useState<StudyRecord[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] =
    useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);

      try {
        const result = await listPlanTasks(planId);

        if (!cancelled) {
          setTasks(result);
        }
      } catch (err) {
        if (!cancelled) {
          setTasks([]);
          setError(errorText(err));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void load();

    return () => {
      cancelled = true;
    };
  }, [planId, revision]);

  function reload() {
    setRevision((value) => value + 1);
  }

  function handleError(err: unknown) {
    setError(errorText(err));
  }

  async function beginEdit(task: PlanTask) {
    if (busy || today === null) {
      return;
    }

    if (
      planStatus !== "ACTIVE" ||
      task.task_date <= today ||
      task.status !== "PENDING"
    ) {
      setError(messages.tasks.futureOnly);
      return;
    }

    setBusy(true);
    setError(null);
    setNotice(null);

    try {
      // 列表是轻量结构，先查询完整任务详情
      const detail = await getTask(task.id);

      if (
        detail.status !== "PENDING" ||
        detail.is_rolled_over ||
        detail.rollover_out_quantity > 0
      ) {
        throw new Error(messages.tasks.changedCannotEdit);
      }

      setEditing(detail);

      setEditText(
        detail.task_type === "BOOLEAN"
          ? detail.content ?? ""
          : String(detail.target_quantity ?? 0),
      );
    } catch (err) {
      handleError(err);
    } finally {
      setBusy(false);
    }
  }

  async function saveEdit() {
    if (!editing || busy) {
      return;
    }

    let payload: ActiveTaskUpdate;

    if (editing.task_type === "BOOLEAN") {
      const content = editText.trim();

      if (!content) {
        setError(messages.tasks.booleanContentRequired);
        return;
      }

      payload = { content };
    } else {
      const value = editText.trim();

      if (!/^\d+$/.test(value)) {
        setError(messages.tasks.targetIntegerRequired);
        return;
      }

      const quantity = Number(value);

      if (!Number.isSafeInteger(quantity)) {
        setError(messages.tasks.quantityTooLarge);
        return;
      }

      payload = { target_quantity: quantity };
    }

    setBusy(true);
    setError(null);

    try {
      await updateFutureTask(editing.id, payload);

      setEditing(null);
      setSaveMessage(messages.tasks.futureUpdated);
      reload();
    } catch (err) {
      handleError(err);
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(task: PlanTask) {
    if (busy || planStatus !== "ACTIVE") {
      return;
    }

    const confirmed = window.confirm(
      messages.tasks.deleteConfirm(task.task_date, task.step_name),
    );

    if (!confirmed) {
      return;
    }

    setBusy(true);
    setError(null);
    setNotice(null);

    try {
      await deleteTask(task.id);

      if (editing?.id === task.id) {
        setEditing(null);
      }

      if (historyTaskId === task.id) {
        setHistoryTaskId(null);
        setRecords([]);
      }

      setNotice(messages.tasks.deleted);
      reload();
    } catch (err) {
      handleError(err);
    } finally {
      setBusy(false);
    }
  }

  async function toggleHistory(taskId: number) {
    if (historyTaskId === taskId) {
      setHistoryTaskId(null);
      return;
    }

    setHistoryTaskId(taskId);
    setRecords([]);
    setHistoryError(null);
    setHistoryLoading(true);

    try {
      const result = await getTaskRecords(taskId);
      setRecords(result);
    } catch (err) {
      setHistoryError(errorText(err));
    } finally {
      setHistoryLoading(false);
    }
  }

  // 按任务日期分组，方便查看全周期
  const groupedTasks = Object.entries(
    tasks.reduce<Record<string, PlanTask[]>>(
      (groups, task) => {
        (groups[task.task_date] ??= []).push(task);
        return groups;
      },
      {},
    ),
  ).sort(([a], [b]) => a.localeCompare(b));

  return (
    <section id="plan-tasks" className="plan-task-panel plan-detail-anchor">
      <header className="plan-task-header">
        <div>
          <h2>{messages.tasks.planTitle}</h2>
          <p>{messages.tasks.planDescription}</p>
        </div>
        <div className="plan-task-header-actions">
          <Link href={`/history?plan_id=${planId}`}>{messages.history.viewFull}</Link>
          <button
            type="button"
            onClick={reload}
            disabled={loading || busy}
          ><RefreshCw size={16} aria-hidden="true" />{messages.common.refresh}</button>
        </div>
      </header>

      {error && (
        <p role="alert" className="plan-task-error">
          {error}
        </p>
      )}

      {notice && (
        <p role="status" className="plan-task-notice">
          {notice}
        </p>
      )}

      {loading ? (
        <p className="plan-task-empty">{messages.tasks.loading}</p>
      ) : tasks.length === 0 ? (
        <p className="plan-task-empty">{messages.tasks.emptyPlan}</p>
      ) : (
        <div className="plan-task-body">
          <p className="plan-task-count">{messages.tasks.validCount(tasks.length)}</p>

          {groupedTasks.map(([date, dayTasks]) => (
            <section key={date} className="plan-task-day">
              <header><h3>{date}</h3><span>{messages.plans.previewTaskCount(dayTasks.length)}</span></header>
              <div className="plan-task-list">
              {dayTasks.map((task) => {
                const canEdit =
                  planStatus === "ACTIVE" &&
                  today !== null &&
                  task.task_date > today &&
                  task.status === "PENDING";

                return (
                  <article key={task.id} className="plan-task-row">
                    <div className="plan-task-row-main">
                      <div className="plan-task-identity">
                        <strong>{task.content || task.step_name}</strong>
                        <small>{task.content && task.content !== task.step_name && <>{task.step_name} · </>}{task.task_type === "NUMERIC" ? messages.tasks.numericType : messages.tasks.booleanType}</small>
                      </div>
                      <span className="plan-task-status" data-status={isSettledNumericTask(task) ? "SETTLED" : task.status}>
                        {isSettledNumericTask(task) ? messages.plans.previewSettled : statusNames[task.status]}
                      </span>
                      <div className="plan-task-measure">
                        {task.task_type === "NUMERIC" && <>
                          <span>{messages.tasks.originalQuantitySummary(task.actual_quantity, task.target_quantity ?? 0)}</span>
                          <span className="plan-task-progress" aria-hidden="true"><span style={{ width: `${task.target_quantity && task.target_quantity > 0 ? Math.min(100, task.actual_quantity / task.target_quantity * 100) : 0}%` }} /></span>
                        </>}
                      </div>
                      <div className="plan-task-actions">
                        {canEdit && (
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => void beginEdit(task)}
                          >{messages.tasks.editFuture}</button>
                        )}

                        <button
                          type="button"
                          aria-expanded={historyTaskId === task.id}
                          aria-controls={historyTaskId === task.id ? `plan-task-history-${task.id}` : undefined}
                          onClick={() =>
                            void toggleHistory(task.id)
                          }
                        >
                          {historyTaskId === task.id
                            ? messages.history.collapse
                            : messages.history.view}
                        </button>

                        {planStatus === "ACTIVE" && (
                          <details className="plan-task-more">
                            <summary aria-label={messages.plans.moreActions}><Ellipsis size={18} aria-hidden="true" /></summary>
                            <button type="button" disabled={busy} onClick={(event) => {
                              event.currentTarget.closest("details")?.removeAttribute("open");
                              void handleDelete(task);
                            }}><Trash2 size={15} aria-hidden="true" />{messages.common.delete}</button>
                          </details>
                        )}
                      </div>
                    </div>

                    {historyTaskId === task.id && (
                      <div id={`plan-task-history-${task.id}`} className="plan-task-history">
                        {historyLoading ? (
                          <p>{messages.history.fetching}</p>
                        ) : historyError ? (
                          <p role="alert">{historyError}</p>
                        ) : records.length === 0 ? (
                          <p>{messages.history.emptyRecords}</p>
                        ) : (
                          <ul>
                            {records.map((record) => (
                              <li key={record.id}>
                                {record.event_type ===
                                "BOOLEAN_COMPLETE"
                                  ? messages.tasks.booleanCheckin
                                  : messages.tasks.submittedTotal(record.recorded_value)}
                                {" · "}
                                {record.recorded_at}
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    )}
                    {editing?.id === task.id && (
                      <div className="plan-task-edit">
                        <h4>{messages.tasks.editFutureTitle(editing.step_name)}</h4>
                        <label htmlFor={`future-edit-${task.id}`}>{editing.task_type === "BOOLEAN" ? messages.tasks.content : messages.tasks.newTarget}</label>
                        <input id={`future-edit-${task.id}`} type="text" value={editText} disabled={busy} onChange={(event) => setEditText(event.target.value)} />
                        {editing.task_type === "NUMERIC" && <p>{messages.tasks.minimumTargetHint}</p>}
                        <div>
                          <button type="button" disabled={busy} onClick={() => void saveEdit()}>{messages.common.saveChanges}</button>
                          <button type="button" disabled={busy} onClick={() => setEditing(null)}>{messages.common.cancel}</button>
                        </div>
                      </div>
                    )}
                  </article>
                );
              })}
              </div>
            </section>
          ))}
        </div>
      )}
      <SaveSuccessDialog message={saveMessage} onClose={() => setSaveMessage(null)} />
    </section>
  );
}
