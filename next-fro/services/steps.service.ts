
import { apiFetch } from "@/lib/api/client";
import type { ApiResponse } from "@/types/api";
import type { StepNode,
  StepCreate,
  StepRule,
  StepUpdate,
 } from "@/types/step";

export async function getPlanSteps(
  planId: number,
): Promise<StepNode[]> {
  const result =
    await apiFetch<ApiResponse<StepNode[]>>(
      `/plans/${planId}/steps`,
    );

  return result.data;
}



// 新增学习步骤（支持一整棵子树）
export async function createStep(
  planId: number,
  data: StepCreate,
): Promise<void> {
  await apiFetch<ApiResponse<unknown>>(
    `/plans/${planId}/steps`,
    {
      method: "POST",
      body: JSON.stringify(data),
    },
  );
}

// 修改节点基本信息
export async function updateStep(
  planId: number,
  stepId: number,
  data: StepUpdate,
): Promise<void> {
  await apiFetch<ApiResponse<unknown>>(
    `/plans/${planId}/steps/${stepId}`,
    {
      method: "PATCH",
      body: JSON.stringify(data),
    },
  );
}

// 修改 LEAF 的执行规则
export async function updateStepRule(
  planId: number,
  stepId: number,
  data: StepRule,
): Promise<void> {
  await apiFetch<ApiResponse<unknown>>(
    `/plans/${planId}/steps/${stepId}/rule`,
    {
      method: "PUT",
      body: JSON.stringify(data),
    },
  );
}

// 删除节点及其后代
export async function deleteStep(
  planId: number,
  stepId: number,
): Promise<void> {
  await apiFetch<ApiResponse<unknown>>(
    `/plans/${planId}/steps/${stepId}`,
    {
      method: "DELETE",
    },
  );
}