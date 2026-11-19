"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { messages } from "@/messages";
import type { FocusStatistics } from "@/types/focus";

function formatDuration(seconds: number) {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return hours > 0 ? messages.statistics.focusHoursMinutes(hours, minutes) : messages.statistics.focusMinutes(minutes);
}

function formatDate(date: string) {
  const parts = date.split("-");
  return parts.length === 3 ? `${Number(parts[1])}/${Number(parts[2])}` : date;
}

export function FocusStatisticsPanel({ data, days, onToggle, disabled }: {
  data: FocusStatistics;
  days: 7 | 30;
  onToggle: () => void;
  disabled: boolean;
}) {
  const chartData = data.daily.map((item) => ({ ...item, minutes: Math.round(item.focused_seconds / 60) }));
  return (
    <div className="statistics-focus-panel">
      <section className="statistics-focus-summary" aria-label={messages.statistics.focusOverview}>
        <article><span>{messages.statistics.focusDuration}</span><strong>{formatDuration(data.period.focused_seconds)}</strong></article>
        <article><span>{messages.statistics.focusSessions}</span><strong>{data.period.session_count}<small>{messages.common.timesUnit}</small></strong></article>
        <article><span>{messages.statistics.completedPomodoros}</span><strong>{data.period.completed_pomodoros}<small>{messages.common.plansUnit}</small></strong></article>
      </section>
      <section className="statistics-focus-chart" aria-labelledby="focus-chart-title">
        <div className="statistics-focus-heading"><div><h2 id="focus-chart-title">{messages.statistics.focusTrend}</h2><p>{messages.statistics.focusTrendSubtitle(days)}</p></div><button type="button" onClick={onToggle} disabled={disabled}>{messages.common.recentDays(days)}</button></div>
        <div className="statistics-focus-chart-canvas">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 12, right: 12, bottom: 0, left: 0 }}>
              <CartesianGrid vertical={false} stroke="#e5edf5" strokeDasharray="4 4" />
              <XAxis dataKey="date" tickFormatter={formatDate} tickLine={false} axisLine={false} minTickGap={days === 30 ? 30 : 8} tick={{ fill: "#7b8fa3", fontSize: 11 }} />
              <YAxis allowDecimals={false} width={40} tickLine={false} axisLine={false} tick={{ fill: "#7b8fa3", fontSize: 11 }} />
              <Tooltip labelFormatter={(label) => String(label)} formatter={(value) => [messages.statistics.focusMinutes(Number(value)), messages.statistics.focusDuration]} />
              <Bar dataKey="minutes" fill="#4d82d4" radius={[6, 6, 2, 2]} maxBarSize={38} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>
    </div>
  );
}
