"use client";

import { messages } from "@/messages";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  CheckCircle2,
  ChevronUp,
  Plus,
  RefreshCw,
  X,
} from "lucide-react";

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
  manageHref?: string;
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
    : messages.common.operationFailed;
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

function countNodes(nodes: StepNode[]): number {
  return nodes.reduce(
    (total, node) => total + 1 + countNodes(node.children),
    0,
  );
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
    <li className="plan-step-branch">
      <div className="plan-step-row" data-kind={node.node_type}>
        <div className="plan-step-row-heading">
          <strong>{node.name}</strong>
          <span>
            {node.node_type === "GROUP"
              ? messages.steps.groupType
              : `${node.task_type} · ${node.schedule_mode}`}
          </span>
        </div>

        <div className="plan-step-row-actions"><button type="button" disabled={busy} onClick={() => onDelete(node)} className="is-danger">{messages.steps.deleteSubtree}</button></div>
      </div>

      {node.children.length > 0 && (
        <ul className="plan-step-children">
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
  manageHref,
}: Props) {
  const router = useRouter();

  const [tree, setTree] = useState<StepNode[]>([]);
  const [revision, setRevision] = useState(0);

  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [today, setToday] = useState<string | null>(null);

  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(!manageHref);
  const [creationSuccessOpen, setCreationSuccessOpen] = useState(false);
  const [createdTaskCount, setCreatedTaskCount] = useState(0);

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
    // 客户端挂载后再读取业务日期，避免服务端预渲染跨日造成水合差异。
    // eslint-disable-next-line react-hooks/set-state-in-effect
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
  const stepCount = useMemo(() => countNodes(tree), [tree]);

  useEffect(() => {
    if (!creationSuccessOpen) return;
    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setCreationSuccessOpen(false);
    }
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [creationSuccessOpen]);

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
          throw new Error(messages.steps.dateContentRequired(date));
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
          throw new Error(messages.steps.dateIntegerRequired(date));
        }

        const quantity = Number(value);

        if (!Number.isSafeInteger(quantity)) {
          throw new Error(messages.steps.dateQuantityTooLarge(date));
        }

        sum += quantity;

        if (!Number.isSafeInteger(sum)) {
          throw new Error(messages.steps.totalTooLarge);
        }

        entries.push({
          task_date: date,
          target_quantity: quantity,
        });
      }

      if (sum !== totalTarget) {
        throw new Error(
          messages.steps.totalMismatch(sum, totalTarget),
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
      setError(messages.steps.nameRequired);
      return;
    }

    if (remainingDates.length === 0) {
      setError(messages.steps.planExpired);
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
        setError(messages.steps.firstLeafRequired);
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

      setCreatedTaskCount(result.generated_task_count);
      setCreationSuccessOpen(true);

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
      messages.steps.deleteSubtreeConfirm(node.name),
    );

    if (!confirmed) {
      return;
    }

    setBusy(true);
    setError(null);
    setNotice(null);

    try {
      await deleteActiveStep(plan.id, node.id);

      setNotice(messages.steps.subtreeDeleted);
      setRevision((value) => value + 1);
      onChanged?.();
    } catch (err) {
      handleApiError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <section id="plan-steps" className="plan-step-card">
        <header className="plan-step-card-header">
          <div><h2>{messages.steps.activeTitle}</h2><p>{messages.steps.stepCount(stepCount)}</p></div>
          <div className="plan-step-header-actions">
            <button type="button" className="plan-step-refresh" onClick={() => setRevision((value) => value + 1)} disabled={loading || busy} aria-label={messages.steps.refresh}><RefreshCw size={16} aria-hidden="true" /></button>
            {remainingDates.length > 0 && (manageHref ? (
              <Link className="plan-step-add" href={manageHref}><span><Plus size={16} /></span>{messages.steps.addStep}</Link>
            ) : (
              <button type="button" className="plan-step-add" onClick={() => setCreateOpen((value) => !value)}><span>{createOpen ? <ChevronUp size={16} /> : <Plus size={16} />}</span>{createOpen ? messages.steps.collapseCreate : messages.steps.addStep}</button>
            ))}
          </div>
        </header>

        <p className="plan-step-active-description">{messages.steps.activeDescription}</p>
        {error && <p role="alert" className="plan-step-feedback is-error">{error}</p>}
        {notice && <p role="status" className="plan-step-feedback is-success">{notice}</p>}

        {remainingDates.length === 0 ? <p className="plan-step-readonly">{messages.steps.noRemainingDates}</p> : createOpen && (
          <div className="plan-step-editor">
            <h3>{messages.steps.addActiveTitle}</h3>
            <p className="plan-step-generation-period">{messages.steps.generationPeriod}{remainingDates[0]} ～ {remainingDates[remainingDates.length - 1]}</p>
            <div className="plan-step-form-grid">
              <div><label htmlFor="active-step-parent">{messages.steps.parentLabel}</label><select id="active-step-parent" value={parentId} onChange={(event) => setParentId(event.target.value)} disabled={busy || loading}><option value="">{messages.steps.topLevel}</option>{groups.map((group) => <option key={group.id} value={group.id}>{group.label}</option>)}</select></div>
              <div><label htmlFor="active-step-type">{messages.steps.nodeType}</label><select id="active-step-type" value={nodeType} disabled={busy} onChange={(event) => setNodeType(event.target.value as "LEAF" | "GROUP")}><option value="LEAF">{messages.steps.leafType}</option><option value="GROUP">{messages.steps.groupType}</option></select></div>
              <div className="plan-step-form-wide"><label htmlFor="active-step-name">{messages.steps.nodeName}</label><input id="active-step-name" value={name} onChange={(event) => setName(event.target.value)} disabled={busy} /></div>
              {nodeType === "GROUP" && <div className="plan-step-form-wide"><label htmlFor="active-step-first-leaf">{messages.steps.firstLeafName}</label><input id="active-step-first-leaf" value={firstLeafName} onChange={(event) => setFirstLeafName(event.target.value)} disabled={busy} /></div>}
            </div>
            <StepRuleFields mode={mode} onModeChange={setMode} repeatContent={repeatContent} onRepeatContentChange={setRepeatContent} totalText={totalText} onTotalTextChange={setTotalText} />

            {mode === "BOOLEAN_DAILY_CUSTOM" && <div className="plan-step-daily-fields"><h4>{messages.steps.dailyBoolean}</h4><p>{messages.steps.dailyBooleanHint}</p>{remainingDates.map((date) => <div key={date}><label htmlFor={`boolean-${date}`}>{date}</label><textarea id={`boolean-${date}`} rows={2} value={booleanDaily[date] ?? ""} onChange={(event) => setBooleanDaily((current) => ({ ...current, [date]: event.target.value }))} disabled={busy} /></div>)}</div>}
            {mode === "NUMERIC_DAILY_MANUAL" && <div className="plan-step-daily-fields"><h4>{messages.steps.dailyNumeric}</h4>{remainingDates.map((date) => <div key={date}><label htmlFor={`numeric-${date}`}>{date}</label><input id={`numeric-${date}`} type="text" inputMode="numeric" value={numericDaily[date] ?? ""} onChange={(event) => setNumericDaily((current) => ({ ...current, [date]: event.target.value }))} disabled={busy} /></div>)}</div>}

            <div className="plan-step-editor-actions"><button type="button" disabled={busy || loading} onClick={() => void handleCreate()}><Plus size={16} aria-hidden="true" />{busy ? messages.common.creating : messages.steps.createAndGenerate}</button></div>
          </div>
        )}

        <div className="plan-step-tree-section"><h3>{messages.steps.treeHeading}</h3>{loading ? <p className="plan-step-empty">{messages.steps.loadingTree}</p> : tree.length === 0 ? <p className="plan-step-empty">{messages.steps.emptyCurrentPlanSentence}</p> : <ul className="plan-step-tree">{tree.map((node) => <ActiveTreeItem key={node.id} node={node} busy={busy} onDelete={(item) => void handleDelete(item)} />)}</ul>}</div>
      </section>

      {creationSuccessOpen && (
        <div className="plan-step-success-backdrop">
          <section className="plan-step-success-dialog" role="dialog" aria-modal="true" aria-labelledby="active-step-success-title">
            <button type="button" className="plan-step-success-close" onClick={() => setCreationSuccessOpen(false)} aria-label={messages.steps.closeCreatedDialog}><X size={20} /></button>
            <span className="plan-step-success-mark" aria-hidden="true"><CheckCircle2 size={34} /></span>
            <h2 id="active-step-success-title">{messages.steps.createdDialogTitle}</h2>
            <p>{messages.steps.createdWithTasks(createdTaskCount)}</p>
            <button type="button" className="plan-step-success-action" onClick={() => setCreationSuccessOpen(false)} autoFocus>{messages.steps.continueAdding}</button>
          </section>
        </div>
      )}
    </>
  );
}
