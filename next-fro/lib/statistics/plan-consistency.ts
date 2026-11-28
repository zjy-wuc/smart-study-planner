import type { CheckinSummary } from "@/types/history";

export function shiftDay(day: string, offset: number): string {
  const date = new Date(`${day}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + offset);
  return date.toISOString().slice(0, 10);
}

export function buildPlanConsistency(summary: CheckinSummary, today: string) {
  const datesByPlan = new Map<number, Set<string>>();
  for (const item of summary.dates) {
    if (item.checkin_date > today) continue;
    let dates = datesByPlan.get(item.plan_id);
    if (!dates) {
      dates = new Set();
      datesByPlan.set(item.plan_id, dates);
    }
    dates.add(item.checkin_date);
  }
  const week = Array.from({ length: 7 }, (_, index) => shiftDay(today, index - 6));
  return summary.plans.map((plan) => {
    const dates = datesByPlan.get(plan.id) ?? new Set<string>();
    // 今天尚未打卡时，保留截至昨天的连续记录，直到今天结束。
    let cursor = dates.has(today) ? today : shiftDay(today, -1);
    let streak = 0;
    while (dates.has(cursor)) {
      streak += 1;
      cursor = shiftDay(cursor, -1);
    }
    return {
      ...plan,
      totalDays: dates.size,
      streak,
      checkedToday: dates.has(today),
      week: week.map((date) => ({ date, checked: dates.has(date) })),
    };
  });
}
