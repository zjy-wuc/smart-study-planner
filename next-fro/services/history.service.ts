import { apiFetch } from "@/lib/api/client";
import type { ApiResponse } from "@/types/api";
import type {
  CheckinRecord,
  CheckinSummary,
  HistoryPage,
  ReviewRecord,
} from "@/types/history";

export type HistoryRange = 7 | 30 | "all";

export async function getCheckinSummary(): Promise<CheckinSummary> {
  return (
    await apiFetch<ApiResponse<CheckinSummary>>("/history/checkin-summary")
  ).data;
}

export async function getCheckins(
  range: HistoryRange,
  page: number,
  planId: number | null,
): Promise<HistoryPage<CheckinRecord>> {
  const query = new URLSearchParams({
    days: String(range),
    page: String(page),
    page_size: "20",
  });
  if (planId !== null) query.set("plan_id", String(planId));
  return (
    await apiFetch<ApiResponse<HistoryPage<CheckinRecord>>>(
      `/history/checkins?${query}`,
    )
  ).data;
}

export async function getReviewHistory(
  page: number,
): Promise<HistoryPage<ReviewRecord>> {
  return (
    await apiFetch<ApiResponse<HistoryPage<ReviewRecord>>>(
      `/history/reviews?page=${page}&page_size=20`,
    )
  ).data;
}
