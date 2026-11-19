"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { messages } from "@/messages";
import {
  cancelFocus,
  finishFocus,
  getFocusHistory,
  getFocusStatistics,
  pauseFocus,
  resumeFocus,
  startFocus,
  syncFocus,
} from "@/services/focus.service";

import type { FocusHistory, FocusSession, FocusStart, FocusStatistics } from "@/types/focus";

function parseBeijingDate(value: string | null): number | null {
  if (!value) return null;
  const normalized = /(?:Z|[+-]\d{2}:?\d{2})$/.test(value)
    ? value
    : `${value.replace(" ", "T")}+08:00`;
  const timestamp = Date.parse(normalized);
  return Number.isNaN(timestamp) ? null : timestamp;
}

export function getLiveFocusedSeconds(session: FocusSession | null, now: number) {
  if (!session) return 0;
  if (session.status !== "RUNNING") return session.focused_seconds;
  const runningStartedAt = parseBeijingDate(session.running_started_at);
  if (runningStartedAt === null) return session.focused_seconds;
  return session.focused_seconds + Math.max(0, Math.floor((now - runningStartedAt) / 1000));
}

export function useFocusSession() {
  const [session, setSession] = useState<FocusSession | null>(null);
  const [completed, setCompleted] = useState<FocusSession | null>(null);
  const [history, setHistory] = useState<FocusHistory | null>(null);
  const [statistics, setStatistics] = useState<FocusStatistics | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const mounted = useRef(true);
  const settlementRequested = useRef<number | null>(null);

  const refreshSupportingData = useCallback(async () => {
    const [nextHistory, nextStatistics] = await Promise.all([
      getFocusHistory(),
      getFocusStatistics(7),
    ]);
    if (!mounted.current) return;
    setHistory(nextHistory);
    setStatistics(nextStatistics);
  }, []);

  const synchronize = useCallback(async () => {
    try {
      const result = await syncFocus();
      if (!mounted.current) return;
      setError("");
      setSession(result.current);
      if (result.auto_completed) setCompleted(result.auto_completed);
      await refreshSupportingData();
    } catch (reason) {
      if (mounted.current) {
        setError(reason instanceof Error ? reason.message : messages.focus.syncFailed);
      }
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, [refreshSupportingData]);

  useEffect(() => {
    mounted.current = true;
    const timer = window.setTimeout(() => void synchronize(), 0);
    return () => {
      window.clearTimeout(timer);
      mounted.current = false;
    };
  }, [synchronize]);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    function syncWhenVisible() {
      if (document.visibilityState === "visible") void synchronize();
    }
    document.addEventListener("visibilitychange", syncWhenVisible);
    window.addEventListener("focus", syncWhenVisible);
    return () => {
      document.removeEventListener("visibilitychange", syncWhenVisible);
      window.removeEventListener("focus", syncWhenVisible);
    };
  }, [synchronize]);

  const run = useCallback(async (action: () => Promise<FocusSession>, conclude = false) => {
    if (working) return;
    setWorking(true);
    setError("");
    try {
      const result = await action();
      if (!mounted.current) return;
      if (conclude || result.status === "COMPLETED" || result.status === "CANCELLED") {
        setSession(null);
        if (result.status === "COMPLETED") setCompleted(result);
      } else {
        setSession(result);
      }
      await refreshSupportingData();
    } catch (reason) {
      if (mounted.current) setError(reason instanceof Error ? reason.message : messages.common.operationFailedRetry);
    } finally {
      if (mounted.current) setWorking(false);
    }
  }, [refreshSupportingData, working]);

  const begin = useCallback(async (data: FocusStart) => {
    await run(() => startFocus(data));
  }, [run]);

  const focusedSeconds = getLiveFocusedSeconds(session, now);
  const displaySeconds = useMemo(() => {
    if (!session) return 0;
    if (session.session_type === "STOPWATCH") return Math.min(focusedSeconds, 86_400);
    return Math.max(0, (session.planned_seconds ?? 0) - focusedSeconds);
  }, [focusedSeconds, session]);

  const progress = useMemo(() => {
    if (!session) return 0;
    if (session.session_type === "STOPWATCH") return Math.min(focusedSeconds / 86_400, 1);
    return Math.min(focusedSeconds / Math.max(session.planned_seconds ?? 1, 1), 1);
  }, [focusedSeconds, session]);

  useEffect(() => {
    if (!session || session.status !== "RUNNING") {
      settlementRequested.current = null;
      return;
    }
    const limit = session.session_type === "POMODORO"
      ? session.planned_seconds
      : 86_400;
    if (limit === null || focusedSeconds < limit || settlementRequested.current === session.id) return;
    settlementRequested.current = session.id;
    void synchronize();
  }, [focusedSeconds, session, synchronize]);

  return {
    session,
    completed,
    history,
    statistics,
    loading,
    working,
    error,
    focusedSeconds,
    displaySeconds,
    progress,
    begin,
    pause: () => session && run(() => pauseFocus(session.id)),
    resume: () => session && run(() => resumeFocus(session.id)),
    finish: () => session && run(() => finishFocus(session.id), true),
    cancel: () => session && run(() => cancelFocus(session.id), true),
    dismissCompleted: () => setCompleted(null),
    synchronize,
  };
}
