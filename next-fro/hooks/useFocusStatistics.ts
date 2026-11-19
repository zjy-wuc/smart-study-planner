"use client";

import { useCallback, useEffect, useState } from "react";

import { messages } from "@/messages";
import { getFocusStatistics } from "@/services/focus.service";

import type { FocusStatistics } from "@/types/focus";

export function useFocusStatistics(days: 7 | 30, enabled: boolean) {
  const [data, setData] = useState<FocusStatistics | null>(null);
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);

  const refresh = useCallback(() => setRevision((value) => value + 1), []);

  useEffect(() => {
    if (!enabled) return;
    let active = true;
    const timer = window.setTimeout(async () => {
      setLoading(true);
      setError("");
      try {
        const result = await getFocusStatistics(days);
        if (active) setData(result);
      } catch (reason) {
        if (active) setError(reason instanceof Error ? reason.message : messages.common.requestFailed);
      } finally {
        if (active) setLoading(false);
      }
    }, 0);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [days, enabled, revision]);

  return { data, loading, error, refresh };
}
