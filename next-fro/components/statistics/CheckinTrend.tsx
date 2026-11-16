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
        <h2 id="checkin-trend-title">每日打卡趋势</h2>
        <p>最近 {days} 天，共 {total} 次</p>
      </div>
      {total === 0 && <p className="statistics-trend-empty">当前时间范围内暂无打卡记录。</p>}
      <div className="statistics-chart" role="img" aria-label={`最近 ${days} 天每日打卡趋势，共 ${total} 次；每日数据可在下方展开查看`}>
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
            <Tooltip labelFormatter={(label) => String(label)} formatter={(value) => [`${value} 次`, "打卡"]} />
            <Area type="monotone" dataKey="checkin_count" stroke="#10a9de" strokeWidth={3} fill="url(#checkin-area-gradient)" dot={days === 7 ? { r: 3, fill: "#10a9de", stroke: "#fff", strokeWidth: 2 } : false} activeDot={{ r: 5, fill: "#10a9de", stroke: "#fff", strokeWidth: 2 }} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <button type="button" className="statistics-range-button" onClick={onToggleDays} disabled={disabled} aria-label={`当前最近 ${days} 天，点击切换到最近 ${days === 7 ? 30 : 7} 天`}>
        最近 {days} 天 <span aria-hidden="true">⌄</span>
      </button>
      <details className="statistics-trend-details">
        <summary>查看每日详细数据</summary>
        <div className="statistics-trend-table-wrap">
          <table><thead><tr><th>日期</th><th>打卡次数</th></tr></thead>
            <tbody>{dailyTrend.map((item) => <tr key={item.date}><td>{item.date}</td><td>{item.checkin_count}</td></tr>)}</tbody>
          </table>
        </div>
      </details>
    </section>
  );
}
