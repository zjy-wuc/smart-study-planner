
"use client";

import {
  useEffect,
  useState,
} from "react";

import { useRouter } from "next/navigation";

import { ApiError } from "@/lib/api/client";

import {
  completeBooleanTask,
  updateNumericTask,
  rolloverTask,
  getTaskRecords,
} from "@/services/tasks.service";

import type {
  DailyTask,
  StudyRecord,
} from "@/types/task";


type Props = {
  task: DailyTask;
  onChanged: () => void;
};

const statusLabels = {
  PENDING: "待完成",
  IN_PROGRESS: "进行中",
  COMPLETED: "已完成",
  OVERDUE: "已逾期",
  ENDED: "已停止",
};


function getErrorText(error: unknown): string {
  if (
    error instanceof ApiError &&
    error.validationIssues.length > 0
  ) {
    return error.validationIssues
      .map((item) => item.msg)
      .join("；");
  }

  return error instanceof Error
    ? error.message
    : "操作失败，请重试";
}


export function TaskActionCard({
  task,
  onChanged,
}: Props) {
  const router = useRouter();

  const [actualText, setActualText] = useState(
    String(task.actual_quantity),
  );

  const [targetDate, setTargetDate] = useState("");
  const [showRollover, setShowRollover] = useState(false);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [showRecords, setShowRecords] = useState(false);
  const [records, setRecords] = useState<StudyRecord[]>([]);
  const [recordsLoading, setRecordsLoading] = useState(false);
  const [recordsError, setRecordsError] =
    useState<string | null>(null);

  // 后端任务状态更新后，同步累计数量输入框。
  useEffect(() => {
    setActualText(String(task.actual_quantity));
  }, [task.id, task.actual_quantity]);

  const isRolledOver =
    task.is_rolled_over ||
    task.has_rollover === 1 ||
    task.rollover_out_quantity > 0;

  const canOperate =
    task.plan_status === "ACTIVE" &&
    (
      task.status === "PENDING" ||
      task.status === "IN_PROGRESS" ||
      task.status === "OVERDUE"
    ) &&
    !isRolledOver;


  async function refreshRecords() {
    setRecordsLoading(true);
    setRecordsError(null);

    try {
      const result = await getTaskRecords(task.id);
      setRecords(result);
    } catch (err) {
      setRecordsError(getErrorText(err));
    } finally {
      setRecordsLoading(false);
    }
  }


  async function runAction(
    action: () => Promise<unknown>,
    successMessage: string,
  ) {
    if (busy) {
      return;
    }

    setBusy(true);
    setError(null);
    setNotice(null);

    try {
      await action();

      setNotice(successMessage);
      setShowRollover(false);
      setTargetDate("");

      // 不自行把任务设置为 COMPLETED。
      // 重新读取后端状态才是最终结果。
      onChanged();

      if (showRecords) {
        await refreshRecords();
      }
    } catch (err) {
      if (
        err instanceof ApiError &&
        err.status === 401
      ) {
        router.replace("/login");
        return;
      }

      setError(getErrorText(err));
    } finally {
      setBusy(false);
    }
  }


  function handleBooleanComplete() {
    if (!canOperate || busy) {
      return;
    }

    void runAction(
      () => completeBooleanTask(task.id),
      "BOOLEAN 任务已完成",
    );
  }


  function handleNumericProgress() {
    if (!canOperate || busy) {
      return;
    }

    const text = actualText.trim();

    if (!/^\d+$/.test(text)) {
      setError("累计数量必须是非负整数");
      return;
    }

    const quantity = Number(text);

    if (!Number.isSafeInteger(quantity)) {
      setError("数量超出前端安全整数范围");
      return;
    }

    void runAction(
      () => updateNumericTask(task.id, quantity),
      "累计完成数量已更新",
    );
  }


  function handleRollover() {
    if (!canOperate || busy) {
      return;
    }

    if (!targetDate) {
      setError("请选择顺延目标日期");
      return;
    }

    if (targetDate > task.plan_end_date) {
      setError("目标日期不能超过计划结束日期");
      return;
    }

    const confirmed = window.confirm(
      task.task_type === "NUMERIC"
        ? "确定将当前任务剩余的全部数量顺延到所选日期吗？"
        : "确定将这条未完成任务顺延到所选日期吗？",
    );

    if (!confirmed) {
      return;
    }

    void runAction(
      () => rolloverTask(task.id, {
        target_date: targetDate,
      }),
      "任务顺延成功",
    );
  }


  async function toggleRecords() {
    if (showRecords) {
      setShowRecords(false);
      return;
    }

    setShowRecords(true);
    await refreshRecords();
  }


  return (
    <article className="space-y-4 rounded-xl border border-slate-200 bg-white p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-semibold">
            {task.content || task.step_name}
          </h2>

          <p className="mt-1 text-sm text-slate-500">
            {task.step_name} · {task.task_date}
          </p>

          <p className="mt-1 text-xs text-slate-500">
            {task.task_type === "BOOLEAN"
              ? "完成型任务"
              : "数量型任务"}
          </p>
        </div>

        <span className="rounded bg-slate-100 px-3 py-1 text-sm">
          {statusLabels[task.display_status]}
        </span>
      </div>

      {task.task_type === "NUMERIC" && (
        <div className="space-y-2">
          <p className="text-sm">
            实际累计：{task.actual_quantity}
          </p>

          <p className="text-sm">
            当前有效目标：
            {task.effective_target_quantity ?? task.target_quantity ?? 0}
          </p>

          <p className="text-sm">
            尚需完成：{task.remaining_quantity ?? 0}
          </p>

          {task.rollover_out_quantity > 0 && (
            <p className="text-sm text-blue-700">
              已转出数量：{task.rollover_out_quantity}
            </p>
          )}
        </div>
      )}

      {isRolledOver && (
        <p className="text-sm text-amber-700">
          该任务已发生向外顺延，来源不能再次打卡或顺延。
        </p>
      )}

      {error && (
        <p role="alert" className="text-sm text-red-700">
          {error}
        </p>
      )}

      {notice && (
        <p role="status" className="text-sm text-green-700">
          {notice}
        </p>
      )}

      {canOperate && (
        <div className="space-y-3">
          {task.task_type === "BOOLEAN" ? (
            <button
              type="button"
              onClick={handleBooleanComplete}
              disabled={busy}
              className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
            >
              {busy ? "处理中..." : "完成任务"}
            </button>
          ) : (
            <div className="flex flex-wrap items-end gap-3">
              <div>
                <label
                  htmlFor={`actual-${task.id}`}
                  className="mb-1 block text-sm"
                >
                  当前累计完成数量
                </label>

                <input
                  id={`actual-${task.id}`}
                  type="text"
                  inputMode="numeric"
                  value={actualText}
                  onChange={(event) =>
                    setActualText(event.target.value)
                  }
                  disabled={busy}
                  className="w-40 rounded border px-3 py-2"
                />
              </div>

              <button
                type="button"
                onClick={handleNumericProgress}
                disabled={busy}
                className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
              >
                {busy ? "保存中..." : "保存累计数量"}
              </button>
            </div>
          )}

          <button
            type="button"
            disabled={busy}
            onClick={() => {
              setError(null);
              setShowRollover((value) => !value);
            }}
            className="block text-sm text-blue-700"
          >
            {showRollover ? "取消顺延" : "顺延到未来日期"}
          </button>

          {showRollover && (
            <div className="space-y-3 rounded border p-3">
              <label
                htmlFor={`rollover-${task.id}`}
                className="block text-sm"
              >
                顺延目标日期
              </label>

              <input
                id={`rollover-${task.id}`}
                type="date"
                value={targetDate}
                max={task.plan_end_date}
                onChange={(event) =>
                  setTargetDate(event.target.value)
                }
                disabled={busy}
                className="rounded border px-3 py-2"
              />

              <p className="text-xs text-slate-500">
                只能选择后端业务日期之后、
                且不超过计划结束日的日期。
                最终合法性由后端检查。
              </p>

              <button
                type="button"
                onClick={handleRollover}
                disabled={busy}
                className="rounded border border-blue-600 px-4 py-2 text-blue-700 disabled:opacity-50"
              >
                确认顺延
              </button>
            </div>
          )}
        </div>
      )}

      <div className="border-t border-slate-200 pt-3">
        <button
          type="button"
          onClick={() => void toggleRecords()}
          className="text-sm text-blue-700"
        >
          {showRecords ? "收起打卡历史" : "查看打卡历史"}
        </button>

        {showRecords && (
          <div className="mt-3 space-y-2">
            {recordsLoading ? (
              <p className="text-sm">正在加载历史...</p>
            ) : recordsError ? (
              <p role="alert" className="text-sm text-red-700">
                {recordsError}
              </p>
            ) : records.length === 0 ? (
              <p className="text-sm text-slate-500">
                暂无打卡记录
              </p>
            ) : (
              <ul className="space-y-2">
                {records.map((record) => (
                  <li
                    key={record.id}
                    className="rounded bg-slate-50 p-3 text-sm"
                  >
                    <p>
                      {record.event_type === "BOOLEAN_COMPLETE"
                        ? "BOOLEAN 完成打卡"
                        : `NUMERIC 累计：${record.recorded_value ?? 0}`}
                    </p>

                    <p className="mt-1 text-xs text-slate-500">
                      记录时间：{record.recorded_at}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </article>
  );
}
