import { apiFetch } from "@/lib/api/client";

import type { ApiResponse } from "@/types/api";
import type {
  FocusHistory,
  FocusSession,
  FocusStart,
  FocusStatistics,
  FocusSyncResult,
} from "@/types/focus";

export async function startFocus(data: FocusStart): Promise<FocusSession> {
  const response = await apiFetch<ApiResponse<FocusSession>>("/focus/sessions", {
    method: "POST",
    body: JSON.stringify(data),
  });
  return response.data;
}

export async function syncFocus(): Promise<FocusSyncResult> {
  const response = await apiFetch<ApiResponse<FocusSyncResult>>("/focus/sync", {
    method: "POST",
  });
  return response.data;
}

async function operateFocus(sessionId: number, action: "pause" | "resume" | "finish" | "cancel") {
  const response = await apiFetch<ApiResponse<FocusSession>>(
    `/focus/sessions/${sessionId}/${action}`,
    { method: "POST" },
  );
  return response.data;
}

export const pauseFocus = (sessionId: number) => operateFocus(sessionId, "pause");
export const resumeFocus = (sessionId: number) => operateFocus(sessionId, "resume");
export const finishFocus = (sessionId: number) => operateFocus(sessionId, "finish");
export const cancelFocus = (sessionId: number) => operateFocus(sessionId, "cancel");

export async function getFocusHistory(page = 1, pageSize = 3): Promise<FocusHistory> {
  const response = await apiFetch<ApiResponse<FocusHistory>>(
    `/focus/sessions?page=${page}&page_size=${pageSize}`,
  );
  return response.data;
}

export async function getFocusStatistics(days: 7 | 30): Promise<FocusStatistics> {
  const response = await apiFetch<ApiResponse<FocusStatistics>>(`/focus/statistics?days=${days}`);
  return response.data;
}
