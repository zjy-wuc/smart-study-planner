import { messages } from "@/messages";

import { apiFetch } from "@/lib/api/client";
import type { ApiResponse } from "@/types/api";
import type {
  StatisticsOverview,
  TrendDays,
} from "@/types/statistics";

// 获取学习统计中心全部数据
export async function getStatisticsOverview(
  days: TrendDays = 7,
): Promise<StatisticsOverview> {
  const response =
    await apiFetch<ApiResponse<StatisticsOverview>>(
      `/statistics/overview?days=${days}`,
    );

  const data = response.data;

  if (
    !data ||
    !data.checkins ||
    !data.plans ||
    !Array.isArray(data.daily_trend)
  ) {
    throw new Error(
      messages.validation.statisticsResponse,
    );
  }

  return data;
}
