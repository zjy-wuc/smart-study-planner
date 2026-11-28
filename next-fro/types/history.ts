export type HistoryPage<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};

export type CheckinRecord = {
  id: number;
  task_id: number;
  event_type: "BOOLEAN_COMPLETE" | "NUMERIC_PROGRESS";
  recorded_value: number | null;
  recorded_at: string;
  content: string;
  step_id: number;
  task_deleted_at: string | null;
  plan_id: number;
  plan_name: string;
  step_name: string;
};

export type HistoryPlan = { id: number; name: string };
export type HistoryStep = {
  id: number;
  plan_id: number;
  parent_id: number | null;
  name: string;
  deleted_at: string | null;
};
export type CheckinSummary = {
  plans: HistoryPlan[];
  steps: HistoryStep[];
  dates: { plan_id: number; step_id: number; checkin_date: string }[];
};

export type ReviewRecord = {
  id: number;
  note_id: number;
  reviewed_at: string;
  note_title: string;
  plan_id: number | null;
  note_deleted_at: string | null;
};
