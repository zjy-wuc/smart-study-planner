
import type { TaskType } from "@/types/task";

import type { ScheduleEntryInput } from "@/types/schedule";

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

export type StepRule = {
  task_type: TaskType;
  schedule_mode: ScheduleMode;
  repeat_content?: string | null;
  total_target?: number | null;
};

export type StepCreate = {
  name: string;
  description?: string | null;
  node_type: NodeType;
  parent_id?: number | null;
  rule?: StepRule | null;
  children?: StepCreate[];
};

export type StepUpdate = {
  name?: string;
  description?: string | null;
};

export type ActiveStepNode = {
  name: string;
  description?: string | null;
  node_type: NodeType;
  rule?: StepRule | null;
  entries?: ScheduleEntryInput[];
  children?: ActiveStepNode[];
};

/**
 * ACTIVE 计划新增节点时提交的请求体
 */
export type ActiveStepTreeCreate = {
  parent_id?: number | null;
  node: ActiveStepNode;
};

/**
 * ACTIVE 计划新增节点成功后的响应数据
 */
export type ActiveStepCreateResult = {
  created_step_ids: number[];
  generated_task_count: number;
  tree: StepNode[];
};
