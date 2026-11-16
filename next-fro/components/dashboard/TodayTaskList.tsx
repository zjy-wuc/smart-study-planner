
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
      <p className="workspace-empty-state">
        今天暂无安排的任务
      </p>
    );
  }

  return (
    <ul className="workspace-task-list">
      {tasks.map((task) => (
        <li
          key={task.id}
          className="workspace-task-item"
          data-status={task.display_status}
        >
          <div>
            <p className="workspace-task-title">
              {task.content || task.step_name}
            </p>

            <p className="workspace-task-meta">
              {task.step_name}
              {" · "}
              {task.task_date}
            </p>

            {task.task_type === "NUMERIC" && (
              <p className="workspace-task-quantity">
                累计完成 {task.actual_quantity}
                {" / "}
                目标 {task.target_quantity ?? 0}
              </p>
            )}

            {task.is_rolled_over && (
              <p className="workspace-rollover-label">
                已发生顺延
              </p>
            )}
          </div>

          <span className="workspace-task-status" data-status={task.display_status}>
            {taskStatusLabels[task.display_status]}
          </span>
        </li>
      ))}
    </ul>
  );
}
