"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError } from "@/lib/api/client";
import { messages } from "@/messages";

// 仅用于知识模块：每次加载失效后丢弃结果，避免筛选或路由切换时旧响应覆盖新状态。
export function useKnowledgeQuery<T>(load: () => Promise<T>) {
  const router = useRouter();
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const refresh = useCallback(() => setRevision((value) => value + 1), []);
  useEffect(() => {
    let cancelled = false;
    async function fetchData() {
      setLoading(true);
      setError("");
      try {
        const result = await load();
        if (!cancelled) setData(result);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 401) router.replace("/login");
        setError(err instanceof Error ? err.message : messages.knowledge.failed);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void fetchData();
    return () => { cancelled = true; };
  }, [load, revision, router]);
  return { data, loading, error, refresh };
}

export function useKnowledgeAction() {
  const router = useRouter();
  const lock = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  async function run(action: () => Promise<void>, success: string) {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
      setNotice(success);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) router.replace("/login");
      setError(err instanceof Error ? err.message : messages.knowledge.failed);
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  return { busy, error, notice, run };
}
