"use client";

import { messages } from "@/messages";

import {
  useEffect,
  useState,
} from "react";

import { useRouter } from "next/navigation";

import { ApiError } from "@/lib/api/client";
import { useDailyCheckin } from "@/hooks/useDailyCheckin";
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
  PENDING: messages.tasks.statusPending,
  IN_PROGRESS: messages.common.statusActive,
  COMPLETED: messages.tasks.statusCompleted,
  OVERDUE: messages.tasks.statusOverdue,
  ENDED: messages.tasks.statusStopped,
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
    : messages.common.operationFailedRetry;
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
  const daily = useDailyCheckin(task.id, task.task_type === "NUMERIC" && canOperate);


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
      messages.tasks.booleanCompletedNotice,
    );
  }


  function handleNumericProgress() {
    if (!canOperate || busy || daily.state !== "available") {
      return;
    }

    const text = actualText.trim();

    if (!/^\d+$/.test(text)) {
      setError(messages.tasks.actualIntegerRequired);
      return;
    }

    const quantity = Number(text);

    if (!Number.isSafeInteger(quantity)) {
      setError(messages.tasks.quantityTooLarge);
      return;
    }

    void runAction(
      async () => { await updateNumericTask(task.id, quantity); daily.markDone(); },
      messages.tasks.quantityUpdated,
    );
  }


  function handleRollover() {
    if (!canOperate || busy) {
      return;
    }

    if (!targetDate) {
      setError(messages.tasks.rolloverDateRequired);
      return;
    }

    if (targetDate > task.plan_end_date) {
      setError(messages.tasks.rolloverDateTooLate);
      return;
    }

    const confirmed = window.confirm(
      task.task_type === "NUMERIC"
        ? messages.tasks.numericRolloverConfirm
        : messages.tasks.booleanRolloverConfirm,
    );

    if (!confirmed) {
      return;
    }

    void runAction(
      () => rolloverTask(task.id, {
        target_date: targetDate,
      }),
      messages.tasks.rolloverSuccess,
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
              ? messages.tasks.booleanType
              : messages.tasks.numericType}
          </p>
        </div>

        <span className="workspace-task-status" data-status={task.display_status}>
          {task.task_type === "NUMERIC" && ["PENDING", "IN_PROGRESS"].includes(task.display_status) ? messages.tasks.statusIncomplete : statusLabels[task.display_status]}
        </span>
      </div>

      {task.task_type === "NUMERIC" && (
        <div className="task-quantity-summary">
          <p>
            <span>{messages.tasks.actualQuantity}</span><strong>{task.actual_quantity}</strong>
          </p>

          <p>
            <span>{messages.tasks.effectiveTarget}</span>
            <strong>{task.effective_target_quantity ?? task.target_quantity ?? 0}</strong>
          </p>

          <p>
            <span>{messages.tasks.remaining}</span><strong>{task.remaining_quantity ?? 0}</strong>
          </p>

          {task.rollover_out_quantity > 0 && (
            <p>
              <span>{messages.tasks.rolledOut}</span><strong>{task.rollover_out_quantity}</strong>
            </p>
          )}
        </div>
      )}

      {isRolledOver && (
        <p className="workspace-feedback workspace-feedback--warning">{messages.tasks.rolloverLockedHint}</p>
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
              {busy ? messages.common.processing : messages.tasks.checkin}
            </button>
          ) : daily.state === "done" ? (
            <span className="checkin-success-text">{messages.tasks.encouragement}</span>
          ) : (
            <div className="task-progress-form">
              <div>
                <label
                  htmlFor={`actual-${task.id}`}
                  className="workspace-field-label"
                >{messages.tasks.currentQuantity}</label>

                <input
                  id={`actual-${task.id}`}
                  type="text"
                  inputMode="numeric"
                  value={actualText}
                  onChange={(event) =>
                    setActualText(event.target.value)
                  }
                  disabled={busy || daily.state !== "available"}
                  className="task-action-input"
                />
              </div>

              <button
                type="button"
                onClick={handleNumericProgress}
                disabled={busy || daily.state !== "available"}
                className="workspace-button workspace-button--primary"
              >
                {busy ? messages.common.savingShort : daily.state === "loading" ? messages.tasks.confirming : messages.tasks.checkin}
              </button>
              {daily.state === "error" && <button type="button" onClick={daily.retry} className="workspace-text-link">{messages.tasks.confirmRetry}</button>}
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
            {showRollover ? messages.tasks.cancelRollover : messages.tasks.rollover}
          </button>

          {showRollover && (
            <div className="task-rollover-form">
              <label
                htmlFor={`rollover-${task.id}`}
                className="workspace-field-label"
              >{messages.tasks.rolloverDate}</label>

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

              <p className="task-action-help">{messages.tasks.rolloverDateHint}</p>

              <button
                type="button"
                onClick={handleRollover}
                disabled={busy}
                className="workspace-button workspace-button--secondary"
              >{messages.tasks.confirmRollover}</button>
            </div>
          )}
        </div>
      )}

      {!canOperate && !isRolledOver && task.status === "COMPLETED" && <span className="checkin-success-text">{messages.tasks.encouragement}</span>}

      <div className="task-records">
        <button
          type="button"
          onClick={() => void toggleRecords()}
          className="workspace-text-link"
        >
          {showRecords ? messages.history.collapseFull : messages.history.viewFull}
        </button>

        {showRecords && (
          <div className="task-records-content">
            {recordsLoading ? (
              <p className="workspace-muted">{messages.history.loadingFull}</p>
            ) : recordsError ? (
              <p role="alert" className="workspace-feedback workspace-feedback--error">
                {recordsError}
              </p>
            ) : records.length === 0 ? (
              <p className="workspace-muted">{messages.history.emptyRecords}</p>
            ) : (
              <ul className="task-records-list">
                {records.map((record) => (
                  <li
                    key={record.id}
                    className="task-record-item"
                  >
                    <p>
                      {record.event_type === "BOOLEAN_COMPLETE"
                        ? messages.tasks.booleanCheckin
                        : messages.tasks.recordedTotalWithColon(record.recorded_value ?? 0)}
                    </p>

                    <p className="task-record-time">{messages.history.recordedAt(record.recorded_at)}
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
