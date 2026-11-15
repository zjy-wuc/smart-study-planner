
import { apiFetch } from "@/lib/api/client";
import type { ApiResponse } from "@/types/api";
import type { DailyTask } from "@/types/task";

export async function listTodayTasks(): Promise<DailyTask[]> {
  const result =
    await apiFetch<ApiResponse<DailyTask[]>>(
      "/tasks/today",
    );

  return result.data;
}
