
"use client";

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
    : "操作失败，请重试";
}

const statusNames = {
  PENDING: "待完成",
  IN_PROGRESS: "进行中",
  COMPLETED: "已完成",
  OVERDUE: "已逾期",
  ENDED: "已停止",
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
      setError("只能修改符合条件的未来待执行任务");
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
        throw new Error("任务已发生变化，不能直接修改");
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
        setError("BOOLEAN 任务内容不能为空");
        return;
      }

      payload = { content };
    } else {
      const value = editText.trim();

      if (!/^\d+$/.test(value)) {
        setError("目标数量必须是非负整数");
        return;
      }

      const quantity = Number(value);

      if (!Number.isSafeInteger(quantity)) {
        setError("数量超出前端安全整数范围");
        return;
      }

      payload = { target_quantity: quantity };
    }

    setBusy(true);
    setError(null);

    try {
      await updateFutureTask(editing.id, payload);

      setEditing(null);
      setNotice("未来任务修改成功");
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
      `确定删除 ${task.task_date} 的「${task.step_name}」吗？\n\n` +
      "删除会影响当前有效任务和计划完成率。" +
      "已有打卡记录、顺延历史不会因此自动恢复。",
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

      setNotice("任务已删除");
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
          <h2 className="text-xl font-semibold">
            计划全部任务
          </h2>
          <p className="text-sm text-slate-500">
            按日期查看、修改未来任务与浏览打卡记录
          </p>
        </div>

        <button
          type="button"
          onClick={reload}
          disabled={loading || busy}
        >
          刷新
        </button>
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
        <p>正在获取任务...</p>
      ) : tasks.length === 0 ? (
        <p>当前计划暂无有效每日任务。</p>
      ) : (
        <div className="space-y-6">
          <p>共 {tasks.length} 条有效任务</p>

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
                            累计 {task.actual_quantity}
                            {" / 原始目标 "}
                            {task.target_quantity ?? 0}
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
                          >
                            修改未来任务
                          </button>
                        )}

                        <button
                          type="button"
                          onClick={() =>
                            void toggleHistory(task.id)
                          }
                          className="text-blue-700"
                        >
                          {historyTaskId === task.id
                            ? "收起历史"
                            : "打卡历史"}
                        </button>

                        {planStatus === "ACTIVE" && (
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() =>
                              void handleDelete(task)
                            }
                            className="text-red-700"
                          >
                            删除
                          </button>
                        )}
                      </div>
                    </div>

                    {historyTaskId === task.id && (
                      <div className="mt-3 border-t pt-3">
                        {historyLoading ? (
                          <p>正在获取历史...</p>
                        ) : historyError ? (
                          <p role="alert">{historyError}</p>
                        ) : records.length === 0 ? (
                          <p>暂无打卡记录</p>
                        ) : (
                          <ul className="space-y-2">
                            {records.map((record) => (
                              <li key={record.id} className="text-sm">
                                {record.event_type ===
                                "BOOLEAN_COMPLETE"
                                  ? "完成打卡"
                                  : `累计提交：${record.recorded_value}`}
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
          <h3 className="font-semibold">
            修改未来任务：{editing.step_name}
          </h3>

          <p className="text-sm">
            日期：{editing.task_date}
          </p>

          <label htmlFor="future-edit" className="block">
            {editing.task_type === "BOOLEAN"
              ? "任务内容"
              : "新的目标数量"}
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

          <p className="text-sm text-slate-500">
            NUMERIC 新目标不能小于已经承接的顺延数量。
            具体限制由后端验证。
          </p>

          <div className="flex gap-3">
            <button
              type="button"
              disabled={busy}
              onClick={() => void saveEdit()}
              className="text-blue-700"
            >
              保存修改
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => setEditing(null)}
            >
              取消
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
