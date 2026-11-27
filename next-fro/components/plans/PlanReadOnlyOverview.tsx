"use client";

import Link from "next/link";
import {
  CalendarDays,
  Check,
  ChevronDown,
  Circle,
  Clock3,
  PencilLine,
  Target,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { getBusinessToday } from "@/lib/plans/business-date";
import { isSettledNumericTask } from "@/lib/tasks/today-presentation";
import { messages } from "@/messages";
import { getPlanProgress } from "@/services/progress.service";
import { getPlanSteps } from "@/services/steps.service";
import { listPlanTasks } from "@/services/tasks.service";
import type { Plan } from "@/types/plan";
import type { PlanProgress } from "@/types/progress";
import type { StepNode } from "@/types/step";
import type { PlanTask } from "@/types/task";

import "@/components/css/PlanPreview.css";

type Props = {
  plan: Plan;
  onManage: () => void;
};

const statusLabels = {
  DRAFT: messages.plans.statusDraft,
  ACTIVE: messages.common.statusActive,
  ENDED: messages.plans.statusEnded,
};

const taskStatusLabels = {
  PENDING: messages.tasks.statusPending,
  IN_PROGRESS: messages.common.statusActive,
  COMPLETED: messages.tasks.statusCompleted,
  OVERDUE: messages.tasks.statusOverdue,
  ENDED: messages.tasks.statusStopped,
};

function collectStepPaths(
  nodes: StepNode[],
  parents: string[] = [],
  paths = new Map<number, string>(),
): Map<number, string> {
  nodes.forEach((node) => {
    const path = [...parents, node.name];
    paths.set(node.id, path.join(" / "));
    collectStepPaths(node.children, path, paths);
  });

  return paths;
}

function countLeaves(nodes: StepNode[]): number {
  return nodes.reduce(
    (total, node) =>
      total + (node.node_type === "LEAF" ? 1 : countLeaves(node.children)),
    0,
  );
}

function collectPathIds(nodes: StepNode[], leafIds: Set<number>): Set<number> {
  const pathIds = new Set<number>();

  function visit(node: StepNode): boolean {
    let childIncludesTarget = false;
    node.children.forEach((child) => {
      if (visit(child)) childIncludesTarget = true;
    });
    const includesTarget = leafIds.has(node.id) || childIncludesTarget;
    if (includesTarget) pathIds.add(node.id);
    return includesTarget;
  }

  nodes.forEach(visit);
  return pathIds;
}

function StepTree({
  nodes,
  todayPathIds,
  progress,
}: {
  nodes: StepNode[];
  todayPathIds: Set<number>;
  progress: PlanProgress | null;
}) {
  const leafProgress = new Map(
    progress?.leaves.map((leaf) => [leaf.step_id, leaf]) ?? [],
  );

  return (
    <ul className="plan-preview-tree">
      {nodes.map((node) => {
        const leaf = leafProgress.get(node.id);
        const row = (
          <div className="plan-preview-tree-row" data-today={todayPathIds.has(node.id)}>
            <span>
              <strong>{node.name}</strong>
              <small>
                {node.node_type === "GROUP"
                  ? messages.steps.group
                  : node.task_type === "NUMERIC"
                    ? messages.tasks.numericType
                    : messages.tasks.booleanType}
              </small>
            </span>
            <span className="plan-preview-tree-meta">
              {todayPathIds.has(node.id) && <em>{messages.plans.previewTodayTag}</em>}
              {leaf?.progress_percent !== null && leaf?.progress_percent !== undefined && (
                <b>{leaf.progress_percent}%</b>
              )}
            </span>
          </div>
        );

        return (
          <li key={node.id}>
            {node.children.length > 0 ? (
              <details open>
                <summary>
                  <ChevronDown size={15} aria-hidden="true" />
                  {row}
                </summary>
                <StepTree
                  nodes={node.children}
                  todayPathIds={todayPathIds}
                  progress={progress}
                />
              </details>
            ) : row}
          </li>
        );
      })}
    </ul>
  );
}

function TaskRow({ task, path }: { task: PlanTask; path: string }) {
  const settled = isSettledNumericTask(task);
  const completed = task.status === "COMPLETED" && !settled;
  const target = task.target_quantity ?? 0;
  const numericProgress = target > 0
    ? Math.min(100, Math.round((task.actual_quantity / target) * 100))
    : 0;

  return (
    <article className="plan-preview-task" data-completed={completed} data-settled={settled}>
      <span className="plan-preview-task-check" aria-hidden="true">
        {completed ? <Check size={16} /> : <Circle size={13} />}
      </span>
      <div className="plan-preview-task-copy">
        <strong>{task.content || task.step_name}</strong>
        <span>{path}</span>
        {task.task_type === "NUMERIC" && (
          <div className="plan-preview-task-progress">
            <span>
              {messages.plans.previewQuantity(task.actual_quantity, target)}
            </span>
            <div aria-hidden="true">
              <i style={{ width: `${numericProgress}%` }} />
            </div>
          </div>
        )}
      </div>
      <span className="plan-preview-task-status" data-status={settled ? "SETTLED" : task.status}>
        {settled ? messages.plans.previewSettled : taskStatusLabels[task.status]}
      </span>
    </article>
  );
}

export function PlanReadOnlyOverview({ plan, onManage }: Props) {
  const [today] = useState(getBusinessToday);
  const [progress, setProgress] = useState<PlanProgress | null>(null);
  const [steps, setSteps] = useState<StepNode[]>([]);
  const [tasks, setTasks] = useState<PlanTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [tasksUnavailable, setTasksUnavailable] = useState(false);
  const [stepsUnavailable, setStepsUnavailable] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function loadPreview() {
      setLoading(true);
      setLoadError(false);
      setTasksUnavailable(false);
      setStepsUnavailable(false);

      const results = await Promise.allSettled([
        getPlanProgress(plan.id),
        getPlanSteps(plan.id),
        listPlanTasks(plan.id),
      ]);

      if (cancelled) return;

      if (results[0].status === "fulfilled") setProgress(results[0].value);
      if (results[1].status === "fulfilled") setSteps(results[1].value);
      if (results[2].status === "fulfilled") setTasks(results[2].value);

      setLoadError(results.some((result) => result.status === "rejected"));
      setStepsUnavailable(results[1].status === "rejected");
      setTasksUnavailable(results[2].status === "rejected");
      setLoading(false);
    }

    void loadPreview();

    return () => {
      cancelled = true;
    };
  }, [plan.id]);

  const stepPaths = useMemo(() => collectStepPaths(steps), [steps]);
  const todayTasks = useMemo(
    () => today === null ? [] : tasks.filter((task) => task.task_date === today),
    [tasks, today],
  );
  const completedToday = todayTasks.filter((task) => task.status === "COMPLETED" && !isSettledNumericTask(task));
  const settledToday = todayTasks.filter(isSettledNumericTask);
  const pendingToday = todayTasks.filter((task) => task.status !== "COMPLETED");

  const nextDate = today === null
    ? null
    : tasks
      .filter((task) => task.task_date > today && task.status !== "COMPLETED")
      .map((task) => task.task_date)
      .sort()[0] ?? null;

  const latestDate = tasks.map((task) => task.task_date).sort().at(-1) ?? null;
  const focusDate = plan.status === "ENDED"
    ? latestDate
    : todayTasks.length > 0
      ? today
      : nextDate;
  const focusTasks = focusDate === null
    ? []
    : tasks.filter((task) => task.task_date === focusDate);
  const focusPending = plan.status === "ACTIVE" && focusDate === today
    ? pendingToday
    : focusTasks.filter((task) => task.status !== "COMPLETED");
  const focusCompleted = plan.status === "ACTIVE" && focusDate === today
    ? completedToday
    : focusTasks.filter((task) => task.status === "COMPLETED" && !isSettledNumericTask(task));
  const focusSettled = plan.status === "ACTIVE" && focusDate === today
    ? settledToday
    : focusTasks.filter(isSettledNumericTask);
  const todayPathIds = collectPathIds(
    steps,
    new Set(todayTasks.map((task) => task.step_id)),
  );
  const progressPercent = progress?.progress_percent;

  return (
    <main className="plan-preview-page">
      <nav className="plan-preview-nav" aria-label={messages.plans.previewNavigation}>
        <Link href="/plans">{messages.plans.backToMyPlans}</Link>
        <button type="button" onClick={onManage}>
          <PencilLine size={15} aria-hidden="true" />
          {messages.plans.managePlan}
        </button>
      </nav>

      <header className="plan-preview-header">
        <div className="plan-preview-heading">
          <div>
            <span className="plan-preview-status" data-status={plan.status}>
              {statusLabels[plan.status]}
            </span>
            <h1>{plan.name}</h1>
            <p>{plan.description || messages.plans.previewNoDescription}</p>
          </div>
          <div className="plan-preview-period">
            <CalendarDays size={18} aria-hidden="true" />
            <span>{messages.plans.previewPeriod}</span>
            <strong>{plan.start_date} ～ {plan.end_date}</strong>
          </div>
        </div>

        <div className="plan-preview-summary">
          <section>
            <Target size={18} aria-hidden="true" />
            <span>{messages.progress.current}</span>
            <strong>{progressPercent === null || progressPercent === undefined ? "—" : `${progressPercent}%`}</strong>
          </section>
          <section>
            <Check size={18} aria-hidden="true" />
            <span>{messages.plans.previewTodayCompleted}</span>
            <strong>{todayTasks.length === 0 ? "—" : `${completedToday.length}/${todayTasks.length}`}</strong>
          </section>
          <section>
            <Clock3 size={18} aria-hidden="true" />
            <span>{messages.plans.previewLearningItems}</span>
            <strong>
              {progress?.leaf_count ?? (stepsUnavailable ? "—" : countLeaves(steps))}
            </strong>
          </section>
        </div>
      </header>

      {loadError && (
        <p role="alert" className="plan-preview-feedback">
          {messages.plans.previewPartialError}
        </p>
      )}

      <div className="plan-preview-grid">
        <section className="plan-preview-tasks" aria-labelledby="plan-preview-task-title">
          <header>
            <div>
              <h2 id="plan-preview-task-title">
                {plan.status === "ENDED"
                  ? messages.plans.previewLastTasks
                  : focusDate === today
                    ? messages.plans.previewTodayTasks
                    : messages.plans.previewNextTasks}
              </h2>
              <p>
                {tasksUnavailable
                  ? messages.plans.previewTasksUnavailableShort
                  : focusDate
                  ? messages.plans.previewTaskDate(focusDate)
                  : messages.plans.previewNoMoreTasks}
              </p>
            </div>
            {focusTasks.length > 0 && <strong>{messages.plans.previewTaskCount(focusTasks.length)}</strong>}
          </header>

          {loading ? (
            <div className="plan-preview-skeleton" aria-label={messages.plans.previewLoading} />
          ) : tasksUnavailable ? (
            <p className="plan-preview-section-error">{messages.plans.previewTasksUnavailable}</p>
          ) : focusTasks.length === 0 ? (
            <div className="plan-preview-empty">
              <Check size={20} aria-hidden="true" />
              <strong>{messages.plans.previewNoTasks}</strong>
              <span>{messages.plans.previewNoMoreTasks}</span>
            </div>
          ) : (
            <div className="plan-preview-task-list">
              {focusPending.map((task) => (
                <TaskRow
                  key={task.id}
                  task={task}
                  path={stepPaths.get(task.step_id) ?? task.step_name}
                />
              ))}

              {focusSettled.length > 0 && (
                <details className="plan-preview-completed" open={focusPending.length === 0}>
                  <summary><ChevronDown size={15} aria-hidden="true" />{messages.plans.previewSettledTasks(focusSettled.length)}</summary>
                  {focusSettled.map((task) => <TaskRow key={task.id} task={task} path={stepPaths.get(task.step_id) ?? task.step_name} />)}
                </details>
              )}

              {focusCompleted.length > 0 && (
                <details className="plan-preview-completed" open={focusPending.length === 0}>
                  <summary>
                    <ChevronDown size={15} aria-hidden="true" />
                    {messages.plans.previewCompletedTasks(focusCompleted.length)}
                  </summary>
                  {focusCompleted.map((task) => (
                    <TaskRow
                      key={task.id}
                      task={task}
                      path={stepPaths.get(task.step_id) ?? task.step_name}
                    />
                  ))}
                </details>
              )}
            </div>
          )}
        </section>

        <section className="plan-preview-steps" aria-labelledby="plan-preview-step-title">
          <header>
            <div>
              <h2 id="plan-preview-step-title">{messages.plans.previewStepTitle}</h2>
              <p>{messages.plans.previewStepDescription}</p>
            </div>
            {!stepsUnavailable && (
              <span>
                {messages.steps.stepCount(
                  progress?.leaf_count ?? countLeaves(steps),
                )}
              </span>
            )}
          </header>

          {loading ? (
            <div className="plan-preview-skeleton" aria-label={messages.plans.previewLoading} />
          ) : stepsUnavailable ? (
            <p className="plan-preview-section-error">{messages.plans.previewStepsUnavailable}</p>
          ) : steps.length === 0 ? (
            <p className="plan-preview-steps-empty">{messages.steps.emptyCurrentPlan}</p>
          ) : (
            <StepTree nodes={steps} todayPathIds={todayPathIds} progress={progress} />
          )}
        </section>
      </div>
    </main>
  );
}
