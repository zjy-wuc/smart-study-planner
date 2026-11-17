import { messages } from "@/messages";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { DailyCheckinTrend, TrendDays } from "@/types/statistics";
import "@/components/css/Statistics.css";

type Props = {
  days: TrendDays;
  dailyTrend: DailyCheckinTrend[];
  onToggleDays: () => void;
  disabled?: boolean;
};

function formatDate(date: string): string {
  const parts = date.split("-");
  return parts.length === 3 ? `${Number(parts[1])}/${Number(parts[2])}` : date;
}

export function CheckinTrend({ days, dailyTrend, onToggleDays, disabled = false }: Props) {
  const total = dailyTrend.reduce((sum, item) => sum + item.checkin_count, 0);

  return (
    <section aria-labelledby="checkin-trend-title" className="statistics-trend">
      <div className="statistics-trend-header">
        <h2 id="checkin-trend-title">{messages.statistics.trendTitle}</h2>
        <p>{messages.statistics.trendSummary(days, total)}</p>
      </div>
      {total === 0 && <p className="statistics-trend-empty">{messages.statistics.emptyTrend}</p>}
      <div className="statistics-chart" role="img" aria-label={messages.statistics.trendAccessible(days, total)}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={dailyTrend} margin={{ top: 15, right: 12, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="checkin-area-gradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#2ab4e3" stopOpacity={0.28} />
                <stop offset="100%" stopColor="#2ab4e3" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid vertical={false} stroke="#e7f0f6" strokeDasharray="4 4" />
            <XAxis dataKey="date" tickFormatter={formatDate} tickLine={false} axisLine={false} minTickGap={days === 30 ? 35 : 12} tick={{ fill: "#819aad", fontSize: 12 }} />
            <YAxis allowDecimals={false} domain={[0, "auto"]} width={32} tickLine={false} axisLine={false} tick={{ fill: "#819aad", fontSize: 12 }} />
            <Tooltip labelFormatter={(label) => String(label)} formatter={(value) => [messages.statistics.times(String(value)), messages.tasks.checkin]} />
            <Area type="monotone" dataKey="checkin_count" stroke="#10a9de" strokeWidth={3} fill="url(#checkin-area-gradient)" dot={days === 7 ? { r: 3, fill: "#10a9de", stroke: "#fff", strokeWidth: 2 } : false} activeDot={{ r: 5, fill: "#10a9de", stroke: "#fff", strokeWidth: 2 }} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <button type="button" className="statistics-range-button" onClick={onToggleDays} disabled={disabled} aria-label={messages.statistics.toggleRangeLabel(days, days === 7 ? 30 : 7)}>{messages.common.recentDays(days)}{" "}<span aria-hidden="true">⌄</span>
      </button>
      <details className="statistics-trend-details">
        <summary>{messages.statistics.dailyDetails}</summary>
        <div className="statistics-trend-table-wrap">
          <table><thead><tr><th>{messages.common.date}</th><th>{messages.statistics.checkinCount}</th></tr></thead>
            <tbody>{dailyTrend.map((item) => <tr key={item.date}><td>{item.date}</td><td>{item.checkin_count}</td></tr>)}</tbody>
          </table>
        </div>
      </details>
    </section>
  );
}
