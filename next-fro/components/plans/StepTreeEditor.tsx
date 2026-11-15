
"use client";

import {
  useEffect,
  useMemo,
  useState,
  type FormEvent,
} from "react";

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
};

type GroupOption = {
  id: number;
  label: string;
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
      label: `${"— ".repeat(depth)}${node.name}`,
    });

    result.push(
      ...collectGroups(node.children, depth + 1),
    );
  }

  return result;
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
    : "操作失败，请重试";
}


function TreeItem({
  node,
  canEdit,
  onRename,
  onEditRule,
  onDelete,
}: {
  node: StepNode;
  canEdit: boolean;
  onRename: (node: StepNode) => void;
  onEditRule: (node: StepNode) => void;
  onDelete: (node: StepNode) => void;
}) {
  return (
    <li className="my-3">
      <div className="rounded border border-slate-200 p-3">
        <div className="flex flex-wrap items-center gap-3">
          <strong>{node.name}</strong>

          <span className="text-sm text-slate-500">
            {node.node_type === "GROUP"
              ? "分类节点"
              : `${node.task_type} · ${node.schedule_mode}`}
          </span>
        </div>

        {canEdit && (
          <div className="mt-3 flex flex-wrap gap-3 text-sm">
            <button
              type="button"
              onClick={() => onRename(node)}
              className="text-blue-700"
            >
              修改名称
            </button>

            {node.node_type === "LEAF" && (
              <button
                type="button"
                onClick={() => onEditRule(node)}
                className="text-blue-700"
              >
                修改规则
              </button>
            )}

            <button
              type="button"
              onClick={() => onDelete(node)}
              className="text-red-700"
            >
              删除节点
            </button>
          </div>
        )}
      </div>

      {node.children.length > 0 && (
        <ul className="ml-5 border-l border-slate-200 pl-4">
          {node.children.map((child) => (
            <TreeItem
              key={child.id}
              node={child}
              canEdit={canEdit}
              onRename={onRename}
              onEditRule={onEditRule}
              onDelete={onDelete}
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
}: Props) {
  const canEdit = status === "DRAFT";

  const [tree, setTree] = useState<StepNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);

  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

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
  }, [planId, revision]);


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

      setNotice(successMessage);
      setRevision((value) => value + 1);

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
      setError("请输入节点名称");
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
          setError("创建 GROUP 时必须填写第一个叶子节点");
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

      const success = await runAction(
        () => createStep(planId, payload),
        "学习步骤创建成功",
      );

      if (success) {
        setName("");
        setFirstLeafName("");
      }
    } catch (err) {
      setError(getErrorText(err));
    }
  }


  function beginRename(node: StepNode) {
    setRuleNode(null);
    setRenamingNode(node);
    setRenameText(node.name);
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
      setError("节点名称不能为空");
      return;
    }

    const success = await runAction(
      () => updateStep(
        planId,
        renamingNode.id,
        { name: value },
      ),
      "节点名称修改成功",
    );

    if (success) {
      setRenamingNode(null);
    }
  }


  function beginEditRule(node: StepNode) {
    setRenamingNode(null);
    setRuleNode(node);

    setMode(getRuleMode(node));
    setRepeatContent(node.repeat_content ?? "");
    setTotalText(String(node.total_target ?? 0));
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
        "执行规则修改成功",
      );

      if (success) {
        setRuleNode(null);
      }
    } catch (err) {
      setError(getErrorText(err));
    }
  }


  async function handleDelete(node: StepNode) {
    const confirmed = window.confirm(
      `确定删除「${node.name}」吗？\n` +
      "该节点及其后代都会被逻辑删除。",
    );

    if (!confirmed) {
      return;
    }

    const success = await runAction(
      () => deleteStep(planId, node.id),
      "节点删除成功",
    );

    if (success) {
      setRenamingNode(null);
      setRuleNode(null);
    }
  }


  return (
    <section className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">
          学习步骤
        </h2>

        <button
          type="button"
          onClick={() =>
            setRevision((value) => value + 1)
          }
          disabled={loading || busy}
          className="text-sm text-blue-700"
        >
          刷新步骤
        </button>
      </div>

      {error && (
        <p role="alert" className="text-red-600">
          {error}
        </p>
      )}

      {notice && (
        <p role="status" className="text-green-700">
          {notice}
        </p>
      )}

      {loading ? (
        <p>正在加载学习步骤...</p>
      ) : tree.length === 0 ? (
        <p className="text-slate-500">
          当前计划还没有学习步骤。
        </p>
      ) : (
        <ul>
          {tree.map((node) => (
            <TreeItem
              key={node.id}
              node={node}
              canEdit={canEdit && !busy}
              onRename={beginRename}
              onEditRule={beginEditRule}
              onDelete={handleDelete}
            />
          ))}
        </ul>
      )}

      {canEdit && renamingNode && (
        <form
          onSubmit={handleRename}
          className="space-y-3 rounded border p-4"
        >
          <h3 className="font-semibold">
            修改名称：{renamingNode.name}
          </h3>

          <input
            value={renameText}
            onChange={(event) =>
              setRenameText(event.target.value)
            }
            maxLength={100}
            className="w-full rounded border p-2"
          />

          <div className="flex gap-3">
            <button
              type="submit"
              disabled={busy}
              className="text-blue-700"
            >
              保存名称
            </button>

            <button
              type="button"
              onClick={() => setRenamingNode(null)}
            >
              取消
            </button>
          </div>
        </form>
      )}

      {canEdit && ruleNode ? (
        <form
          onSubmit={handleUpdateRule}
          className="space-y-4 rounded border p-4"
        >
          <h3 className="font-semibold">
            修改规则：{ruleNode.name}
          </h3>

          <p className="text-sm text-amber-700">
            修改执行规则会清除该叶子原有的草稿每日安排。
            如需自定义安排，修改后应重新填写。
          </p>

          <StepRuleFields
            mode={mode}
            onModeChange={setMode}
            repeatContent={repeatContent}
            onRepeatContentChange={setRepeatContent}
            totalText={totalText}
            onTotalTextChange={setTotalText}
          />

          <div className="flex gap-3">
            <button
              type="submit"
              disabled={busy}
              className="text-blue-700"
            >
              保存规则
            </button>

            <button
              type="button"
              onClick={() => setRuleNode(null)}
            >
              取消
            </button>
          </div>
        </form>
      ) : canEdit ? (
        <form
          onSubmit={handleCreate}
          className="space-y-4 rounded border p-5"
        >
          <h3 className="text-lg font-semibold">
            新增学习步骤
          </h3>

          <div>
            <label className="mb-1 block">
              新增位置
            </label>

            <select
              value={parentId}
              onChange={(event) =>
                setParentId(event.target.value)
              }
              className="w-full rounded border p-2"
            >
              <option value="">
                顶层节点
              </option>

              {groups.map((group) => (
                <option
                  key={group.id}
                  value={group.id}
                >
                  {group.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1 block">
              节点类型
            </label>

            <select
              value={nodeType}
              onChange={(event) =>
                setNodeType(
                  event.target.value as "LEAF" | "GROUP",
                )
              }
              className="w-full rounded border p-2"
            >
              <option value="LEAF">
                LEAF · 学习项目
              </option>

              <option value="GROUP">
                GROUP · 分类（同时创建首个叶子）
              </option>
            </select>
          </div>

          <div>
            <label className="mb-1 block">
              {nodeType === "GROUP"
                ? "分类名称"
                : "学习项目名称"}
            </label>

            <input
              value={name}
              onChange={(event) =>
                setName(event.target.value)
              }
              maxLength={100}
              required
              className="w-full rounded border p-2"
            />
          </div>

          {nodeType === "GROUP" && (
            <div>
              <label className="mb-1 block">
                第一个叶子的名称
              </label>

              <input
                value={firstLeafName}
                onChange={(event) =>
                  setFirstLeafName(event.target.value)
                }
                maxLength={100}
                required
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

          <button
            type="submit"
            disabled={busy}
            className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
          >
            {busy ? "正在提交..." : "创建步骤"}
          </button>
        </form>
      ) : (
        <p className="text-sm text-slate-500">
          当前计划不处于草稿状态，已有步骤仅供查看。
        </p>
      )}
    </section>
  );
}
