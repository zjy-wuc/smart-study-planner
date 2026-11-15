
import type { TaskType } from "@/types/task";

export type NodeType = "GROUP" | "LEAF";

export type ScheduleMode =
  | "REPEAT"
  | "DAILY_CUSTOM"
  | "AUTO_DISTRIBUTE"
  | "DAILY_MANUAL";

export type StepNode = {
  id: number;
  plan_id: number;
  parent_id: number | null;
  name: string;
  description: string | null;

  node_type: NodeType;
  task_type: TaskType | null;

  schedule_mode: ScheduleMode | null;
  repeat_content: string | null;
  total_target: number | null;

  sort_order: number;
  created_at: string;
  updated_at: string;

  children: StepNode[];
};
