
"use client";

import { useState } from "react";

import { useStatistics } from "@/hooks/useStatistics";

import { StatisticsSummary } from
  "@/components/statistics/StatisticsSummary";

import { StudyCalendar } from "@/components/statistics/StudyCalendar";
import { StatisticsSky } from "@/components/statistics/StatisticsSky";

import { CheckinTrend } from
  "@/components/statistics/CheckinTrend";

import type { TrendDays } from "@/types/statistics";

import "@/components/css/StatisticsScene.css";

export default function StatisticsPage() {
  const [days, setDays] = useState<TrendDays>(7);

  const {
    data,
    loading,
    error,
    refresh,
  } = useStatistics(days);
  const calendar = useStatistics(30);

  // 保留上次成功的数据，加载或失败时不让页面高度突然缩短。
  const visibleData = data;
  const switching = !!data && data.trend_days !== days;

  function refreshAll() {
    refresh();
    calendar.refresh();
  }

  return (
    <>
      <StatisticsSky />
      <div className="statistics-page mx-auto w-full max-w-6xl space-y-6 p-4 sm:p-6">
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold">
              学习统计
            </h1>

            <p className="mt-2 text-sm text-slate-600">
              查看打卡记录、学习连续性和计划执行情况。
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={refreshAll}
              disabled={loading || calendar.loading}
              className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 disabled:opacity-50"
            >
              {loading && visibleData ? "刷新中..." : "刷新数据"}
            </button>
          </div>
        </header>

        {loading && !visibleData && (
          <p role="status" className="py-8 text-slate-600">
            正在加载学习统计...
          </p>
        )}

        {error && !loading && (
          <div
            role="alert"
            className="space-y-3 rounded-xl border border-red-200 p-5"
          >
            <p className="text-sm text-red-700">
              {visibleData ? "更新失败，当前显示上次的数据：" : "加载失败："}{error}
            </p>

            <button
              type="button"
              onClick={refreshAll}
              className="rounded-lg border px-3 py-2 text-sm"
            >
              重新尝试
            </button>
          </div>
        )}

        {visibleData && (
          <>
            {calendar.data ? <>
              {calendar.error && <p role="alert">日历更新失败，当前显示上次的数据：{calendar.error}</p>}
              <StudyCalendar data={calendar.data} />
            </> : calendar.error ? <p role="alert">日历加载失败：{calendar.error} <button type="button" onClick={calendar.refresh}>重试</button></p> : <p role="status">正在加载学习日历...</p>}
            <StatisticsSummary
              checkins={visibleData.checkins}
              plans={visibleData.plans}
            />

            {loading && switching && (
              <p role="status" className="text-sm text-slate-600">
                正在切换到最近 {days} 天，暂时显示最近 {visibleData.trend_days} 天的数据。
              </p>
            )}

            <CheckinTrend
              days={visibleData.trend_days}
              dailyTrend={visibleData.daily_trend}
              onToggleDays={() => setDays(visibleData.trend_days === 7 ? 30 : 7)}
              disabled={loading}
            />

            <p className="text-xs text-slate-500">
              统计截至北京时间 {visibleData.as_of_date}。
              打卡数据以成功保存的学习记录为准。
            </p>
          </>
        )}
      </div>
    </>
  );
}
