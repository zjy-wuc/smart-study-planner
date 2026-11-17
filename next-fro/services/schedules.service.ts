import { messages } from "@/messages";

import { apiFetch } from "@/lib/api/client";

import type { ApiResponse } from "@/types/api";
import type {
  ScheduleEntry,
  ScheduleEntryInput,
} from "@/types/schedule";


// 后端 GET 的 data 包装结构需要兼容性检查，
// 不能在接口格式异常时假装返回空数组。
function parseScheduleEntries(
  value: unknown,
): ScheduleEntry[] {
  if (Array.isArray(value)) {
    return value as ScheduleEntry[];
  }

  if (
    value !== null &&
    typeof value === "object" &&
    "entries" in value &&
    Array.isArray(value.entries)
  ) {
    return value.entries as ScheduleEntry[];
  }

  throw new Error(
    messages.validation.scheduleResponse,
  );
}


// 读取某个叶子节点的草稿安排
export async function getSchedule(
  planId: number,
  stepId: number,
): Promise<ScheduleEntry[]> {
  const result = await apiFetch<ApiResponse<unknown>>(
    `/plans/${planId}/steps/${stepId}/schedule`,
  );

  return parseScheduleEntries(result.data);
}


// 整组替换某个叶子的草稿安排
export async function replaceSchedule(
  planId: number,
  stepId: number,
  entries: ScheduleEntryInput[],
): Promise<void> {
  await apiFetch<ApiResponse<unknown>>(
    `/plans/${planId}/steps/${stepId}/schedule`,
    {
      method: "PUT",
      body: JSON.stringify({ entries }),
    },
  );
}
