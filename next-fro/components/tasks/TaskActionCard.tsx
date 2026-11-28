"use client";

import { messages } from "@/messages";
import { todayTaskMessages } from "@/messages/zh-CN/tasks";

import {
  useEffect,
  useState,
} from "react";

import { BookOpen, Check, ClipboardList } from "lucide-react";

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
  planName?: string;
  onChanged: () => void;
  onCheckinStatus: (taskId: number, checked: boolean) => void;
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
  planName,
  onChanged,
  onCheckinStatus,
}: Props) {
  const completionQuantity = task.effective_target_quantity ?? task.target_quantity ?? task.actual_quantity;

  const [actualText, setActualText] = useState("");
  const [quantityEdited, setQuantityEdited] = useState(false);

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
  const checkedIn = !isRolledOver && task.status === "COMPLETED";
  const label = isRolledOver ? messages.tasks.rolledOver
    : task.plan_status !== "ACTIVE" && task.status !== "COMPLETED" ? messages.tasks.statusStopped
    : task.task_type === "NUMERIC" && ["PENDING", "IN_PROGRESS"].includes(task.display_status)
      ? messages.tasks.statusIncomplete : statusLabels[task.display_status];

  useEffect(() => {
    onCheckinStatus(task.id, canOperate && daily.state === "done");
  }, [task.id, canOperate, daily.state, onCheckinStatus]);


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
    if (!canOperate || busy) {
      return;
    }

    const text = quantityEdited ? actualText.trim() : String(completionQuantity);

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
      async () => {
        await updateNumericTask(task.id, quantity);
        daily.markDone();
        setActualText("");
        setQuantityEdited(false);
      },
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
      <div className="today-task-row">
        <div className="today-task-identity">
          <span className="today-task-icon" data-checked={checkedIn} aria-hidden="true">
            {checkedIn ? <Check size={18} /> : task.task_type === "NUMERIC" ? <BookOpen size={18} /> : <ClipboardList size={18} />}
          </span>
          <div>
            <h3>{task.content || task.step_name}</h3>
            <p className="task-action-meta">{planName && <>{planName} / </>}{task.step_name}</p>
          </div>
        </div>
        <div className="today-task-state">
          {task.task_type === "NUMERIC" && <strong>{task.actual_quantity} / {task.effective_target_quantity ?? task.target_quantity ?? 0}</strong>}
          <span className="workspace-task-status" data-status={isRolledOver ? "ROLLED_OVER" : task.display_status}>{label}</span>
        </div>
        <div className="today-task-actions">
          {checkedIn && <span className="checkin-success-text">{messages.tasks.encouragement}</span>}
          {task.task_type === "NUMERIC" && canOperate && daily.state === "done" && <span className="checkin-success-text">{messages.tasks.todayRecorded}</span>}
          {canOperate && (task.task_type === "BOOLEAN" ? (
            <button type="button" onClick={handleBooleanComplete} disabled={busy} className="workspace-button workspace-button--primary">
              {busy ? messages.common.processing : messages.tasks.checkin}
            </button>
          ) : (
            <div className="task-progress-form">
              <label className="task-progress-label" htmlFor={`task-progress-${task.id}`}>{messages.tasks.cumulativeQuantityLabel}</label>
              <input
                id={`task-progress-${task.id}`}
                aria-label={messages.tasks.quantityLabel(task.content || task.step_name)}
                title={messages.tasks.numericCheckinHint}
                type="text" inputMode="numeric" value={actualText}
                placeholder={task.remaining_quantity !== null ? messages.tasks.remainingPlaceholder(task.remaining_quantity) : undefined}
                onChange={(event) => { setActualText(event.target.value); setQuantityEdited(true); }}
                disabled={busy}
                className="task-action-input"
              />
              <button type="button" onClick={handleNumericProgress} disabled={busy} className="workspace-button workspace-button--primary">
                {busy ? messages.common.savingShort : quantityEdited ? messages.tasks.checkin : messages.tasks.completeAll}
              </button>
            </div>
          ))}
        </div>
        <details className="today-task-details">
          <summary>{todayTaskMessages.expandTaskDetails}</summary>
          <div className="today-task-detail-content">
            <p className="task-action-meta">
              {task.task_type === "BOOLEAN" ? messages.tasks.booleanType : messages.tasks.numericType} · <time>{task.task_date}</time>
            </p>

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

            {canOperate && (
              <div className="task-action-controls">
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
          </div>
        </details>
      </div>
      {error && <p role="alert" className="workspace-feedback workspace-feedback--error">{error}</p>}
      {notice && <p role="status" className="workspace-feedback workspace-feedback--success">{notice}</p>}
    </article>
  );
}
