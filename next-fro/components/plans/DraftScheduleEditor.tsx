"use client";

import { messages } from "@/messages";
import { SaveSuccessDialog } from "@/components/ui/SaveSuccessDialog";

import {
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { ApiError } from "@/lib/api/client";
import { listPlanDates } from "@/lib/plans/date-range";

import { getPlanSteps } from "@/services/steps.service";
import {
  getSchedule,
  replaceSchedule,
} from "@/services/schedules.service";

import type { StepNode } from "@/types/step";
import type { ScheduleEntryInput } from "@/types/schedule";


type Props = {
  planId: number;
  startDate: string;
  endDate: string;
  treeRevision: number;
  onStepCount: (count: number | null) => void;
};

function countSteps(nodes: StepNode[]): number {
  return nodes.reduce((count, node) => count + 1 + countSteps(node.children), 0);
}

type CustomRow = {
  id: number;
  taskDate: string;
  content: string;
};


function collectManualLeaves(
  nodes: StepNode[],
): StepNode[] {
  const result: StepNode[] = [];

  for (const node of nodes) {
    if (
      node.node_type === "LEAF" &&
      (
        node.schedule_mode === "DAILY_CUSTOM" ||
        node.schedule_mode === "DAILY_MANUAL"
      )
    ) {
      result.push(node);
    }

    result.push(
      ...collectManualLeaves(node.children),
    );
  }

  return result;
}


function errorMessage(error: unknown): string {
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


export function DraftScheduleEditor({
  planId,
  startDate,
  endDate,
  treeRevision,
  onStepCount,
}: Props) {
  const dates = useMemo(
    () => listPlanDates(startDate, endDate),
    [startDate, endDate],
  );

  const [leaves, setLeaves] = useState<StepNode[]>([]);
  const [selectedStepId, setSelectedStepId] =
    useState<number | null>(null);

  const [customRows, setCustomRows] =
    useState<CustomRow[]>([]);

  const [numericValues, setNumericValues] =
    useState<Record<string, string>>({});

  const rowSequence = useRef(0);

  const [treeLoading, setTreeLoading] = useState(true);
  const [scheduleLoading, setScheduleLoading] =
    useState(false);

  const [saving, setSaving] = useState(false);

  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [scheduleRevision, setScheduleRevision] =
    useState(0);

  const selectedLeaf = leaves.find(
    (leaf) => leaf.id === selectedStepId,
  );
  const stepId = selectedLeaf?.id;
  const mode = selectedLeaf?.schedule_mode;

  // 读取当前计划中需要手动排期的叶子节点
  useEffect(() => {
    let cancelled = false;

    async function loadLeaves() {
      setTreeLoading(true);
      setError(null);

      try {
        const tree = await getPlanSteps(planId);
        const nextLeaves = collectManualLeaves(tree);

        if (cancelled) {
          return;
        }

        setLeaves(nextLeaves);
        onStepCount(countSteps(tree));

        setSelectedStepId((current) => {
          if (
            current !== null &&
            nextLeaves.some((leaf) => leaf.id === current)
          ) {
            return current;
          }

          return nextLeaves[0]?.id ?? null;
        });

      } catch (err) {
        if (!cancelled) {
          setLeaves([]);
          onStepCount(null);
          setSelectedStepId(null);
          setError(errorMessage(err));
        }
      } finally {
        if (!cancelled) {
          setTreeLoading(false);
        }
      }
    }

    void loadLeaves();

    return () => {
      cancelled = true;
    };
  }, [onStepCount, planId, treeRevision]);


  // 切换叶子时，从后端加载它已有的草稿安排
  useEffect(() => {
    if (stepId === undefined) return;

    let cancelled = false;

    async function loadEntries(stepId: number) {
      setScheduleLoading(true);
      setError(null);
      
      setCustomRows([]);
      setNumericValues({});

      try {
        const entries = await getSchedule(planId, stepId);

        if (cancelled) {
          return;
        }

        if (mode === "DAILY_CUSTOM") {
          const rows: CustomRow[] = [];

          for (const date of dates) {
            const currentEntries = entries.filter(
              (entry) => entry.task_date === date,
            );

            if (currentEntries.length === 0) {
              rows.push({
                id: ++rowSequence.current,
                taskDate: date,
                content: "",
              });
            } else {
              for (const entry of currentEntries) {
                rows.push({
                  id: ++rowSequence.current,
                  taskDate: date,
                  content: entry.content ?? "",
                });
              }
            }
          }

          setCustomRows(rows);
        }

        if (mode === "DAILY_MANUAL") {
          const values: Record<string, string> = {};

          for (const date of dates) {
            const entry = entries.find(
              (item) => item.task_date === date,
            );

            values[date] =
              entry?.target_quantity == null
                ? ""
                : String(entry.target_quantity);
          }

          setNumericValues(values);
        }

      } catch (err) {
        if (!cancelled) {
          setError(errorMessage(err));
        }
      } finally {
        if (!cancelled) {
          setScheduleLoading(false);
        }
      }
    }

    void loadEntries(stepId);

    return () => {
      cancelled = true;
    };
  }, [
    planId,
    stepId,
    mode,
    dates,
    scheduleRevision,
    treeRevision,
  ]);


  function addBooleanRow(date: string) {
    setCustomRows((current) => [
      ...current,
      {
        id: ++rowSequence.current,
        taskDate: date,
        content: "",
      },
    ]);
  }


  function updateBooleanRow(
    rowId: number,
    content: string,
  ) {
    setCustomRows((current) =>
      current.map((row) =>
        row.id === rowId
          ? { ...row, content }
          : row,
      ),
    );
  }


  function removeBooleanRow(rowId: number) {
    setCustomRows((current) =>
      current.filter((row) => row.id !== rowId),
    );
  }


  // 计算当前已填写的 NUMERIC 数量总和
  const numericSum = useMemo(() => {
    let sum = 0;

    for (const value of Object.values(numericValues)) {
      if (/^\d+$/.test(value.trim())) {
        sum += Number(value.trim());
      }
    }

    return Number.isSafeInteger(sum)
      ? String(sum)
      : messages.schedule.safeRangeExceeded;
  }, [numericValues]);


  async function handleSave() {
    if (!selectedLeaf || scheduleLoading || saving) {
      return;
    }

    setError(null);
    setNotice(null);

    const entries: ScheduleEntryInput[] = [];

    try {
      if (selectedLeaf.schedule_mode === "DAILY_CUSTOM") {
        // 空白输入行不保存；同一天可以有多条。
        for (const row of customRows) {
          const content = row.content.trim();

          if (content) {
            entries.push({
              task_date: row.taskDate,
              content,
            });
          }
        }
      } else if (
        selectedLeaf.schedule_mode === "DAILY_MANUAL"
      ) {
        for (const date of dates) {
          const text = (numericValues[date] ?? "").trim();

          // 暂时不填写某天是允许的：
          // 草稿可以保存不完整安排。
          if (text === "") {
            continue;
          }

          if (!/^\d+$/.test(text)) {
            throw new Error(
              messages.schedule.dateTargetInvalid(date),
            );
          }

          const value = Number(text);

          if (!Number.isSafeInteger(value)) {
            throw new Error(
              messages.schedule.dateTargetTooLarge(date),
            );
          }

          entries.push({
            task_date: date,
            target_quantity: value,
          });
        }
      } else {
        throw new Error(messages.schedule.notManual);
      }

      // PUT 是整组替换，清空时要求再次确认
      if (
        entries.length === 0 &&
        !window.confirm(
          messages.schedule.clearConfirm,
        )
      ) {
        return;
      }

      setSaving(true);

      await replaceSchedule(
        planId,
        selectedLeaf.id,
        entries,
      );

      setNotice(messages.schedule.saved);

      // 保存后重新读取数据库实际内容
      setScheduleRevision((value) => value + 1);

    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }


  if (treeLoading) return <p role="status">{messages.schedule.loadingSteps}</p>;
  if (!leaves.length) {
    return error ? <p role="alert" className="plan-detail-error">{error}</p> : null;
  }

  return (
    <section className="plan-workflow-card space-y-5">
      <h2 className="text-xl font-semibold">{messages.schedule.title}</h2>

      <p className="text-sm">{messages.schedule.description}</p>

      {error && (
        <p role="alert" className="text-red-600">
          {error}
        </p>
      )}

      {(
        <>
          <div>
            <label
              htmlFor="schedule-step"
              className="mb-2 block font-medium"
            >{messages.schedule.selectLeaf}</label>

            <select
              id="schedule-step"
              value={selectedStepId ?? ""}
              onChange={(event) => {
                  setNotice(null);
                setSelectedStepId(Number(event.target.value));
              }}
              disabled={saving}
              className="w-full rounded border p-2"
            >
              {leaves.map((leaf) => (
                <option key={leaf.id} value={leaf.id}>
                  {leaf.name} · {leaf.schedule_mode}
                </option>
              ))}
            </select>
          </div>

          {scheduleLoading ? (
            <p>{messages.schedule.loading}</p>
          ) : selectedLeaf?.schedule_mode ===
            "DAILY_CUSTOM" ? (
            <div className="space-y-4">
              {dates.map((date) => {
                const rows = customRows.filter(
                  (row) => row.taskDate === date,
                );

                return (
                  <div
                    key={date}
                    className="space-y-2 rounded border p-3"
                  >
                    <h3 className="font-medium">
                      {date}
                    </h3>

                    {rows.length === 0 && (
                      <p className="text-sm">{messages.schedule.emptyDay}</p>
                    )}

                    {rows.map((row) => (
                      <div
                        key={row.id}
                        className="flex gap-2"
                      >
                        <input
                          value={row.content}
                          onChange={(event) =>
                            updateBooleanRow(
                              row.id,
                              event.target.value,
                            )
                          }
                          disabled={saving}
                          placeholder={messages.schedule.contentPlaceholder}
                          className="min-w-0 flex-1 rounded border p-2"
                        />

                        <button
                          type="button"
                          disabled={saving}
                          onClick={() =>
                            removeBooleanRow(row.id)
                          }
                          className="text-red-700"
                        >{messages.common.delete}</button>
                      </div>
                    ))}

                    <button
                      type="button"
                      disabled={saving}
                      onClick={() => addBooleanRow(date)}
                      className="text-blue-700"
                    >{messages.schedule.addDailyTask}</button>
                  </div>
                );
              })}
            </div>
          ) : selectedLeaf?.schedule_mode ===
            "DAILY_MANUAL" ? (
            <div className="space-y-4">
              <p className="text-sm">
                {messages.schedule.quantitySummary(numericSum, selectedLeaf.total_target ?? 0)}
              </p>

              {dates.map((date) => (
                <div
                  key={date}
                  className="flex items-center gap-3"
                >
                  <label
                    htmlFor={`quantity-${date}`}
                    className="w-32 shrink-0"
                  >
                    {date}
                  </label>

                  <input
                    id={`quantity-${date}`}
                    type="text"
                    inputMode="numeric"
                    value={numericValues[date] ?? ""}
                    onChange={(event) =>
                      setNumericValues((current) => ({
                        ...current,
                        [date]: event.target.value,
                      }))
                    }
                    disabled={saving}
                    placeholder={messages.schedule.quantityPlaceholder}
                    className="min-w-0 flex-1 rounded border p-2"
                  />
                </div>
              ))}

              <p className="text-sm">{messages.schedule.numericHint}</p>
            </div>
          ) : null}

          <button
            type="button"
            disabled={
              saving ||
              scheduleLoading ||
              treeLoading ||
              !selectedLeaf
            }
            onClick={() => void handleSave()}
            className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
          >
            {saving ? messages.common.saving : messages.schedule.save}
          </button>
        </>
      )}
      <SaveSuccessDialog message={notice} onClose={() => setNotice(null)} />
    </section>
  );
}
