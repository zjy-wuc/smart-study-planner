
import type { DailyTask } from "@/types/task";


const taskStatusLabels = {
  PENDING: "待完成",
  IN_PROGRESS: "进行中",
  COMPLETED: "已完成",
  OVERDUE: "已逾期",
  ENDED: "已停止",
};


export function TodayTaskList({
  tasks,
}: {
  tasks: DailyTask[];
}) {
  if (tasks.length === 0) {
    return (
      <p className="py-6 text-sm text-slate-500">
        今天暂无安排的任务
      </p>
    );
  }

  return (
    <ul className="divide-y divide-slate-200">
      {tasks.map((task) => (
        <li
          key={task.id}
          className="flex items-start justify-between gap-4 py-4"
        >
          <div>
            <p className="font-medium">
              {task.content || task.step_name}
            </p>

            <p className="mt-1 text-sm text-slate-500">
              {task.step_name}
              {" · "}
              {task.task_date}
            </p>

            {task.task_type === "NUMERIC" && (
              <p className="mt-1 text-sm text-slate-600">
                累计完成 {task.actual_quantity}
                {" / "}
                目标 {task.target_quantity ?? 0}
              </p>
            )}

            {task.is_rolled_over && (
              <p className="mt-1 text-xs text-blue-700">
                已发生顺延
              </p>
            )}
          </div>

          <span className="shrink-0 text-sm text-slate-600">
            {taskStatusLabels[task.display_status]}
          </span>
        </li>
      ))}
    </ul>
  );
}
