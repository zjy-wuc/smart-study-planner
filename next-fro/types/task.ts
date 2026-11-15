
import type { PlanStatus } from "@/types/plan";

export type TaskType = "BOOLEAN" | "NUMERIC";

export type TaskStatus =
  | "PENDING"
  | "IN_PROGRESS"
  | "COMPLETED"
  | "OVERDUE"
  | "ENDED";

export type DailyTask = {
  id: number;
  plan_id: number;
  step_id: number;
  step_name: string;
  task_date: string;
  task_type: TaskType;

  content: string | null;
  target_quantity: number | null;
  actual_quantity: number;
  rollover_out_quantity: number;

  status: TaskStatus;
  display_status: TaskStatus;

  completed_at: string | null;
  created_at: string;
  updated_at: string;

  plan_status: PlanStatus;
  plan_start_date: string;
  plan_end_date: string;

  has_rollover: 0 | 1;
  is_overdue: boolean;
  is_rolled_over: boolean;

  effective_target_quantity: number | null;
  remaining_quantity: number | null;
};


export type NumericProgressUpdate = {
  actual_quantity: number;
};

export type RolloverRequest = {
  target_date: string;
};

export type StudyRecord = {
  id: number;
  task_id: number;
  event_type: "BOOLEAN_COMPLETE" | "NUMERIC_PROGRESS";
  recorded_value: number | null;
  task_date: string;
  recorded_at: string;
};

export type RolloverResult = {
  source_task_id: number;
  target_task_id: number;
  task_type: "BOOLEAN" | "NUMERIC";
  target_date: string;
  rollover_quantity: number | null;
  merged: boolean;
  source_remaining_quantity?: number;
};
