
"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { StepRuleFields } from "./StepRuleFields";

import {
  buildStepRule,
  type RuleMode,
} from "@/lib/plans/step-rule";

import { getBusinessToday } from "@/lib/plans/business-date";
import { listPlanDates } from "@/lib/plans/date-range";
import { ApiError } from "@/lib/api/client";

import {
  getPlanSteps,
  createActiveStep,
  deleteActiveStep,
} from "@/services/steps.service";

import type { Plan } from "@/types/plan";
import type {
  StepNode,
  ActiveStepNode,
} from "@/types/step";
import type { ScheduleEntryInput } from "@/types/schedule";

type Props = {
  plan: Plan;
  onChanged?: () => void;
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
    : "操作失败";
}

function collectGroups(
  nodes: StepNode[],
  depth = 0,
): { id: number; label: string }[] {
  const result: { id: number; label: string }[] = [];

  for (const node of nodes) {
    if (node.node_type !== "GROUP") {
      continue;
    }

    result.push({
      id: node.id,
      label: `${"— ".repeat(depth)}${node.name}`,
    });

    result.push(
      ...collectGroups(node.children, depth + 1),
    );
  }

  return result;
}

function ActiveTreeItem({
  node,
  onDelete,
  busy,
}: {
  node: StepNode;
  onDelete: (node: StepNode) => void;
  busy: boolean;
}) {
  return (
    <li className="my-2">
      <div className="flex items-center justify-between gap-3 rounded border p-3">
        <div>
          <strong>{node.name}</strong>
          <p className="text-sm text-slate-500">
            {node.node_type === "GROUP"
              ? "GROUP · 分类"
              : `${node.task_type} · ${node.schedule_mode}`}
          </p>
        </div>

        <button
          type="button"
          disabled={busy}
          onClick={() => onDelete(node)}
          className="text-red-700"
        >
          删除子树
        </button>
      </div>

      {node.children.length > 0 && (
        <ul className="ml-5 border-l pl-4">
          {node.children.map((child) => (
            <ActiveTreeItem
              key={child.id}
              node={child}
              onDelete={onDelete}
              busy={busy}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

export function ActiveStepManager({
  plan,
  onChanged,
}: Props) {
  const router = useRouter();

  const [tree, setTree] = useState<StepNode[]>([]);
  const [revision, setRevision] = useState(0);

  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [today, setToday] = useState<string | null>(null);

  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [parentId, setParentId] = useState("");
  const [nodeType, setNodeType] =
    useState<"LEAF" | "GROUP">("LEAF");

  const [name, setName] = useState("");
  const [firstLeafName, setFirstLeafName] = useState("");

  const [mode, setMode] =
    useState<RuleMode>("BOOLEAN_REPEAT");
  const [repeatContent, setRepeatContent] = useState("");
  const [totalText, setTotalText] = useState("0");

  const [booleanDaily, setBooleanDaily] =
    useState<Record<string, string>>({});

  const [numericDaily, setNumericDaily] =
    useState<Record<string, string>>({});

  useEffect(() => {
    setToday(getBusinessToday());
  }, []);

  // ACTIVE 新增节点只生成剩余周期的任务
  const remainingDates = useMemo(() => {
    if (today === null || today > plan.end_date) {
      return [];
    }

    const start =
      today > plan.start_date ? today : plan.start_date;

    return listPlanDates(start, plan.end_date);
  }, [today, plan.start_date, plan.end_date]);

  const groups = useMemo(
    () => collectGroups(tree),
    [tree],
  );

  useEffect(() => {
    let cancelled = false;

    async function loadTree() {
      setLoading(true);
      setError(null);

      try {
        const result = await getPlanSteps(plan.id);

        if (!cancelled) {
          setTree(result);
        }
      } catch (err) {
        if (!cancelled) {
          setError(getErrorText(err));
          setTree([]);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadTree();

    return () => {
      cancelled = true;
    };
  }, [plan.id, revision]);

  function handleApiError(err: unknown) {
    if (err instanceof ApiError && err.status === 401) {
      router.replace("/login");
      return;
    }

    setError(getErrorText(err));
  }

  function buildEntries(
    ruleMode: RuleMode,
    totalTarget: number | null | undefined,
  ): ScheduleEntryInput[] {
    const entries: ScheduleEntryInput[] = [];

    if (ruleMode === "BOOLEAN_DAILY_CUSTOM") {
      for (const date of remainingDates) {
        // 每行代表当天的一条 BOOLEAN 任务
        const lines = (booleanDaily[date] ?? "")
          .split(/\r?\n/)
          .map((line) => line.trim())
          .filter(Boolean);

        if (lines.length === 0) {
          throw new Error(`${date} 至少填写一条任务内容`);
        }

        for (const content of lines) {
          entries.push({
            task_date: date,
            content,
          });
        }
      }
    }

    if (ruleMode === "NUMERIC_DAILY_MANUAL") {
      let sum = 0;

      for (const date of remainingDates) {
        const value = (numericDaily[date] ?? "").trim();

        if (!/^\d+$/.test(value)) {
          throw new Error(`${date} 必须填写非负整数`);
        }

        const quantity = Number(value);

        if (!Number.isSafeInteger(quantity)) {
          throw new Error(`${date} 的数量超出安全范围`);
        }

        sum += quantity;

        if (!Number.isSafeInteger(sum)) {
          throw new Error("总数量超出安全整数范围");
        }

        entries.push({
          task_date: date,
          target_quantity: quantity,
        });
      }

      if (sum !== totalTarget) {
        throw new Error(
          `每日数量合计 ${sum}，但总目标是 ${totalTarget}`,
        );
      }
    }

    return entries;
  }

  async function handleCreate() {
    if (busy || plan.status !== "ACTIVE") {
      return;
    }

    const cleanedName = name.trim();

    if (!cleanedName) {
      setError("请输入节点名称");
      return;
    }

    if (remainingDates.length === 0) {
      setError("当前计划已超过结束日期，不能新增执行任务");
      return;
    }

    try {
      const rule = buildStepRule(
        mode,
        repeatContent,
        totalText,
      );

      const entries = buildEntries(mode, rule.total_target);

      const leafName =
        nodeType === "LEAF"
          ? cleanedName
          : firstLeafName.trim();

      if (!leafName) {
        setError("请填写第一个叶子的名称");
        return;
      }

      const leaf: ActiveStepNode = {
        name: leafName,
        node_type: "LEAF",
        rule,
        ...(entries.length > 0 ? { entries } : {}),
      };

      const node: ActiveStepNode =
        nodeType === "GROUP"
          ? {
              name: cleanedName,
              node_type: "GROUP",
              children: [leaf],
            }
          : leaf;

      setBusy(true);
      setError(null);
      setNotice(null);

      const result = await createActiveStep(plan.id, {
        parent_id:
          parentId === "" ? null : Number(parentId),
        node,
      });

      setNotice(
        `创建成功，生成 ${result.generated_task_count} 条每日任务`,
      );

      setName("");
      setFirstLeafName("");
      setBooleanDaily({});
      setNumericDaily({});

      setRevision((value) => value + 1);
      onChanged?.();
    } catch (err) {
      handleApiError(err);
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(node: StepNode) {
    if (busy || plan.status !== "ACTIVE") {
      return;
    }

    const confirmed = window.confirm(
      `确定删除「${node.name}」及其所有后代吗？\n\n` +
      "关联的有效每日任务将被逻辑删除，" +
      "完成率会重新统计。\n" +
      "至少需要保留一个有效叶子节点。",
    );

    if (!confirmed) {
      return;
    }

    setBusy(true);
    setError(null);
    setNotice(null);

    try {
      await deleteActiveStep(plan.id, node.id);

      setNotice("节点及其关联任务已删除");
      setRevision((value) => value + 1);
      onChanged?.();
    } catch (err) {
      handleApiError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="space-y-6 rounded border p-5">
      <h2 className="text-xl font-semibold">
        执行中的学习步骤
      </h2>

      <p className="text-sm text-slate-500">
        可以新增步骤或删除子树。
        已存在节点的修改规则与草稿阶段不同，
        不在这里直接修改执行规则。
      </p>

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
        <p>正在加载步骤树...</p>
      ) : (
        <ul>
          {tree.map((node) => (
            <ActiveTreeItem
              key={node.id}
              node={node}
              busy={busy}
              onDelete={(item) => void handleDelete(item)}
            />
          ))}
        </ul>
      )}

      {remainingDates.length === 0 ? (
        <p>
          当前计划已没有可以新生成任务的日期。
        </p>
      ) : (
        <div className="space-y-4 border-t pt-5">
          <h3 className="font-semibold">
            新增执行中的学习节点
          </h3>

          <p className="text-sm text-slate-500">
            本次新节点的任务生成范围：
            {remainingDates[0]} ～{" "}
            {remainingDates[remainingDates.length - 1]}
          </p>

          <div>
            <label className="mb-1 block">新增位置</label>

            <select
              value={parentId}
              onChange={(event) =>
                setParentId(event.target.value)
              }
              disabled={busy || loading}
              className="w-full rounded border p-2"
            >
              <option value="">顶层</option>

              {groups.map((group) => (
                <option key={group.id} value={group.id}>
                  {group.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1 block">节点类型</label>

            <select
              value={nodeType}
              disabled={busy}
              onChange={(event) =>
                setNodeType(
                  event.target.value as "LEAF" | "GROUP",
                )
              }
              className="w-full rounded border p-2"
            >
              <option value="LEAF">LEAF · 学习项目</option>
              <option value="GROUP">GROUP · 分类</option>
            </select>
          </div>

          <div>
            <label className="mb-1 block">节点名称</label>

            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              disabled={busy}
              className="w-full rounded border p-2"
            />
          </div>

          {nodeType === "GROUP" && (
            <div>
              <label className="mb-1 block">
                第一个叶子名称
              </label>

              <input
                value={firstLeafName}
                onChange={(event) =>
                  setFirstLeafName(event.target.value)
                }
                disabled={busy}
                className="w-full rounded border p-2"
              />
            </div>
          )}

          <StepRuleFields
            mode={mode}
            onModeChange={setMode}
            repeatContent={repeatContent}
            onRepeatContentChange={setRepeatContent}
            totalText={totalText}
            onTotalTextChange={setTotalText}
          />

          {mode === "BOOLEAN_DAILY_CUSTOM" && (
            <div className="space-y-3">
              <h4 className="font-medium">
                每日 BOOLEAN 任务
              </h4>

              <p className="text-sm">
                每天至少一条，每行填写一条任务。
              </p>

              {remainingDates.map((date) => (
                <div key={date}>
                  <label className="block">{date}</label>
                  <textarea
                    rows={2}
                    value={booleanDaily[date] ?? ""}
                    onChange={(event) =>
                      setBooleanDaily((current) => ({
                        ...current,
                        [date]: event.target.value,
                      }))
                    }
                    disabled={busy}
                    className="w-full rounded border p-2"
                  />
                </div>
              ))}
            </div>
          )}

          {mode === "NUMERIC_DAILY_MANUAL" && (
            <div className="space-y-3">
              <h4 className="font-medium">
                每日 NUMERIC 目标
              </h4>

              {remainingDates.map((date) => (
                <div key={date}>
                  <label className="block">{date}</label>
                  <input
                    type="text"
                    inputMode="numeric"
                    value={numericDaily[date] ?? ""}
                    onChange={(event) =>
                      setNumericDaily((current) => ({
                        ...current,
                        [date]: event.target.value,
                      }))
                    }
                    disabled={busy}
                    className="w-full rounded border p-2"
                  />
                </div>
              ))}
            </div>
          )}

          <button
            type="button"
            disabled={busy || loading}
            onClick={() => void handleCreate()}
            className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
          >
            {busy ? "正在创建..." : "新增节点并生成任务"}
          </button>
        </div>
      )}
    </section>
  );
}
