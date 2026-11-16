
"use client";

import {
  useCallback,
  useEffect,
  useState,
} from "react";

import { getStatisticsOverview } from
  "@/services/statistics.service";

import type {
  StatisticsOverview,
  TrendDays,
} from "@/types/statistics";

export function useStatistics(days: TrendDays) {
  const [data, setData] =
    useState<StatisticsOverview | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] =
    useState<string | null>(null);

  const [refreshKey, setRefreshKey] = useState(0);
//用来缓存函数引用
  const refresh = useCallback(() => {
    setRefreshKey((value) => value + 1);
  }, []);
 // 执行副作用
  useEffect(() => {
    let cancelled = false;
//异步请求竞态（Race Condition）

    async function load() {
      setLoading(true);
      setError(null);
//表示请求开始时进入加载状态，并清除上一次错误
      try {
        const result =
          await getStatisticsOverview(days);

        if (!cancelled) {
          setData(result);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "获取学习统计失败",
          );
        }
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
  }, [days, refreshKey]);
 // 清理副作用
  return {
    data,
    loading,
    error,
    refresh,//最终返回四个属性，然后根据不同状态渲染 UI
  };
}
