import type { DailyTask, PlanTask } from "@/types/task";

export function isOpenTodayTask(task: DailyTask): boolean {
  return task.plan_status === "ACTIVE" &&
    task.status !== "COMPLETED" && task.status !== "ENDED" &&
    !task.is_rolled_over && !task.has_rollover && task.rollover_out_quantity === 0;
}

export function isSettledNumericTask(task: PlanTask): boolean {
  return task.task_type === "NUMERIC" && task.status === "COMPLETED" &&
    task.actual_quantity < (task.target_quantity ?? 0);
}
