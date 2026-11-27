"use client";

import { messages } from "@/messages";
import { historyRangeSummary } from "@/messages/zh-CN/history";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Check, ChevronDown } from "lucide-react";
import { listPlans } from "@/services/plans.service";
import { getPlanSteps } from "@/services/steps.service";
import { getTaskRecords, listPlanTasks } from "@/services/tasks.service";
import type { Plan } from "@/types/plan";
import type { StepNode } from "@/types/step";
import type { PlanTask, StudyRecord } from "@/types/task";
import "@/components/css/History.css";

type Range = 7 | 30 | "all";
type HistoryEntry = { plan: Plan; task: PlanTask; record: StudyRecord; path: string[] };
type PlanHistory = { plan: Plan; steps: StepNode[]; entries: HistoryEntry[]; incomplete: boolean };

function todayInBeijing() {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
}

function previousDay(day: string, days = 1) {
  const date = new Date(`${day}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() - days);
  return date.toISOString().slice(0, 10);
}

function formatHistoryDate(date: string, today: string) {
  const [year, month, day] = date.split("-").map(Number);
  const weekday = [messages.common.weekdaySunday, messages.common.weekdayMonday, messages.common.weekdayTuesday, messages.common.weekdayWednesday, messages.common.weekdayThursday, messages.common.weekdayFriday, messages.common.weekdaySaturday][new Date(Date.UTC(year, month - 1, day)).getUTCDay()];
  return messages.history.dateHeading(month, day, weekday, date === today ? messages.history.todaySuffix : "");
}

function countDays(entries: HistoryEntry[], today: string) {
  const dates = new Set(entries.map((entry) => entry.record.recorded_at.slice(0, 10)).filter((date) => date <= today));
  let cursor = dates.has(today) ? today : previousDay(today);
  let streak = 0;
  while (dates.has(cursor)) {
    streak += 1;
    cursor = previousDay(cursor);
  }
  return { total: dates.size, streak };
}

function nodePaths(nodes: StepNode[], parents: string[] = [], paths = new Map<number, string[]>()) {
  for (const node of nodes) {
    const path = [...parents, node.name];
    paths.set(node.id, path);
    nodePaths(node.children, path, paths);
  }
  return paths;
}

function descendants(node: StepNode): number[] {
  return [node.id, ...node.children.flatMap(descendants)];
}

async function mapLimited<T, R>(items: T[], concurrency: number, fn: (item: T) => Promise<R>, cancelled: () => boolean, onSettled?: () => void): Promise<PromiseSettledResult<R>[]> {
  const results: PromiseSettledResult<R>[] = new Array(items.length);
  let next = 0;
  await Promise.all(Array.from({ length: Math.min(items.length, concurrency) }, async () => {
    while (!cancelled() && next < items.length) {
      const index = next++;
      try { results[index] = { status: "fulfilled", value: await fn(items[index]) }; }
      catch (reason) { results[index] = { status: "rejected", reason }; }
      if (!cancelled()) onSettled?.();
    }
  }));
  return results;
}

function StepItem({ node, entries, today, incomplete }: { node: StepNode; entries: HistoryEntry[]; today: string; incomplete: boolean }) {
  const ids = new Set(descendants(node));
  const counts = countDays(entries.filter((entry) => ids.has(entry.task.step_id)), today);
  return <li className="history-step"><div className="history-step-row"><span>{node.name}</span><span className="history-step-count">{incomplete ? messages.history.incompleteData : messages.history.dayCounts(counts.total, counts.streak)}</span></div>
    {node.children.length > 0 && <ul className="history-step-children">{node.children.map((child) => <StepItem key={child.id} node={child} entries={entries} today={today} incomplete={incomplete} />)}</ul>}
  </li>;
}

export default function HistoryPage() {
  const [plans, setPlans] = useState<PlanHistory[]>([]);
  const [range, setRange] = useState<Range>(7);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const [asOf, setAsOf] = useState("");
  const [planErrors, setPlanErrors] = useState(0);
  const [loadProgress, setLoadProgress] = useState<{ done: number; total: number } | null>(null);

  const reload = useCallback(() => setRevision((value) => value + 1), []);
  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError("");
      setLoadProgress(null);
      try {
        const allPlans = await listPlans();
        let completedPlans = 0;
        setLoadProgress({ done: 0, total: allPlans.length });
        const planResults = await mapLimited(allPlans, 4, async (plan) => {
          const [steps, tasks] = await Promise.all([getPlanSteps(plan.id), listPlanTasks(plan.id)]);
          return { plan, steps, tasks };
        }, () => cancelled, () => setLoadProgress({ done: ++completedPlans, total: allPlans.length }));
        if (cancelled) return;
        const failedPlans = planResults.filter((item) => item.status === "rejected");
        const loaded = planResults.flatMap((item) => item.status === "fulfilled" ? [item.value] : []);
        const work = loaded.flatMap(({ plan, tasks }) => tasks.map((task) => ({ plan, task })));
        let completedTasks = 0;
        setLoadProgress({ done: 0, total: work.length });
        const records = await mapLimited(work, 6, async ({ plan, task }) => ({ plan, task, records: await getTaskRecords(task.id) }), () => cancelled, () => {
          completedTasks += 1;
          if (completedTasks % 5 === 0 || completedTasks === work.length) setLoadProgress({ done: completedTasks, total: work.length });
        });
        if (cancelled) return;
        const result = loaded.map(({ plan, steps }) => ({ plan, steps, entries: [] as HistoryEntry[], incomplete: false }));
        const byId = new Map(result.map((item) => [item.plan.id, item]));
        const paths = new Map(result.map((item) => [item.plan.id, nodePaths(item.steps)]));
        records.forEach((item, index) => {
          const bucket = byId.get(work[index].plan.id)!;
          if (item.status === "rejected") { bucket.incomplete = true; return; }
          for (const record of item.value.records) bucket.entries.push({ plan: item.value.plan, task: item.value.task, record, path: paths.get(bucket.plan.id)?.get(item.value.task.step_id) ?? [item.value.task.step_name] });
        });
        setPlans(result);
        setPlanErrors(failedPlans.length);
        setAsOf(todayInBeijing());
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : messages.common.loadFailedRetry);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => { cancelled = true; };
  }, [revision]);

  const entries = useMemo(() => plans.flatMap((plan) => plan.entries).sort((a, b) => b.record.recorded_at.localeCompare(a.record.recorded_at) || b.record.id - a.record.id), [plans]);
  const grouped = useMemo(() => {
    if (!asOf) return [];
    const start = range === "all" ? null : previousDay(asOf, range - 1);
    const groups = new Map<string, HistoryEntry[]>();
    for (const entry of entries) {
      const day = entry.record.recorded_at.slice(0, 10);
      if (day > asOf || (start && day < start)) continue;
      const list = groups.get(day) ?? [];
      list.push(entry);
      groups.set(day, list);
    }
    return [...groups.entries()];
  }, [entries, range, asOf]);
  const incomplete = planErrors > 0 || plans.some((plan) => plan.incomplete);

  const recordCount = grouped.reduce((total, [, records]) => total + records.length, 0);

  return <div className="workspace-page history-page">
    <header className="history-page-header">
      <div>
        <h1>{messages.navigation.history}</h1>
        <p aria-live="polite">
          {loading || error || incomplete ? messages.history.subtitle : historyRangeSummary(grouped.length, recordCount)}
        </p>
      </div>
      <button className="history-refresh" type="button" onClick={reload} disabled={loading}>{messages.history.refresh}</button>
    </header>
    {loading ? <p role="status" className="workspace-loading">{messages.history.loading}{loadProgress && loadProgress.total > 0 && <> {messages.history.loadProgress(loadProgress.done, loadProgress.total)}</>}</p> : error ? <div role="alert" className="workspace-feedback workspace-feedback--error">{error} <button type="button" onClick={reload}>{messages.common.retry}</button></div> : <>
      {incomplete && <div role="alert" className="history-warning">{messages.history.partialFailure}<button type="button" onClick={reload}>{messages.common.reload}</button></div>}
      <div className="history-layout">
        <section className="history-panel" aria-labelledby="history-timeline-title">
          <div className="history-panel-title"><div><h2 id="history-timeline-title">{messages.history.recordsTitle}</h2><p>{messages.history.recordsSubtitle}</p></div></div>
          <div className="history-filters" data-range={range} role="group" aria-label={messages.history.rangeLabel}>
            {([7, 30, "all"] as const).map((value) => (
              <button key={value} type="button" aria-pressed={range === value} onClick={() => setRange(value)}>
                {value === "all" ? messages.common.all : messages.common.recentDays(value)}
              </button>
            ))}
          </div>
          {grouped.length === 0 ? (
            <p className="history-empty">{incomplete ? messages.history.partialRetry : messages.history.emptyRange}</p>
          ) : (
            <div className="history-timeline" key={range}>
              {grouped.map(([day, dayEntries]) => (
                <section className="history-day" key={day}>
                  <div className="history-day-heading">
                    <h3><time dateTime={day}>{formatHistoryDate(day, asOf)}</time></h3>
                    <span>{messages.history.checkinCount(dayEntries.length)}</span>
                  </div>
                  <ul>
                    {dayEntries.map(({ plan, task, record, path }) => (
                      <li className="history-entry" key={record.id}>
                        <span className="history-entry-icon" aria-hidden="true"><Check size={16} strokeWidth={2.4} /></span>
                        <div>
                          <strong>{task.content || task.step_name}</strong>
                          <p>{plan.name} / {path.join(" / ")}</p>
                          <small>{record.event_type === "BOOLEAN_COMPLETE" ? messages.tasks.booleanCheckin : messages.tasks.recordedTotal(record.recorded_value ?? 0)}</small>
                        </div>
                        <time>{record.recorded_at.slice(11, 16)}</time>
                      </li>
                    ))}
                  </ul>
                </section>
              ))}
            </div>
          )}
        </section>
        <section className="history-panel" aria-labelledby="history-plans-title"><div className="history-panel-title"><div><h2 id="history-plans-title">{messages.history.plansTitle}</h2><p>{messages.history.plansSubtitle}</p></div></div>
          <p className="history-explanation">{messages.history.streakExplanation}</p>
          {plans.length === 0 ? <p className="history-empty">{messages.plans.empty}</p> : (
            <div className="history-plans">
              {plans.map((item) => {
                const counts = countDays(item.entries, asOf);
                return (
                  <details className="history-plan" key={item.plan.id}>
                    <summary>
                      <span className="history-plan-name">{item.plan.name}</span>
                      <span className="history-plan-metrics">
                        {item.incomplete ? <small>{messages.history.incompleteData}</small> : <>
                          <span><strong>{counts.total}</strong><small>{messages.history.totalDays}</small></span>
                          <span><strong>{counts.streak}</strong><small>{messages.history.streakDays}</small></span>
                        </>}
                      </span>
                      <ChevronDown className="history-plan-chevron" size={16} aria-hidden="true" />
                    </summary>
                    <div className="history-plan-body">
                      {item.steps.length ? (
                        <ul>{item.steps.map((node) => <StepItem key={node.id} node={node} entries={item.entries} today={asOf} incomplete={item.incomplete} />)}</ul>
                      ) : <p>{messages.history.emptyPlanSteps}</p>}
                    </div>
                  </details>
                );
              })}
            </div>
          )}
        </section>
      </div>
      <p className="history-footnote">{messages.history.dataScope}</p>
    </>}
  </div>;
}
