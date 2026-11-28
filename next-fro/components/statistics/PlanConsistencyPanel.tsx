"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowUpRight, Check } from "lucide-react";
import { getCheckinSummary } from "@/services/history.service";
import { buildPlanConsistency } from "@/lib/statistics/plan-consistency";
import { messages } from "@/messages";
import type { CheckinSummary } from "@/types/history";
import type { PlanStatistics } from "@/types/statistics";
import "@/components/css/PlanConsistency.css";

const copy = messages.statistics;

export function PlanConsistencyPanel({ today, overview, overviewError, refreshing, refreshKey, onRefresh }: {
  today: string;
  overview: PlanStatistics | null;
  overviewError: string | null;
  refreshing: boolean;
  refreshKey: number;
  onRefresh: () => void;
}) {
  const [summary, setSummary] = useState<CheckinSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const result = await getCheckinSummary();
        if (!cancelled) setSummary(result);
      } catch (failure) {
        if (!cancelled) setError(failure instanceof Error ? failure.message : copy.fetchFailed);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => { cancelled = true; };
  }, [refreshKey]);

  const plans = useMemo(() => summary ? buildPlanConsistency(summary, today) : [], [summary, today]);

  return (
    <section className="statistics-consistency" aria-labelledby="consistency-title">
      <div className="plan-consistency-heading">
        <div><h2 id="consistency-title">{copy.consistencyTitle}</h2><p>{copy.consistencySubtitle}</p></div>
        <dl className="plan-consistency-summary">
          <div><dt>{copy.activePlansMetric}</dt><dd>{overview?.active_count ?? "—"}<small>{messages.common.plansUnit}</small></dd></div>
          <div><dt>{copy.endedPlansMetric}</dt><dd>{overview?.ended_count ?? "—"}<small>{messages.common.plansUnit}</small></dd></div>
        </dl>
      </div>
      <p className="plan-consistency-rule">{copy.consistencyRule}</p>
      {(error || overviewError) && <p className="plan-consistency-error" role="alert">
        {error ? (summary ? copy.staleError(error) : messages.common.loadError(error)) : copy.staleError(overviewError ?? "")}
        <button type="button" disabled={loading || refreshing} onClick={onRefresh}>{messages.common.retry}</button>
      </p>}
      {loading && <p className="plan-consistency-status" role="status">{summary ? messages.common.refreshing : copy.loadingConsistency}</p>}
      {!summary ? null : plans.length === 0 ? <div className="plan-consistency-empty"><p>{copy.noConsistencyPlans}</p><Link href="/plans/new">{messages.plans.create}</Link></div> : <>
        <div className="plan-consistency-legend"><span><Check size={13} aria-hidden="true" />{copy.checkedIn}</span><span>{copy.consistencyWeek}</span></div>
        <ul className="plan-consistency-list" aria-label={copy.consistencyTitle} tabIndex={0}>
          {plans.map((plan) => <li key={plan.id} className="plan-consistency-row">
            <div className="plan-consistency-name"><Link href={`/plans/${plan.id}`}>{plan.name}<ArrowUpRight size={15} aria-hidden="true" /></Link><span data-checked={plan.checkedToday}>{plan.checkedToday ? copy.consistencyTodayDone : plan.totalDays === 0 ? copy.consistencyNotStarted : copy.consistencyTodayPending}</span></div>
            <dl className="plan-consistency-metrics"><div><dt>{copy.consistencyTotalDays}</dt><dd>{plan.totalDays}<small>{copy.dayUnitSpaced}</small></dd></div><div><dt>{copy.consistencyStreakDays}</dt><dd>{plan.streak}<small>{copy.dayUnitSpaced}</small></dd></div></dl>
            <div className="plan-consistency-week" role="group" aria-label={copy.consistencyWeekLabel(plan.name)}>
              {plan.week.map((day) => {
                const label = copy.consistencyDayLabel(day.date, day.checked ? copy.checkedIn : copy.notCheckedIn);
                return <span className="plan-consistency-day" key={day.date} data-checked={day.checked} data-today={day.date === today} title={label} aria-label={label}>
                  <span className="plan-consistency-dot">{day.checked && <Check size={13} strokeWidth={3} aria-hidden="true" />}</span>
                  <small>{day.date === today ? messages.common.today : `${Number(day.date.slice(5, 7))}/${Number(day.date.slice(8))}`}</small>
                </span>;
              })}
            </div>
          </li>)}
        </ul>
        <p className="plan-consistency-footnote">{copy.consistencyHistoryScope}</p>
      </>}
    </section>
  );
}
