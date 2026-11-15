
import { apiFetch } from "@/lib/api/client";
import type { ApiResponse } from "@/types/api";
import type { PlanProgress } from "@/types/progress";

export async function getPlanProgress(
  planId: number,
): Promise<PlanProgress> {
  const result =
    await apiFetch<ApiResponse<PlanProgress>>(
      `/plans/${planId}/progress`,
    );

  return result.data;
}
