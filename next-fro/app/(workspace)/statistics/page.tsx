"use client";

import { messages } from "@/messages";

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
            <h1 className="text-2xl font-semibold">{messages.navigation.statistics}</h1>

            <p className="mt-2 text-sm text-slate-600">{messages.statistics.subtitle}</p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={refreshAll}
              disabled={loading || calendar.loading}
              className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 disabled:opacity-50"
            >
              {loading && visibleData ? messages.common.refreshing : messages.common.refreshData}
            </button>
          </div>
        </header>

        {loading && !visibleData && (
          <p role="status" className="py-8 text-slate-600">{messages.statistics.loading}</p>
        )}

        {error && !loading && (
          <div
            role="alert"
            className="space-y-3 rounded-xl border border-red-200 p-5"
          >
            <p className="text-sm text-red-700">
              {visibleData ? messages.statistics.staleError(error) : messages.common.loadError(error)}
            </p>

            <button
              type="button"
              onClick={refreshAll}
              className="rounded-lg border px-3 py-2 text-sm"
            >{messages.common.tryAgain}</button>
          </div>
        )}

        {visibleData && (
          <>
            {calendar.data ? <>
              {calendar.error && <p role="alert">{messages.statistics.calendarStaleError(calendar.error)}</p>}
              <StudyCalendar data={calendar.data} />
            </> : calendar.error ? <p role="alert">{messages.statistics.calendarError(calendar.error)} <button type="button" onClick={calendar.refresh}>{messages.common.retry}</button></p> : <p role="status">{messages.statistics.loadingCalendar}</p>}
            <StatisticsSummary
              checkins={visibleData.checkins}
              plans={visibleData.plans}
            />

            {loading && switching && (
              <p role="status" className="text-sm text-slate-600">{messages.statistics.switchingRange(days, visibleData.trend_days)}</p>
            )}

            <CheckinTrend
              days={visibleData.trend_days}
              dailyTrend={visibleData.daily_trend}
              onToggleDays={() => setDays(visibleData.trend_days === 7 ? 30 : 7)}
              disabled={loading}
            />

            <p className="text-xs text-slate-500">{messages.statistics.asOf(visibleData.as_of_date)}</p>
          </>
        )}
      </div>
    </>
  );
}
