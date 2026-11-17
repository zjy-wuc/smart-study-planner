"use client";

import { messages } from "@/messages";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import {
  listPlanTasks,
  getTask,
  updateFutureTask,
  deleteTask,
  getTaskRecords,
} from "@/services/tasks.service";

import { ApiError } from "@/lib/api/client";
import { getBusinessToday } from "@/lib/plans/business-date";

import type { PlanStatus } from "@/types/plan";
import type {
  PlanTask,
  DailyTask,
  StudyRecord,
  ActiveTaskUpdate,
} from "@/types/task";

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
  const router = useRouter();

  const [tasks, setTasks] = useState<PlanTask[]>([]);
  const [today, setToday] = useState<string | null>(null);

  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);

  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

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
    setToday(getBusinessToday());
  }, []);

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
    if (err instanceof ApiError && err.status === 401) {
      router.replace("/login");
      return;
    }

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
      setNotice(messages.tasks.futureUpdated);
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
    <section className="space-y-5 rounded border p-5">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold">{messages.tasks.planTitle}</h2>
          <p className="text-sm text-slate-500">{messages.tasks.planDescription}</p>
        </div>

        <button
          type="button"
          onClick={reload}
          disabled={loading || busy}
        >{messages.common.refresh}</button>
      </div>

      {error && (
        <p role="alert" className="text-red-700">
          {error}
        </p>
      )}

      {notice && (
        <p role="status" className="text-green-700">
          {notice}
        </p>
      )}

      {loading ? (
        <p>{messages.tasks.loading}</p>
      ) : tasks.length === 0 ? (
        <p>{messages.tasks.emptyPlan}</p>
      ) : (
        <div className="space-y-6">
          <p>{messages.tasks.validCount(tasks.length)}</p>

          {groupedTasks.map(([date, dayTasks]) => (
            <section key={date} className="space-y-3">
              <h3 className="font-semibold">{date}</h3>

              {dayTasks.map((task) => {
                const canEdit =
                  planStatus === "ACTIVE" &&
                  today !== null &&
                  task.task_date > today &&
                  task.status === "PENDING";

                return (
                  <article
                    key={task.id}
                    className="rounded border p-4"
                  >
                    <div className="flex flex-wrap justify-between gap-3">
                      <div>
                        <p className="font-medium">
                          {task.content || task.step_name}
                        </p>
                        <p className="text-sm text-slate-500">
                          {task.step_name}
                          {" · "}
                          {task.task_type}
                        </p>
                        <p className="text-sm">
                          {statusNames[task.status]}
                        </p>

                        {task.task_type === "NUMERIC" && (
                          <p className="text-sm">
                            {messages.tasks.originalQuantitySummary(task.actual_quantity, task.target_quantity ?? 0)}
                          </p>
                        )}
                      </div>

                      <div className="flex flex-wrap gap-3 text-sm">
                        {canEdit && (
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => void beginEdit(task)}
                            className="text-blue-700"
                          >{messages.tasks.editFuture}</button>
                        )}

                        <button
                          type="button"
                          onClick={() =>
                            void toggleHistory(task.id)
                          }
                          className="text-blue-700"
                        >
                          {historyTaskId === task.id
                            ? messages.history.collapse
                            : messages.navigation.history}
                        </button>

                        {planStatus === "ACTIVE" && (
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() =>
                              void handleDelete(task)
                            }
                            className="text-red-700"
                          >{messages.common.delete}</button>
                        )}
                      </div>
                    </div>

                    {historyTaskId === task.id && (
                      <div className="mt-3 border-t pt-3">
                        {historyLoading ? (
                          <p>{messages.history.fetching}</p>
                        ) : historyError ? (
                          <p role="alert">{historyError}</p>
                        ) : records.length === 0 ? (
                          <p>{messages.history.emptyRecords}</p>
                        ) : (
                          <ul className="space-y-2">
                            {records.map((record) => (
                              <li key={record.id} className="text-sm">
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
                  </article>
                );
              })}
            </section>
          ))}
        </div>
      )}

      {editing && (
        <div className="space-y-3 rounded border p-4">
          <h3 className="font-semibold">{messages.tasks.editFutureTitle(editing.step_name)}
          </h3>

          <p className="text-sm">{messages.tasks.dateText(editing.task_date)}
          </p>

          <label htmlFor="future-edit" className="block">
            {editing.task_type === "BOOLEAN"
              ? messages.tasks.content
              : messages.tasks.newTarget}
          </label>

          <input
            id="future-edit"
            type="text"
            value={editText}
            disabled={busy}
            onChange={(event) =>
              setEditText(event.target.value)
            }
            className="w-full rounded border p-2"
          />

          <p className="text-sm text-slate-500">{messages.tasks.minimumTargetHint}</p>

          <div className="flex gap-3">
            <button
              type="button"
              disabled={busy}
              onClick={() => void saveEdit()}
              className="text-blue-700"
            >{messages.common.saveChanges}</button>
            <button
              type="button"
              disabled={busy}
              onClick={() => setEditing(null)}
            >{messages.common.cancel}</button>
          </div>
        </div>
      )}
    </section>
  );
}
