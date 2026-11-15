
import { apiFetch } from "@/lib/api/client";
import type { ApiResponse } from "@/types/api";
import type { DailyTask } from "@/types/task";


import type {
  PlanTask,
  TaskType,
  TaskStatus,
  ActiveTaskUpdate,
} from "@/types/task";


export async function listTodayTasks(): Promise<DailyTask[]> {
  const result =
    await apiFetch<ApiResponse<DailyTask[]>>(
      "/tasks/today",
    );

  return result.data;
}



import type {
  StudyRecord,
  RolloverRequest,
  RolloverResult,
} from "@/types/task";


// BOOLEAN：确认完成
export async function completeBooleanTask(
  taskId: number,
): Promise<void> {
  await apiFetch<ApiResponse<unknown>>(
    `/tasks/${taskId}/complete`,
    { method: "POST" },
  );
}


// NUMERIC：提交累计完成数量
export async function updateNumericTask(
  taskId: number,
  actualQuantity: number,
): Promise<void> {
  await apiFetch<ApiResponse<unknown>>(
    `/tasks/${taskId}/progress`,
    {
      method: "PUT",
      body: JSON.stringify({
        actual_quantity: actualQuantity,
      }),
    },
  );
}


// 将未完成任务顺延到指定日期
export async function rolloverTask(
  taskId: number,
  data: RolloverRequest,
): Promise<RolloverResult> {
  const result =
    await apiFetch<ApiResponse<RolloverResult>>(
      `/tasks/${taskId}/rollover`,
      {
        method: "POST",
        body: JSON.stringify(data),
      },
    );

  return result.data;
}


// 获取打卡历史
export async function getTaskRecords(
  taskId: number,
): Promise<StudyRecord[]> {
  const response =
    await apiFetch<ApiResponse<unknown>>(
      `/tasks/${taskId}/records`,
    );

  const data = response.data;

  // 兼容数组和 { records: [...] } 两种结构。
  // 若真实响应不是其中之一，明确报错。
  if (Array.isArray(data)) {
    return data as StudyRecord[];
  }

  if (
    data !== null &&
    typeof data === "object" &&
    "records" in data &&
    Array.isArray(data.records)
  ) {
    return data.records as StudyRecord[];
  }

  throw new Error(
    "打卡历史响应格式不符合预期，请核对后端接口",
  );
}



// 查询指定计划的全部有效任务
export async function listPlanTasks(
  planId: number,
): Promise<PlanTask[]> {
  const response =
    await apiFetch<ApiResponse<PlanTask[]>>(
      `/plans/${planId}/tasks`,
    );

  return response.data;
}

// 读取完整任务详情
export async function getTask(
  taskId: number,
): Promise<DailyTask> {
  const response =
    await apiFetch<ApiResponse<DailyTask>>(
      `/tasks/${taskId}`,
    );

  return response.data;
}

// 修改符合条件的未来任务
export async function updateFutureTask(
  taskId: number,
  data: ActiveTaskUpdate,
): Promise<void> {
  await apiFetch<ApiResponse<unknown>>(
    `/tasks/${taskId}`,
    {
      method: "PATCH",
      body: JSON.stringify(data),
    },
  );
}

// 逻辑删除任务
export async function deleteTask(
  taskId: number,
): Promise<void> {
  await apiFetch<ApiResponse<unknown>>(
    `/tasks/${taskId}`,
    {
      method: "DELETE",
    },
  );
}