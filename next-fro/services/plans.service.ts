//curd 操作
import { apiFetch } from "@/lib/api/client";
import type { ApiResponse } from "@/types/api";
import type { Plan, EndPlanResult } from "@/types/plan";

export type StartPlanResult = {
  plan_id: number;
  status: "ACTIVE";
  generated_count: number;
  start_date: string;
  end_date: string;
};



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

// 启动草稿，并让后端生成全周期每日任务
export async function startPlan(
  planId: number,
): Promise<StartPlanResult> {
  const result =
    await apiFetch<ApiResponse<StartPlanResult>>(
      `/plans/${planId}/start`,
      {
        method: "POST",
      },
    );

  return result.data;
}

/**
 * 结束执行中的学习计划。
 *
 * 后端负责：
 * 1. 校验计划归属和 ACTIVE 状态
 * 2. 区分 EARLY / NORMAL_EXPIRED
 * 3. 处理任务状态或逻辑删除
 * 4. 在事务内更新计划状态
 */
export async function endPlan(
  planId: number,
): Promise<EndPlanResult> {
  const response =
    await apiFetch<ApiResponse<EndPlanResult>>(
      `/plans/${planId}/end`,
      {
        method: "POST",
      },
    );

  return response.data;
}
