
"use client";

import {
  useCallback,
  useEffect,
  useState,
} from "react";

import { useRouter } from "next/navigation";

import { ApiError } from "@/lib/api/client";
import { listTodayTasks } from "@/services/tasks.service";

import type { DailyTask } from "@/types/task";


export function useTodayTasks() {
  const router = useRouter();

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

        if (
          err instanceof ApiError &&
          err.status === 401
        ) {
          router.replace("/login");
          return;
        }

        setError(
          err instanceof Error
            ? err.message
            : "今日任务加载失败",
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
  }, [router, revision]);


  return {
    tasks,
    loading,
    error,
    reload,
  };
}
