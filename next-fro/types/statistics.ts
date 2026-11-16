
export type TrendDays = 7 | 30;

export type CheckinStatistics = {
  total_count: number;
  last_7_days_count: number;
  last_30_days_count: number;
  current_streak_days: number;
};

export type PlanStatistics = {
  active_count: number;
  ended_count: number;
};

export type DailyCheckinTrend = {
  date: string;
  checkin_count: number;
};

export type StatisticsOverview = {
  as_of_date: string;
  checkins: CheckinStatistics;
  plans: PlanStatistics;
  trend_days: TrendDays;
  daily_trend: DailyCheckinTrend[];
};
