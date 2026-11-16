
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
    <li className="workspace-step-branch">
      <div className="workspace-step-row" data-kind={node.node_type}>
        <span className="workspace-step-kind">
          {node.node_type === "GROUP" ? "分类" : "任务"}
        </span>

        <span>{node.name}</span>
      </div>

      {node.children.length > 0 && (
        <ul className="workspace-step-children">
          {node.children.map((child) => (
            <StepBranch key={child.id} node={child} />
          ))}
        </ul>
      )}
    </li>
  );
}


function StepTree({ planId }: { planId: number }) {
  const [nodes, setNodes] = useState<StepNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadSteps() {
      try {
        const result = await getPlanSteps(planId);

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
  }, [planId]);

  if (loading) return <p role="status" className="workspace-loading">正在加载步骤...</p>;
  if (error) return <p role="alert" className="workspace-feedback workspace-feedback--error">{error}</p>;
  if (nodes.length === 0) return <p className="workspace-empty-state">当前计划还没有学习步骤</p>;

  return (
    <ul className="workspace-step-tree">
      {nodes.map((node) => <StepBranch key={node.id} node={node} />)}
    </ul>
  );
}

export function StepPreview({ plans }: { plans: Plan[] }) {
  const [selectedPlanId, setSelectedPlanId] = useState<number | null>(null);
  const activePlanId = plans.some((plan) => plan.id === selectedPlanId)
    ? selectedPlanId
    : plans[0]?.id ?? null;

  if (plans.length === 0) {
    return (
      <p className="workspace-empty-state">
        创建计划后，这里将显示学习步骤。
      </p>
    );
  }

  return (
    <div className="workspace-step-preview">
      <label
        htmlFor="preview-plan"
        className="workspace-field-label"
      >
        选择学习计划
      </label>

      <select
        id="preview-plan"
        value={activePlanId ?? ""}
        onChange={(event) => {
          setSelectedPlanId(Number(event.target.value));
        }}
        className="workspace-select"
      >
        {plans.map((plan) => (
          <option key={plan.id} value={plan.id}>
            {plan.name}
          </option>
        ))}
      </select>

      {activePlanId !== null && <StepTree key={activePlanId} planId={activePlanId} />}
    </div>
  );
}
