"use client";

import { messages } from "@/messages";

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import {
  CheckCircle2,
  ChevronDown,
  Ellipsis,
  ChevronUp,
  Plus,
  RefreshCw,
  X,
} from "lucide-react";

import {
  getPlanSteps,
  createStep,
  updateStep,
  updateStepRule,
  deleteStep,
} from "@/services/steps.service";

import { ApiError } from "@/lib/api/client";
import {
  buildStepRule,
  type RuleMode,
} from "@/lib/plans/step-rule";

import { StepRuleFields } from "./StepRuleFields";

import type { PlanStatus } from "@/types/plan";
import type {
  StepNode,
  StepCreate,
} from "@/types/step";


type Props = {
  planId: number;
  status: PlanStatus;
  onChanged?: () => void;
};

type GroupOption = {
  id: number;
  label: string;
  name: string;
};


function collectGroups(
  nodes: StepNode[],
  depth = 0,
): GroupOption[] {
  const result: GroupOption[] = [];

  for (const node of nodes) {
    if (node.node_type !== "GROUP") {
      continue;
    }

    result.push({
      id: node.id,
      name: node.name,
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

function findStepPath(nodes: StepNode[], id: number): number[] {
  for (const node of nodes) {
    if (node.id === id) return [id];
    const path = findStepPath(node.children, id);
    if (path.length) return [node.id, ...path];
  }
  return [];
}


function getRuleMode(node: StepNode): RuleMode {
  if (node.task_type === "BOOLEAN") {
    return node.schedule_mode === "DAILY_CUSTOM"
      ? "BOOLEAN_DAILY_CUSTOM"
      : "BOOLEAN_REPEAT";
  }

  return node.schedule_mode === "DAILY_MANUAL"
    ? "NUMERIC_DAILY_MANUAL"
    : "NUMERIC_AUTO_DISTRIBUTE";
}


function getErrorText(error: unknown): string {
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


function TreeItem({
  node,
  canEdit,
  onRename,
  onEditRule,
  onDelete,
  controls,
}: {
  node: StepNode;
  canEdit: boolean;
  onRename: (node: StepNode) => void;
  onEditRule: (node: StepNode) => void;
  onDelete: (node: StepNode) => void;
  controls: {
    collapsed: number[];
    toggle: (id: number) => void;
    editId?: number;
    savedId: number | null;
    editor: ReactNode;
    addChild: (id: number) => void;
  };
}) {
  const isGroup = node.node_type === "GROUP";
  const expandable = node.children.length > 0;
  const open = !controls.collapsed.includes(node.id);
  const editing = controls.editId === node.id;
  const saved = controls.savedId === node.id;
  const ruleLabels = {
    BOOLEAN_REPEAT: messages.steps.booleanRepeat,
    BOOLEAN_DAILY_CUSTOM: messages.steps.booleanCustom,
    NUMERIC_AUTO_DISTRIBUTE: messages.steps.numericAuto,
    NUMERIC_DAILY_MANUAL: messages.steps.numericManual,
  };

  return (
    <li className="plan-step-branch">
      <div
        id={`plan-step-row-${node.id}`}
        className="plan-step-row"
        data-kind={node.node_type}
        data-feedback={editing ? "editing" : saved ? "saved" : undefined}
      >
        <div className="plan-step-row-heading">
          {expandable && (
            <button
              type="button"
              className="plan-step-disclosure"
              aria-expanded={open}
              aria-controls={open ? `plan-step-children-${node.id}` : undefined}
              aria-label={node.name}
              onClick={() => controls.toggle(node.id)}
            ><ChevronDown size={15} aria-hidden="true" /></button>
          )}
          <strong>{node.name}</strong>
          <span>
            {isGroup
              ? messages.steps.groupNode
              : ruleLabels[getRuleMode(node)]}
          </span>
          {editing && <span className="plan-step-row-feedback">{messages.steps.editInProgress}</span>}
          {saved && <span role="status" className="plan-step-row-feedback">{messages.steps.rowSaved}</span>}
        </div>

        {canEdit && (
          <div className="plan-step-row-actions">
            {isGroup && (
              <button type="button" onClick={() => controls.addChild(node.id)}>{messages.steps.addChild}</button>
            )}
            {node.node_type === "LEAF" && (
              <button
                type="button"
                onClick={() => onEditRule(node)}
              >{messages.steps.editRule}</button>
            )}

            <details className="plan-step-row-menu">
              <summary aria-label={`${node.name} · ${messages.plans.moreActions}`}>
                <Ellipsis size={16} aria-hidden="true" />
              </summary>
              <div>
                <button type="button" onClick={(event) => {
                  event.currentTarget.closest("details")?.removeAttribute("open");
                  onRename(node);
                }}>{messages.steps.rename}</button>
                <button type="button" className="is-danger" onClick={(event) => {
                  event.currentTarget.closest("details")?.removeAttribute("open");
                  onDelete(node);
                }}>{messages.steps.deleteNode}</button>
              </div>
            </details>
          </div>
        )}
      </div>
      {editing && controls.editor}

      {expandable && open && (
        <ul id={`plan-step-children-${node.id}`} className="plan-step-children">
          {node.children.map((child) => (
            <TreeItem
              key={child.id}
              node={child}
              canEdit={canEdit}
              onRename={onRename}
              onEditRule={onEditRule}
              onDelete={onDelete}
              controls={controls}
            />
          ))}
        </ul>
      )}
    </li>
  );
}


export function StepTreeEditor({
  planId,
  status,
  onChanged,
}: Props) {
  const canEdit = status === "DRAFT";

  const [tree, setTree] = useState<StepNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);

  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [creationSuccessOpen, setCreationSuccessOpen] = useState(false);
  const [collapsed, setCollapsed] = useState<number[]>([]);
  const [savedId, setSavedId] = useState<number | null>(null);
  const [revealId, setRevealId] = useState<number | null>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const editScroll = useRef(0);
  const restoredKey = useRef("");
  const stateKey = `plan-steps:${planId}`;
  const scrollKey = `${stateKey}:editor:scroll`;

  // 创建节点表单
  const [nodeType, setNodeType] = useState<"LEAF" | "GROUP">(
    "LEAF",
  );
  const [parentId, setParentId] = useState("");
  const [name, setName] = useState("");
  const [firstLeafName, setFirstLeafName] = useState("");

  // 执行规则表单
  const [mode, setMode] =
    useState<RuleMode>("BOOLEAN_REPEAT");
  const [repeatContent, setRepeatContent] = useState("");
  const [totalText, setTotalText] = useState("0");

  // 修改名称
  const [renamingNode, setRenamingNode] =
    useState<StepNode | null>(null);
  const [renameText, setRenameText] = useState("");

  // 修改执行规则
  const [ruleNode, setRuleNode] =
    useState<StepNode | null>(null);

  const groups = useMemo(
    () => collectGroups(tree),
    [tree],
  );
  const stepCount = useMemo(() => countNodes(tree), [tree]);
  const editId = renamingNode?.id ?? ruleNode?.id;

  useEffect(() => {
    if (savedId === null) return;
    const timer = window.setTimeout(() => setSavedId(null), 2500);
    return () => window.clearTimeout(timer);
  }, [savedId]);

  useEffect(() => {
    const list = listRef.current;
    if (loading || !list) return;
    if (restoredKey.current !== scrollKey) {
      restoredKey.current = scrollKey;
      try {
        list.scrollTop = Number(sessionStorage.getItem(scrollKey)) || 0;
      } catch {
        // The list still works when storage is disabled.
      }
    }
    if (creationSuccessOpen || revealId === null) return;
    const row = document.getElementById(`plan-step-row-${revealId}`);
    if (!row || !list.contains(row)) return;
    const rowBounds = row.getBoundingClientRect();
    const listBounds = list.getBoundingClientRect();
    if (rowBounds.top < 0 || rowBounds.bottom > window.innerHeight) {
      row.scrollIntoView({ block: "nearest" });
    } else if (rowBounds.top < listBounds.top) {
      list.scrollTop += rowBounds.top - listBounds.top;
    } else if (rowBounds.bottom > listBounds.bottom) {
      list.scrollTop += rowBounds.bottom - listBounds.bottom;
    }
    const frame = requestAnimationFrame(() => setRevealId(null));
    return () => cancelAnimationFrame(frame);
  }, [creationSuccessOpen, loading, revealId, scrollKey, tree]);

  function updateCollapsed(next: number[]) {
    setCollapsed(next);
    try {
      sessionStorage.setItem(stateKey, JSON.stringify(next));
    } catch {
      // Collapse state still applies to the current view.
    }
  }

  function beginCreate(parent = "") {
    setError(null);
    setParentId(parent);
    setRenamingNode(null);
    setRuleNode(null);
    setCreateOpen(true);
    requestAnimationFrame(() => document.getElementById("step-name")?.focus());
  }


  useEffect(() => {
    if (!creationSuccessOpen) return;
    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setCreationSuccessOpen(false);
    }
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [creationSuccessOpen]);


  // 获取真实树形数据
  useEffect(() => {
    let cancelled = false;

    async function loadTree() {
      setLoading(true);
      setError(null);

      try {
        const result = await getPlanSteps(planId);

        if (!cancelled) {
          setTree(result);
          if (restoredKey.current !== scrollKey) {
            const parent = new URLSearchParams(window.location.search).get("parent");
            if (parent && collectGroups(result).some((group) => String(group.id) === parent)) {
              setParentId(parent);
              setCreateOpen(true);
            } else if (canEdit && result.length === 0) {
              setCreateOpen(true);
            }
            try {
              const stored = JSON.parse(sessionStorage.getItem(stateKey) ?? "[]");
              if (Array.isArray(stored)) setCollapsed(stored);
            } catch {
              // Storage is optional.
            }
          }
        }
      } catch (err) {
        if (!cancelled) {
          setTree([]);
          setError(getErrorText(err));
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
  }, [canEdit, planId, revision, scrollKey, stateKey]);


  // 统一处理修改操作
  async function runAction(
    action: () => Promise<void>,
    successMessage: string,
  ): Promise<boolean> {
    if (busy) {
      return false;
    }

    setBusy(true);
    setError(null);
    setNotice(null);

    try {
      await action();

      setNotice(successMessage || null);
      setRevision((value) => value + 1);
      onChanged?.();

      return true;
    } catch (err) {
      setError(getErrorText(err));
      return false;
    } finally {
      setBusy(false);
    }
  }


  // 创建 GROUP 或 LEAF
  async function handleCreate(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();

    const cleanedName = name.trim();

    if (!cleanedName) {
      setError(messages.steps.nameRequired);
      return;
    }

    try {
      const rule = buildStepRule(
        mode,
        repeatContent,
        totalText,
      );

      const parent =
        parentId === "" ? null : Number(parentId);

      let payload: StepCreate;

      if (nodeType === "LEAF") {
        payload = {
          name: cleanedName,
          node_type: "LEAF",
          parent_id: parent,
          rule,
        };
      } else {
        const childName = firstLeafName.trim();

        if (!childName) {
          setError(messages.steps.groupNeedsLeaf);
          return;
        }

        payload = {
          name: cleanedName,
          node_type: "GROUP",
          parent_id: parent,
          children: [
            {
              name: childName,
              node_type: "LEAF",
              rule,
            },
          ],
        };
      }

      let createdId = 0;
      const success = await runAction(
        async () => { createdId = await createStep(planId, payload); },
        "",
      );

      if (success) {
        if (parent !== null) {
          const path = findStepPath(tree, parent);
          updateCollapsed(collapsed.filter((id) => !path.includes(id)));
        }
        setRevealId(createdId);
        setName("");
        setFirstLeafName("");
        setCreationSuccessOpen(true);
      }
    } catch (err) {
      setError(getErrorText(err));
    }
  }


  function beginRename(node: StepNode) {
    editScroll.current = listRef.current?.scrollTop ?? 0;
    setError(null);
    setSavedId(null);
    setCreateOpen(false);
    setRuleNode(null);
    setRenamingNode(node);
    setRenameText(node.name);
    requestAnimationFrame(() => document.getElementById("step-rename")?.focus());
  }


  async function handleRename(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();

    if (!renamingNode) {
      return;
    }

    const value = renameText.trim();

    if (!value) {
      setError(messages.steps.emptyName);
      return;
    }

    const success = await runAction(
      () => updateStep(
        planId,
        renamingNode.id,
        { name: value },
      ),
      messages.steps.renamed,
    );

    if (success) {
      setSavedId(renamingNode.id);
      closeEditor();
    }
  }


  function beginEditRule(node: StepNode) {
    editScroll.current = listRef.current?.scrollTop ?? 0;
    setError(null);
    setSavedId(null);
    setCreateOpen(false);
    setRenamingNode(null);
    setRuleNode(node);

    setMode(getRuleMode(node));
    setRepeatContent(node.repeat_content ?? "");
    setTotalText(String(node.total_target ?? 0));
    requestAnimationFrame(() => document.getElementById("rule-mode")?.focus());
  }


  async function handleUpdateRule(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();

    if (!ruleNode) {
      return;
    }

    try {
      const rule = buildStepRule(
        mode,
        repeatContent,
        totalText,
      );

      const success = await runAction(
        () => updateStepRule(planId, ruleNode.id, rule),
        messages.steps.ruleUpdated,
      );

      if (success) {
        setSavedId(ruleNode.id);
        closeEditor();
      }
    } catch (err) {
      setError(getErrorText(err));
    }
  }

  function closeEditor() {
    setError(null);
    setRenamingNode(null);
    setRuleNode(null);
    const previousScroll = editScroll.current;
    requestAnimationFrame(() => {
      if (listRef.current) listRef.current.scrollTop = previousScroll;
    });
  }

  async function handleDelete(node: StepNode) {
    const confirmed = window.confirm(
      messages.steps.deleteConfirm(node.name),
    );

    if (!confirmed) {
      return;
    }

    const success = await runAction(
      () => deleteStep(planId, node.id),
      messages.steps.deleted,
    );

    if (success) {
      setRenamingNode(null);
      setRuleNode(null);
    }
  }


  const editor = renamingNode ? (
    <form onSubmit={handleRename} className="plan-step-editor">
      <h3>{messages.steps.renameTitle(renamingNode.name)}</h3>
      {error && <p role="alert" className="plan-step-feedback is-error">{error}</p>}
      <label htmlFor="step-rename">{messages.steps.nodeName}</label>
      <input id="step-rename" value={renameText} onChange={(event) => setRenameText(event.target.value)} maxLength={100} />
      <div className="plan-step-editor-actions"><button type="submit" disabled={busy}>{messages.steps.saveName}</button><button type="button" className="is-secondary" disabled={busy} onClick={closeEditor}>{messages.common.cancel}</button></div>
    </form>
  ) : ruleNode ? (
    <form onSubmit={handleUpdateRule} className="plan-step-editor">
      <h3>{messages.steps.editRuleTitle(ruleNode.name)}</h3>
      {error && <p role="alert" className="plan-step-feedback is-error">{error}</p>}
      <p className="plan-step-warning">{messages.steps.ruleChangeWarning}</p>
      <StepRuleFields mode={mode} onModeChange={setMode} repeatContent={repeatContent} onRepeatContentChange={setRepeatContent} totalText={totalText} onTotalTextChange={setTotalText} />
      <div className="plan-step-editor-actions"><button type="submit" disabled={busy}>{messages.steps.saveRule}</button><button type="button" className="is-secondary" disabled={busy} onClick={closeEditor}>{messages.common.cancel}</button></div>
    </form>
  ) : null;

  return (
    <>
      <section id="plan-steps" className="plan-step-card plan-draft-step-card">
        <header className="plan-step-card-header">
          <div>
            <h2>{messages.steps.title}</h2>
            <p>{messages.steps.stepCount(stepCount)}</p>
          </div>
          <div className="plan-step-header-actions">
            <button type="button" className="plan-step-refresh" onClick={() => setRevision((value) => value + 1)} disabled={loading || busy} aria-label={messages.steps.refresh}><RefreshCw size={16} aria-hidden="true" /></button>
            {canEdit && (
              <button type="button" className="plan-step-add" onClick={() => createOpen ? setCreateOpen(false) : beginCreate()}><span>{createOpen ? <ChevronUp size={16} /> : <Plus size={16} />}</span>{createOpen ? messages.steps.collapseCreate : messages.steps.addStep}</button>
            )}
          </div>
        </header>

        {error && editId === undefined && <p role="alert" className="plan-step-feedback is-error">{error}</p>}
        {notice && <p role="status" className="plan-step-feedback is-success">{notice}</p>}

        {canEdit && createOpen ? (
          <form onSubmit={handleCreate} className="plan-step-editor">
            <h3>{messages.steps.createTitle}</h3>
            <p className="plan-step-create-target">{messages.steps.addTo(groups.find((group) => String(group.id) === parentId)?.name ?? messages.steps.rootNode)}</p>
            <div className="plan-step-form-grid">
              <div><label htmlFor="step-parent">{messages.steps.parentLabel}</label><select id="step-parent" value={parentId} onChange={(event) => setParentId(event.target.value)}><option value="">{messages.steps.rootNode}</option>{groups.map((group) => <option key={group.id} value={group.id}>{group.label}</option>)}</select></div>
              <div><label htmlFor="step-type">{messages.steps.nodeType}</label><select id="step-type" value={nodeType} onChange={(event) => setNodeType(event.target.value as "LEAF" | "GROUP")}><option value="LEAF">{messages.steps.leafType}</option><option value="GROUP">{messages.steps.groupWithLeaf}</option></select></div>
              <div className="plan-step-form-wide"><label htmlFor="step-name">{nodeType === "GROUP" ? messages.steps.groupName : messages.steps.leafName}</label><input id="step-name" value={name} onChange={(event) => setName(event.target.value)} maxLength={100} required /></div>
              {nodeType === "GROUP" && <div className="plan-step-form-wide"><label htmlFor="step-first-leaf">{messages.steps.firstLeafNameLabel}</label><input id="step-first-leaf" value={firstLeafName} onChange={(event) => setFirstLeafName(event.target.value)} maxLength={100} required /></div>}
            </div>
            <StepRuleFields mode={mode} onModeChange={setMode} repeatContent={repeatContent} onRepeatContentChange={setRepeatContent} totalText={totalText} onTotalTextChange={setTotalText} />
            <div className="plan-step-editor-actions"><button type="submit" disabled={busy}><Plus size={16} aria-hidden="true" />{busy ? messages.common.submitting : messages.steps.create}</button></div>
          </form>
        ) : !canEdit ? <p className="plan-step-readonly">{messages.steps.readOnlyHint}</p> : null}

        <div className="plan-step-tree-section" aria-busy={loading}>
          {tree.length === 0 ? (
            <p className="plan-step-empty">{loading ? messages.steps.loadingFull : messages.steps.emptyCurrentPlanSentence}</p>
          ) : (
            <ul
              className="plan-step-tree"
              ref={listRef}
              onScroll={(event) => {
                try {
                  sessionStorage.setItem(scrollKey, String(event.currentTarget.scrollTop));
                } catch {
                  // Scrolling does not depend on storage.
                }
              }}
            >
              {tree.map((node) => (
                <TreeItem
                  key={node.id}
                  node={node}
                  canEdit={canEdit && !busy && !loading}
                  onRename={beginRename}
                  onEditRule={beginEditRule}
                  onDelete={handleDelete}
                  controls={{
                    collapsed,
                    toggle: (id) => updateCollapsed(collapsed.includes(id) ? collapsed.filter((item) => item !== id) : [...collapsed, id]),
                    editId,
                    savedId,
                    editor,
                    addChild: (id) => beginCreate(String(id)),
                  }}
                />
              ))}
            </ul>
          )}
        </div>
      </section>

      {creationSuccessOpen && (
        <div className="plan-step-success-backdrop">
          <section className="plan-step-success-dialog" role="dialog" aria-modal="true" aria-labelledby="step-success-title">
            <button type="button" className="plan-step-success-close" onClick={() => setCreationSuccessOpen(false)} aria-label={messages.steps.closeCreatedDialog}><X size={20} /></button>
            <span className="plan-step-success-mark" aria-hidden="true"><CheckCircle2 size={34} /></span>
            <h2 id="step-success-title">{messages.steps.createdDialogTitle}</h2>
            <p>{messages.steps.createdDialogDescription}</p>
            <button type="button" className="plan-step-success-action" onClick={() => setCreationSuccessOpen(false)} autoFocus>{messages.steps.continueAdding}</button>
          </section>
        </div>
      )}
    </>
  );
}
