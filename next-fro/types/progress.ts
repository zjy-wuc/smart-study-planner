
import type { PlanStatus } from "@/types/plan";
import type { TaskType } from "@/types/task";

export type ProgressReason =
  | "PLAN_NOT_ACTIVE"
  | "NO_VALID_TASKS"
  | "ZERO_TARGET"
  | "DATA_ANOMALY"
  | "NO_COMPUTABLE_LEAF";

export type ProgressLeaf = {
  step_id: number;
  name: string;
  task_type: TaskType;

  progress_percent: number | null;
  reason: ProgressReason | null;

  valid_task_count: number;
  completed_task_count: number | null;

  target_total: number | null;
  actual_total: number | null;
};

export type DataAnomaly = {
  step_id: number;
  task_id: number;
  detail: string;
};

export type PlanProgress = {
  plan_id: number;
  plan_status: PlanStatus;

  progress_percent: number | null;
  reason: ProgressReason | null;

  leaf_count: number;
  computable_leaf_count: number;

  leaves: ProgressLeaf[];
  data_anomalies: DataAnomaly[];
};
