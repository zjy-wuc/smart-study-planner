"use client";

import { messages } from "@/messages";
import { todayTaskMessages } from "@/messages/zh-CN/tasks";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { useTodayTasks } from "@/hooks/useTodayTasks";
import { TaskActionCard } from "@/components/tasks/TaskActionCard";
import { WorkspaceIcon } from "@/components/ui/WorkspaceIcon";
import { getBusinessToday } from "@/lib/plans/business-date";
import { listPlans } from "@/services/plans.service";
import type { Plan } from "@/types/plan";
import type { DailyTask } from "@/types/task";


export default function TodayTasksPage() {
  const {
    tasks,
    loading,
    error,
    reload,
  } = useTodayTasks();
  const [plans, setPlans] = useState<Plan[]>([]);
  const [checkedIds, setCheckedIds] = useState<Set<number>>(() => new Set());

  useEffect(() => {
    let cancelled = false;
    void listPlans().then((result) => {
      if (!cancelled) setPlans(result);
    }).catch(() => {
      // 任务接口仍提供步骤名，计划名加载失败时可以照常打卡。
    });
    return () => { cancelled = true; };
  }, []);

  const onCheckinStatus = useCallback((id: number, checked: boolean) => {
    setCheckedIds((current) => {
      if (current.has(id) === checked) return current;
      const next = new Set(current);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });
  }, []);

  const pending: DailyTask[] = [];
  const checked: DailyTask[] = [];
  const closed: DailyTask[] = [];
  for (const task of tasks) {
    const rolledOver = task.is_rolled_over || task.has_rollover === 1 || task.rollover_out_quantity > 0;
    if (rolledOver || task.status === "ENDED" || (task.plan_status !== "ACTIVE" && task.status !== "COMPLETED")) {
      closed.push(task);
    } else if (task.status === "COMPLETED" || checkedIds.has(task.id)) {
      checked.push(task);
    } else {
      pending.push(task);
    }
  }
  const groups = [
    { id: "pending", title: todayTaskMessages.todayPendingGroup, items: pending },
    { id: "checked", title: todayTaskMessages.todayCheckedGroup, items: checked },
    { id: "closed", title: todayTaskMessages.todayClosedGroup, items: closed },
  ];

  return (
    <div className="workspace-page today-task-page">
      <div className="workspace-page-heading">
        <div>
          <h1 className="text-2xl font-bold">{messages.navigation.today}</h1>

          <p>
            <time>{getBusinessToday()}</time>
            {!error && (!loading || tasks.length > 0) && <> · {todayTaskMessages.todaySummary(tasks.length, checked.length)}</>}
          </p>
        </div>

        <button
          type="button"
          onClick={reload}
          disabled={loading}
          className="workspace-button workspace-button--secondary"
        >
          <WorkspaceIcon name="refresh" />{messages.tasks.refresh}</button>
      </div>

      {loading && tasks.length === 0 ? (
        <p role="status" className="workspace-loading">{messages.tasks.loadingToday}</p>
      ) : error ? (
        <div role="alert" className="workspace-feedback workspace-feedback--error">
          <p className="text-red-700">{messages.tasks.fetchError(error)}
          </p>

          <button
            type="button"
            onClick={reload}
            className="workspace-text-link"
          >{messages.common.tryAgain}</button>
        </div>
      ) : tasks.length === 0 ? (
        <div className="workspace-empty-state">
          <p>{messages.tasks.emptyToday}</p>

          <Link
            href="/plans"
            className="workspace-text-link"
          >{messages.plans.viewMyPlans}</Link>
        </div>
      ) : (
        <div className="today-task-list" aria-busy={loading}>
          {/* 同一层级保留任务 key，分组变化时保留详情、输入与提交状态。 */}
          {groups.flatMap(({ id, title, items }) => items.length ? [
            <h2 className="today-task-group" key={id}>{title} <span>{items.length}</span></h2>,
            ...items.map((task) => (
              <TaskActionCard
                key={task.id}
                task={task}
                planName={plans.find((plan) => plan.id === task.plan_id)?.name}
                onChanged={reload}
                onCheckinStatus={onCheckinStatus}
              />
            )),
          ] : [])}
        </div>
      )}

      <Link href="/" className="workspace-text-link workspace-back-link">{messages.navigation.backHome}</Link>
    </div>
  );
}
