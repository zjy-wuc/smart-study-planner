//curd 操作
import { apiFetch } from "@/lib/api/client";
import type { ApiResponse } from "@/types/api";
import type { Plan } from "@/types/plan";

import type {
  PlanCreate,
  PlanUpdate,
} from "@/types/plan";



export async function listPlans(): Promise<Plan[]> {
  const result =
    await apiFetch<ApiResponse<Plan[]>>("/plans");

  return result.data;
}


// 获取一个学习计划
export async function getPlan(
  planId: number,
): Promise<Plan> {
  const result = await apiFetch<ApiResponse<Plan>>(
    `/plans/${planId}`,
  );

  return result.data;
}


// 创建学习计划
export async function createPlan(
  data: PlanCreate,
): Promise<Plan> {
  const result = await apiFetch<ApiResponse<Plan>>(
    "/plans",
    {
      method: "POST",
      body: JSON.stringify(data),
    },
  );

  return result.data;
}


// 修改学习计划
export async function updatePlan(
  planId: number,
  data: PlanUpdate,
): Promise<Plan> {
  const result = await apiFetch<ApiResponse<Plan>>(
    `/plans/${planId}`,
    {
      method: "PATCH",
      body: JSON.stringify(data),
    },
  );

  return result.data;
}


// 删除学习计划
export async function deletePlan(
  planId: number,
): Promise<void> {
  await apiFetch<ApiResponse<unknown>>(
    `/plans/${planId}`,
    {
      method: "DELETE",
    },
  );
}