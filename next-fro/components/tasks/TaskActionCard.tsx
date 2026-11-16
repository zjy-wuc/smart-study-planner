
"use client";

import {
  useEffect,
  useState,
} from "react";

import { useRouter } from "next/navigation";

import { ApiError } from "@/lib/api/client";
import "@/components/css/Tasks.css";

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
    <article className="task-action-card" data-status={task.display_status}>
      <div className="task-action-heading">
        <div>
          <h2 className="font-semibold">
            {task.content || task.step_name}
          </h2>

          <p className="task-action-meta">
            {task.step_name} · {task.task_date}
          </p>

          <p className="task-action-type">
            {task.task_type === "BOOLEAN"
              ? "完成型任务"
              : "数量型任务"}
          </p>
        </div>

        <span className="workspace-task-status" data-status={task.display_status}>
          {statusLabels[task.display_status]}
        </span>
      </div>

      {task.task_type === "NUMERIC" && (
        <div className="task-quantity-summary">
          <p>
            <span>实际累计</span><strong>{task.actual_quantity}</strong>
          </p>

          <p>
            <span>当前有效目标</span>
            <strong>{task.effective_target_quantity ?? task.target_quantity ?? 0}</strong>
          </p>

          <p>
            <span>尚需完成</span><strong>{task.remaining_quantity ?? 0}</strong>
          </p>

          {task.rollover_out_quantity > 0 && (
            <p>
              <span>已转出数量</span><strong>{task.rollover_out_quantity}</strong>
            </p>
          )}
        </div>
      )}

      {isRolledOver && (
        <p className="workspace-feedback workspace-feedback--warning">
          该任务已发生向外顺延，来源不能再次打卡或顺延。
        </p>
      )}

      {error && (
        <p role="alert" className="workspace-feedback workspace-feedback--error">
          {error}
        </p>
      )}

      {notice && (
        <p role="status" className="workspace-feedback workspace-feedback--success">
          {notice}
        </p>
      )}

      {canOperate && (
        <div className="task-action-controls">
          {task.task_type === "BOOLEAN" ? (
            <button
              type="button"
              onClick={handleBooleanComplete}
              disabled={busy}
              className="workspace-button workspace-button--primary"
            >
              {busy ? "处理中..." : "完成任务"}
            </button>
          ) : (
            <div className="task-progress-form">
              <div>
                <label
                  htmlFor={`actual-${task.id}`}
                  className="workspace-field-label"
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
                  className="task-action-input"
                />
              </div>

              <button
                type="button"
                onClick={handleNumericProgress}
                disabled={busy}
                className="workspace-button workspace-button--primary"
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
            className="workspace-text-link task-rollover-toggle"
          >
            {showRollover ? "取消顺延" : "顺延到未来日期"}
          </button>

          {showRollover && (
            <div className="task-rollover-form">
              <label
                htmlFor={`rollover-${task.id}`}
                className="workspace-field-label"
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
                className="task-action-input"
              />

              <p className="task-action-help">
                只能选择后端业务日期之后、
                且不超过计划结束日的日期。
                最终合法性由后端检查。
              </p>

              <button
                type="button"
                onClick={handleRollover}
                disabled={busy}
                className="workspace-button workspace-button--secondary"
              >
                确认顺延
              </button>
            </div>
          )}
        </div>
      )}

      <div className="task-records">
        <button
          type="button"
          onClick={() => void toggleRecords()}
          className="workspace-text-link"
        >
          {showRecords ? "收起打卡历史" : "查看打卡历史"}
        </button>

        {showRecords && (
          <div className="task-records-content">
            {recordsLoading ? (
              <p className="workspace-muted">正在加载历史...</p>
            ) : recordsError ? (
              <p role="alert" className="workspace-feedback workspace-feedback--error">
                {recordsError}
              </p>
            ) : records.length === 0 ? (
              <p className="workspace-muted">
                暂无打卡记录
              </p>
            ) : (
              <ul className="task-records-list">
                {records.map((record) => (
                  <li
                    key={record.id}
                    className="task-record-item"
                  >
                    <p>
                      {record.event_type === "BOOLEAN_COMPLETE"
                        ? "BOOLEAN 完成打卡"
                        : `NUMERIC 累计：${record.recorded_value ?? 0}`}
                    </p>

                    <p className="task-record-time">
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
