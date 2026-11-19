export type FocusSessionType = "POMODORO" | "STOPWATCH";

export type FocusSessionStatus =
  | "RUNNING"
  | "PAUSED"
  | "COMPLETED"
  | "CANCELLED";

export type FocusSession = {
  id: number;
  user_id: number;
  plan_id: number | null;
  task_id: number | null;
  session_type: FocusSessionType;
  status: FocusSessionStatus;
  planned_seconds: number | null;
  focused_seconds: number;
  running_started_at: string | null;
  started_at: string;
  ended_at: string | null;
  focus_date: string;
  created_at: string;
  updated_at: string;
};

export type FocusStart = {
  session_type: FocusSessionType;
  planned_seconds: number | null;
  plan_id: number | null;
  task_id: number | null;
};

export type FocusSyncResult = {
  current: FocusSession | null;
  auto_completed: FocusSession | null;
};

export type FocusHistory = {
  items: FocusSession[];
  total: number;
  page: number;
  page_size: number;
};

export type FocusDailyStatistic = {
  date: string;
  focused_seconds: number;
  session_count: number;
  completed_pomodoros: number;
};

export type FocusStatisticSummary = {
  focused_seconds: number;
  session_count: number;
  completed_pomodoros: number;
};

export type FocusStatistics = {
  days: 7 | 30;
  today: FocusStatisticSummary;
  period: FocusStatisticSummary;
  daily: FocusDailyStatistic[];
};
