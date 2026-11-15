
"use client";

import { useEffect, useState } from "react";

import { getPlanSteps } from "@/services/steps.service";
import type { Plan } from "@/types/plan";
import type { StepNode } from "@/types/step";


function StepBranch({
  node,
}: {
  node: StepNode;
}) {
  return (
    <li className="my-2">
      <div className="flex items-center gap-2">
        <span className="text-xs text-slate-500">
          {node.node_type === "GROUP" ? "分类" : "任务"}
        </span>

        <span>{node.name}</span>
      </div>

      {node.children.length > 0 && (
        <ul className="ml-4 border-l border-slate-200 pl-3">
          {node.children.map((child) => (
            <StepBranch key={child.id} node={child} />
          ))}
        </ul>
      )}
    </li>
  );
}


export function StepPreview({
  plans,
}: {
  plans: Plan[];
}) {
  const [selectedPlanId, setSelectedPlanId] =
    useState<number | null>(null);

  const [nodes, setNodes] = useState<StepNode[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 计划列表改变时，保证当前选中的计划依然存在
  useEffect(() => {
    setSelectedPlanId((current) => {
      if (plans.length === 0) {
        return null;
      }

      if (
        current !== null &&
        plans.some((plan) => plan.id === current)
      ) {
        return current;
      }

      return plans[0].id;
    });
  }, [plans]);

  useEffect(() => {
    if (selectedPlanId === null) {
      setNodes([]);
      setError(null);
      return;
    }

    let cancelled = false;

    async function loadSteps() {
      setLoading(true);
      setError(null);
      setNodes([]);

      try {
        const result = await getPlanSteps(selectedPlanId!);

        if (!cancelled) {
          setNodes(result);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "获取学习步骤失败",
          );
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadSteps();

    return () => {
      cancelled = true;
    };
  }, [selectedPlanId]);

  if (plans.length === 0) {
    return (
      <p className="py-6 text-sm text-slate-500">
        创建计划后，这里将显示学习步骤。
      </p>
    );
  }

  return (
    <div>
      <label
        htmlFor="preview-plan"
        className="mb-2 block text-sm text-slate-600"
      >
        选择学习计划
      </label>

      <select
        id="preview-plan"
        value={selectedPlanId ?? ""}
        onChange={(event) => {
          setSelectedPlanId(Number(event.target.value));
        }}
        className="w-full rounded-lg border border-slate-300 px-3 py-2"
      >
        {plans.map((plan) => (
          <option key={plan.id} value={plan.id}>
            {plan.name}
          </option>
        ))}
      </select>

      {loading ? (
        <p className="mt-4 text-sm">正在加载步骤...</p>
      ) : error ? (
        <p role="alert" className="mt-4 text-sm text-red-600">
          {error}
        </p>
      ) : nodes.length === 0 ? (
        <p className="mt-4 text-sm text-slate-500">
          当前计划还没有学习步骤
        </p>
      ) : (
        <ul className="mt-4">
          {nodes.map((node) => (
            <StepBranch key={node.id} node={node} />
          ))}
        </ul>
      )}
    </div>
  );
}
