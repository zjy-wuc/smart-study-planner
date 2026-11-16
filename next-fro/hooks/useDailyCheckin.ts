"use client";

import { useCallback, useEffect, useState } from "react";
import { getTaskRecords } from "@/services/tasks.service";

function beijingDate(): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit",
  }).format(new Date());
}

export function useDailyCheckin(taskId: number, enabled: boolean) {
  const [state, setState] = useState<"loading" | "available" | "done" | "error">(enabled ? "loading" : "available");
  const [revision, setRevision] = useState(0);
  const markDone = useCallback(() => setState("done"), []);
  const retry = useCallback(() => setRevision((value) => value + 1), []);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    let date = beijingDate();
    async function load() {
      setState("loading");
      try {
        const records = await getTaskRecords(taskId);
        if (!cancelled) {
          setState(records.some((record) => record.event_type === "NUMERIC_PROGRESS" && record.recorded_at.slice(0, 10) === date) ? "done" : "available");
        }
      } catch {
        if (!cancelled) setState("error");
      }
    }
    function checkDate() {
      const current = beijingDate();
      if (current !== date) {
        date = current;
        void load();
      }
    }
    void load();
    const timer = window.setInterval(checkDate, 30000);
    window.addEventListener("focus", checkDate);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
      window.removeEventListener("focus", checkDate);
    };
  }, [taskId, enabled, revision]);

  return { state, markDone, retry };
}
