"use client";

import { messages } from "@/messages";

import { useCallback, useEffect, useState } from "react";


import { listPlans } from "@/services/plans.service";
import { listTodayTasks } from "@/services/tasks.service";

import type { Plan } from "@/types/plan";
import type { DailyTask } from "@/types/task";


function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }

  return messages.common.requestFailed;
}


export function useDashboardData() {

  const [plans, setPlans] = useState<Plan[]>([]);
  const [tasks, setTasks] = useState<DailyTask[]>([]);

  const [plansError, setPlansError] = useState<string | null>(null);
  const [tasksError, setTasksError] = useState<string | null>(null);

  const [loading, setLoading] = useState(true);
  const [reloadKey, setReloadKey] = useState(0);

  const reload = useCallback(() => {
    setReloadKey((current) => current + 1);
  }, []);

  useEffect(() => {
    let cancelled = false;


    async function load() {
      setLoading(true);
      setPlansError(null);
      setTasksError(null);

      // 并发请求，但其中一项失败不会导致另一项丢失
      const [plansResult, tasksResult] =
        await Promise.allSettled([
          listPlans(),
          listTodayTasks(),
        ]);

      if (cancelled) {
        return;
      }

      if (plansResult.status === "fulfilled") {
        setPlans(plansResult.value);
      } else {
        setPlans([]);
        setPlansError(getErrorMessage(plansResult.reason));
      }

      if (tasksResult.status === "fulfilled") {
        setTasks(tasksResult.value);
      } else {
        setTasks([]);
        setTasksError(getErrorMessage(tasksResult.reason));
      }

      setLoading(false);
    }

    void load();

    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  return {
    plans,
    tasks,
    plansError,
    tasksError,
    loading,
    reload,
  };
}
