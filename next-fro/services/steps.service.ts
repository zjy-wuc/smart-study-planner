
import { apiFetch } from "@/lib/api/client";
import type { ApiResponse } from "@/types/api";
import type { StepNode } from "@/types/step";

export async function getPlanSteps(
  planId: number,
): Promise<StepNode[]> {
  const result =
    await apiFetch<ApiResponse<StepNode[]>>(
      `/plans/${planId}/steps`,
    );

  return result.data;
}
