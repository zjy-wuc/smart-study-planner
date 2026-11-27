"use client";

import { messages } from "@/messages";

import {
  useCallback,
  useEffect,
  useState,
} from "react";


import { listTodayTasks } from "@/services/tasks.service";

import type { DailyTask } from "@/types/task";


export function useTodayTasks() {

  const [tasks, setTasks] = useState<DailyTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [revision, setRevision] = useState(0);

  const reload = useCallback(() => {
    setRevision((value) => value + 1);
  }, []);


  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);

      try {
        const result = await listTodayTasks();

        if (!cancelled) {
          setTasks(result);
        }

      } catch (err) {
        if (cancelled) {
          return;
        }

        setTasks([]);

        setError(
          err instanceof Error
            ? err.message
            : messages.tasks.loadTodayFailed,
        );

      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void load();

    return () => {
      cancelled = true;
    };
  }, [revision]);


  return {
    tasks,
    loading,
    error,
    reload,
  };
}
