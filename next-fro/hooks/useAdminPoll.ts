"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export function useAdminPoll<T>(load: () => Promise<T>, intervalMs: number) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const inFlight = useRef<number | null>(null);
  const live = useRef(false);
  const generation = useRef(0);

  const refresh = useCallback(async () => {
    if (!live.current || inFlight.current === generation.current) return;
    const request = generation.current;
    inFlight.current = request;
    try {
      const result = await load();
      if (live.current && generation.current === request) {
        setData(result);
        setUpdatedAt(new Date());
        setError("");
      }
    } catch (err) {
      if (live.current && generation.current === request)
        setError(err instanceof Error ? err.message : String(err));
    } finally {
      if (inFlight.current === request) inFlight.current = null;
    }
  }, [load]);

  useEffect(() => {
    live.current = true;
    queueMicrotask(() => void refresh());
    const visible = () => {
      if (document.visibilityState === "visible") void refresh();
    };
    document.addEventListener("visibilitychange", visible);
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void refresh();
    }, intervalMs);
    return () => {
      live.current = false;
      generation.current += 1;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", visible);
    };
  }, [refresh, intervalMs]);

  return { data, error, updatedAt, refresh };
}
