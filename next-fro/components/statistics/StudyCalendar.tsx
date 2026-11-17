"use client";

import { messages } from "@/messages";

import { CalendarDays, Check, Flame, Sparkles } from "lucide-react";
import type { StatisticsOverview } from "@/types/statistics";
import "@/components/css/StudyCalendar.css";

const WEEKDAYS = [messages.common.weekdayMonday, messages.common.weekdayTuesday, messages.common.weekdayWednesday, messages.common.weekdayThursday, messages.common.weekdayFriday, messages.common.weekdaySaturday, messages.common.weekdaySunday];

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
        <div className="study-calendar-eyebrow"><span><CalendarDays size={16} /></span>{messages.statistics.calendarTitle}</div>
        <h2 id="study-calendar-title">{messages.statistics.calendarMottoFirstLine}<br />{messages.statistics.calendarMottoSecondLine}</h2>
        <p>{messages.statistics.calendarSubtitle}</p>
        <div className="study-calendar-streak">
          <span className="study-calendar-streak-icon"><Flame size={21} /></span>
          <div><span>{messages.statistics.currentStreak}</span><strong>{data.checkins.current_streak_days}<small>{messages.statistics.dayUnitSpaced}</small></strong></div>
        </div>
        <div className="study-calendar-message"><Sparkles size={15} />{todayCount > 0 ? messages.statistics.todayEncouragement : messages.statistics.todayReminder}</div>
      </div>
      <div className="study-calendar-month">
        <div className="study-calendar-month-header">
          <div><h3>{messages.statistics.monthHeading(year, month)}</h3><p>{messages.statistics.calendarProgressMotto}</p></div>
          <span className="study-calendar-today">{messages.statistics.todayDate(month, day)}</span>
        </div>
        <div className="study-calendar-grid" role="group" aria-label={messages.statistics.calendarLabel(year, month)}>
          {WEEKDAYS.map((label) => <span key={label} className="study-calendar-weekday">{label}</span>)}
          {Array.from({ length: offset }, (_, index) => <span key={`blank-${index}`} aria-hidden="true" />)}
          {Array.from({ length: monthDays }, (_, index) => {
            const date = `${year}-${String(month).padStart(2, "0")}-${String(index + 1).padStart(2, "0")}`;
            const count = counts.get(date);
            const future = date > data.as_of_date;
            const unknown = !future && count === undefined;
            const checked = count !== undefined && count > 0;
            const label = messages.statistics.calendarDayLabel(month, index + 1, date === data.as_of_date ? messages.statistics.todaySuffix : "", future ? messages.statistics.futureDate : unknown ? messages.statistics.noData : checked ? messages.statistics.checkins(count) : messages.statistics.notCheckedIn);
            return <div key={date} aria-label={label} title={label} className={`study-calendar-day${checked ? " is-checked" : ""}${date === data.as_of_date ? " is-today" : ""}${future ? " is-future" : ""}${unknown ? " is-unknown" : ""}`}><span>{index + 1}</span>{checked && <Check size={11} strokeWidth={3} aria-hidden="true" />}{unknown && <span className="study-calendar-unknown-mark" aria-hidden="true">—</span>}</div>;
          })}
        </div>
        <div className="study-calendar-legend"><span><i className="study-calendar-legend-check" />{messages.statistics.checkedIn}</span><span><i className="study-calendar-legend-today" />{messages.common.today}</span>{missingPast && <span>{messages.statistics.noDataLegend}</span>}</div>
        {missingPast && <p className="study-calendar-note">{messages.statistics.calendarRange(firstAvailable)}</p>}
      </div>
    </section>
  );
}
