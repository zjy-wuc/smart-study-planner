"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Check, CalendarDays } from "lucide-react";
import { ApiError } from "@/lib/api/client";
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
  const weekday = ["日", "一", "二", "三", "四", "五", "六"][new Date(Date.UTC(year, month - 1, day)).getUTCDay()];
  return `${month}月${day}日 · 周${weekday}${date === today ? " · 今天" : ""}`;
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

async function mapLimited<T, R>(items: T[], concurrency: number, fn: (item: T) => Promise<R>, cancelled: () => boolean): Promise<PromiseSettledResult<R>[]> {
  const results: PromiseSettledResult<R>[] = new Array(items.length);
  let next = 0;
  await Promise.all(Array.from({ length: Math.min(items.length, concurrency) }, async () => {
    while (!cancelled() && next < items.length) {
      const index = next++;
      try { results[index] = { status: "fulfilled", value: await fn(items[index]) }; }
      catch (reason) { results[index] = { status: "rejected", reason }; }
    }
  }));
  return results;
}

function StepItem({ node, entries, today, incomplete }: { node: StepNode; entries: HistoryEntry[]; today: string; incomplete: boolean }) {
  const ids = new Set(descendants(node));
  const counts = countDays(entries.filter((entry) => ids.has(entry.task.step_id)), today);
  return <li className="history-step"><div className="history-step-row"><span>{node.name}</span><span className="history-step-count">{incomplete ? "数据未完整加载" : `累计 ${counts.total} 天 · 连续 ${counts.streak} 天`}</span></div>
    {node.children.length > 0 && <ul className="history-step-children">{node.children.map((child) => <StepItem key={child.id} node={child} entries={entries} today={today} incomplete={incomplete} />)}</ul>}
  </li>;
}

export default function HistoryPage() {
  const router = useRouter();
  const [plans, setPlans] = useState<PlanHistory[]>([]);
  const [range, setRange] = useState<Range>(7);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const [asOf, setAsOf] = useState("");
  const [planErrors, setPlanErrors] = useState(0);

  const reload = useCallback(() => setRevision((value) => value + 1), []);
  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError("");
      try {
        const allPlans = await listPlans();
        const planResults = await mapLimited(allPlans, 4, async (plan) => {
          const [steps, tasks] = await Promise.all([getPlanSteps(plan.id), listPlanTasks(plan.id)]);
          return { plan, steps, tasks };
        }, () => cancelled);
        if (cancelled) return;
        const failedPlans = planResults.filter((item) => item.status === "rejected");
        const planAuthFailure = failedPlans.some((item) => item.status === "rejected" && item.reason instanceof ApiError && item.reason.status === 401);
        if (planAuthFailure) throw new ApiError("登录已过期", 401);
        const loaded = planResults.flatMap((item) => item.status === "fulfilled" ? [item.value] : []);
        const work = loaded.flatMap(({ plan, tasks }) => tasks.map((task) => ({ plan, task })));
        const records = await mapLimited(work, 6, async ({ plan, task }) => ({ plan, task, records: await getTaskRecords(task.id) }), () => cancelled);
        if (cancelled) return;
        if (records.some((item) => item.status === "rejected" && item.reason instanceof ApiError && item.reason.status === 401)) throw new ApiError("登录已过期", 401);
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
        if (err instanceof ApiError && err.status === 401) router.replace("/login");
        else setError(err instanceof Error ? err.message : "加载失败，请重试");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => { cancelled = true; };
  }, [router, revision]);

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

  return <div className="workspace-page history-page">
    <header className="history-page-header"><div><h1>打卡历史</h1><p>记录每一次认真学习的日子</p></div><button className="history-refresh" type="button" onClick={reload} disabled={loading}>刷新记录</button></header>
    {loading ? <p role="status" className="workspace-loading">正在整理打卡记录，任务较多时需要一些时间…</p> : error ? <div role="alert" className="workspace-feedback workspace-feedback--error">{error} <button type="button" onClick={reload}>重试</button></div> : <>
      {incomplete && <div role="alert" className="history-warning">部分数据加载失败，记录可能不完整，受影响的计划不显示统计。<button type="button" onClick={reload}>重新加载</button></div>}
      <div className="history-layout">
        <section className="history-panel" aria-labelledby="history-timeline-title">
          <div className="history-panel-title"><div><h2 id="history-timeline-title">打卡记录</h2><p>每一次努力，都值得被记录</p></div></div>
          <div className="history-filters" role="group" aria-label="打卡记录时间范围">{([7, 30, "all"] as const).map((value) => <button key={value} type="button" aria-pressed={range === value} onClick={() => setRange(value)}>{value === "all" ? "全部" : `最近 ${value} 天`}</button>)}</div>
          {grouped.length === 0 ? <p className="history-empty">{incomplete ? "部分数据未加载，请重试" : "这个时间范围还没有打卡记录"}</p> : <div className="history-timeline">{grouped.map(([day, dayEntries]) => <section className="history-day" key={day}><div className="history-day-heading"><h3><CalendarDays size={17} aria-hidden="true" />{formatHistoryDate(day, asOf)}</h3><span>{dayEntries.length} 次打卡</span></div><ul>{dayEntries.map(({ plan, task, record, path }) => <li className="history-entry" key={record.id}><span className="history-entry-icon" aria-hidden="true"><Check size={19} strokeWidth={2.6} /></span><div><strong>{task.content || task.step_name}</strong><p>{plan.name} / {path.join(" / ")}</p><small>{record.event_type === "BOOLEAN_COMPLETE" ? "完成打卡" : `累计完成 ${record.recorded_value ?? 0}`}</small></div><time>{record.recorded_at.slice(11, 16)}</time></li>)}</ul></section>)}</div>}
        </section>
        <section className="history-panel" aria-labelledby="history-plans-title"><div className="history-panel-title"><div><h2 id="history-plans-title">计划坚持情况</h2><p>每个学习方向的点滴积累</p></div></div>
          <p className="history-explanation">同一天打卡多次只算一天；今天未打卡时，连续天数从昨天计算。</p>
          {plans.length === 0 ? <p className="history-empty">暂无学习计划</p> : <div className="history-plans">{plans.map((item) => { const counts = countDays(item.entries, asOf); return <details className="history-plan" key={item.plan.id}><summary><span className="history-plan-name">{item.plan.name}<small>{item.steps.length ? "展开查看学习步骤" : "暂无学习步骤"}</small></span><span className="history-plan-metrics">{item.incomplete ? <small>数据未完整加载</small> : <><span><strong>{counts.total}</strong><small>累计天数</small></span><span><strong>{counts.streak}</strong><small>连续天数</small></span></>}</span></summary><div className="history-plan-body">{item.steps.length ? <ul>{item.steps.map((node) => <StepItem key={node.id} node={node} entries={item.entries} today={asOf} incomplete={item.incomplete} />)}</ul> : <p>此计划暂无步骤</p>}</div></details>; })}</div>}
        </section>
      </div>
      <p className="history-footnote">按北京时间的实际打卡日期统计；当前展示可查询的有效计划、步骤和任务记录。</p>
    </>}
  </div>;
}
