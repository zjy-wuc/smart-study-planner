"use client";

import { CalendarDays, Check, Flame, Sparkles } from "lucide-react";
import type { StatisticsOverview } from "@/types/statistics";
import "@/components/css/StudyCalendar.css";

const WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"];

export function StudyCalendar({ data }: { data: StatisticsOverview }) {
  const [year, month, day] = data.as_of_date.split("-").map(Number);
  const firstDay = new Date(Date.UTC(year, month - 1, 1));
  const offset = (firstDay.getUTCDay() + 6) % 7;
  const monthDays = new Date(Date.UTC(year, month, 0)).getUTCDate();
  const counts = new Map(data.daily_trend.map((item) => [item.date, item.checkin_count]));
  const firstAvailable = data.daily_trend[0]?.date;
  const missingPast = Array.from({ length: day }, (_, index) => `${year}-${String(month).padStart(2, "0")}-${String(index + 1).padStart(2, "0")}`)
    .some((date) => !counts.has(date));
  const todayCount = counts.get(data.as_of_date) ?? 0;

  return (
    <section className="study-calendar" aria-labelledby="study-calendar-title">
      <div className="study-calendar-intro">
        <div className="study-calendar-eyebrow"><span><CalendarDays size={16} /></span> 我的学习日历</div>
        <h2 id="study-calendar-title">把每一天的努力，<br />留在日历里。</h2>
        <p>时间会记住你的每一次坚持。</p>
        <div className="study-calendar-streak">
          <span className="study-calendar-streak-icon"><Flame size={21} /></span>
          <div><span>当前连续打卡</span><strong>{data.checkins.current_streak_days}<small> 天</small></strong></div>
        </div>
        <div className="study-calendar-message"><Sparkles size={15} />{todayCount > 0 ? "今天也在向目标靠近" : "今天也为自己留一点学习时间"}</div>
      </div>
      <div className="study-calendar-month">
        <div className="study-calendar-month-header">
          <div><h3>{year} 年 {month} 月</h3><p>每一次打卡，都是前进的一步</p></div>
          <span className="study-calendar-today">今天 {month}/{day}</span>
        </div>
        <div className="study-calendar-grid" role="group" aria-label={`${year}年${month}月学习日历`}>
          {WEEKDAYS.map((label) => <span key={label} className="study-calendar-weekday">{label}</span>)}
          {Array.from({ length: offset }, (_, index) => <span key={`blank-${index}`} aria-hidden="true" />)}
          {Array.from({ length: monthDays }, (_, index) => {
            const date = `${year}-${String(month).padStart(2, "0")}-${String(index + 1).padStart(2, "0")}`;
            const count = counts.get(date);
            const future = date > data.as_of_date;
            const unknown = !future && count === undefined;
            const checked = count !== undefined && count > 0;
            const label = `${month}月${index + 1}日${date === data.as_of_date ? "，今天" : ""}，${future ? "未来日期" : unknown ? "暂无数据" : checked ? `打卡 ${count} 次` : "未打卡"}`;
            return <div key={date} aria-label={label} title={label} className={`study-calendar-day${checked ? " is-checked" : ""}${date === data.as_of_date ? " is-today" : ""}${future ? " is-future" : ""}${unknown ? " is-unknown" : ""}`}><span>{index + 1}</span>{checked && <Check size={11} strokeWidth={3} aria-hidden="true" />}{unknown && <span className="study-calendar-unknown-mark" aria-hidden="true">—</span>}</div>;
          })}
        </div>
        <div className="study-calendar-legend"><span><i className="study-calendar-legend-check" />已打卡</span><span><i className="study-calendar-legend-today" />今天</span>{missingPast && <span>— 暂无数据</span>}</div>
        {missingPast && <p className="study-calendar-note">日历显示最近 30 天的打卡情况；{firstAvailable ? `${firstAvailable} 之前` : "当前"}暂无日期明细。</p>}
      </div>
    </section>
  );
}
