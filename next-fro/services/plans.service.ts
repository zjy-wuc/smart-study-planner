
import { apiFetch } from "@/lib/api/client";
import type { ApiResponse } from "@/types/api";
import type { Plan } from "@/types/plan";

export async function listPlans(): Promise<Plan[]> {
  const result =
    await apiFetch<ApiResponse<Plan[]>>("/plans");

  return result.data;
}
