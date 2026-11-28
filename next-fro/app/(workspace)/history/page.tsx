"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { Check, ChevronDown } from "lucide-react";
import { messages } from "@/messages";
import { aiPractice } from "@/messages/zh-CN/ai-practice";
import { listPractices } from "@/services/ai-practice.service";
import { getFocusHistory } from "@/services/focus.service";
import {
  getCheckinSummary,
  getCheckins,
  getReviewHistory,
  type HistoryRange,
} from "@/services/history.service";
import type { FocusHistory } from "@/types/focus";
import type { PracticeList } from "@/types/ai-practice";
import type {
  CheckinRecord,
  CheckinSummary,
  HistoryPage,
  HistoryStep,
  ReviewRecord,
} from "@/types/history";
import "@/components/css/History.css";

type Tab = "checkins" | "focus" | "reviews" | "practice";
type HistoryData =
  | HistoryPage<CheckinRecord>
  | FocusHistory
  | HistoryPage<ReviewRecord>
  | PracticeList;

function todayInBeijing() {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

function previousDay(day: string) {
  const date = new Date(`${day}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() - 1);
  return date.toISOString().slice(0, 10);
}

function countDays(dates: string[], today: string) {
  const unique = new Set(dates.filter((day) => day <= today));
  let cursor = unique.has(today) ? today : previousDay(today);
  let streak = 0;
  while (unique.has(cursor)) {
    streak += 1;
    cursor = previousDay(cursor);
  }
  return { total: unique.size, streak };
}

function formatHistoryDate(day: string, today: string) {
  const [year, month, date] = day.split("-").map(Number);
  const weekday = [
    messages.common.weekdaySunday,
    messages.common.weekdayMonday,
    messages.common.weekdayTuesday,
    messages.common.weekdayWednesday,
    messages.common.weekdayThursday,
    messages.common.weekdayFriday,
    messages.common.weekdaySaturday,
  ][new Date(Date.UTC(year, month - 1, date)).getUTCDay()];
  return messages.history.dateHeading(
    month,
    date,
    weekday,
    day === today ? messages.history.todaySuffix : "",
  );
}

function stepPath(stepId: number, steps: HistoryStep[]) {
  const byId = new Map(steps.map((step) => [step.id, step]));
  const names: string[] = [];
  const seen = new Set<number>();
  let step = byId.get(stepId);
  while (step && !seen.has(step.id)) {
    names.unshift(step.name);
    seen.add(step.id);
    step = step.parent_id === null ? undefined : byId.get(step.parent_id);
  }
  return names.join(" / ");
}

function StepItem({
  node,
  summary,
  today,
}: {
  node: HistoryStep;
  summary: CheckinSummary;
  today: string;
}) {
  const descendants = new Set<number>([node.id]);
  const collect = (id: number) => {
    for (const child of summary.steps.filter(
      (step) => step.parent_id === id && !descendants.has(step.id),
    )) {
      descendants.add(child.id);
      collect(child.id);
    }
  };
  collect(node.id);
  const counts = countDays(
    summary.dates
      .filter((item) => descendants.has(item.step_id))
      .map((item) => item.checkin_date),
    today,
  );
  const children = summary.steps.filter((step) => step.parent_id === node.id);
  return (
    <li className="history-step">
      <div className="history-step-row">
        <span>
          {node.name}
          {node.deleted_at && (
            <small className="history-deleted-step">
              {" "}
              · {messages.history.stepDeleted}
            </small>
          )}
        </span>
        <span className="history-step-count">
          {messages.history.dayCounts(counts.total, counts.streak)}
        </span>
      </div>
      {children.length > 0 && (
        <ul className="history-step-children">
          {children.map((child) => (
            <StepItem
              key={child.id}
              node={child}
              summary={summary}
              today={today}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

function HistoryContent() {
  const params = useSearchParams();
  const requestedPlan = Number(params.get("plan_id"));
  const [planId, setPlanId] = useState<number | null>(
    Number.isInteger(requestedPlan) && requestedPlan > 0 ? requestedPlan : null,
  );
  const [tab, setTab] = useState<Tab>("checkins");
  const [range, setRange] = useState<HistoryRange>(7);
  const [page, setPage] = useState(1);
  const [summary, setSummary] = useState<CheckinSummary | null>(null);
  const [data, setData] = useState<HistoryData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [summaryError, setSummaryError] = useState("");
  const [revision, setRevision] = useState(0);
  const today = todayInBeijing();

  useEffect(() => {
    let live = true;
    getCheckinSummary()
      .then((result) => {
        if (live) {
          setSummary(result);
          setSummaryError("");
        }
      })
      .catch((cause) => {
        if (live)
          setSummaryError(
            cause instanceof Error
              ? cause.message
              : messages.common.loadFailedRetry,
          );
      });
    return () => {
      live = false;
    };
  }, [revision]);

  useEffect(() => {
    let live = true;
    Promise.resolve()
      .then(() => {
        if (live) {
          setLoading(true);
          setData(null);
          setError("");
        }
        const request: Promise<HistoryData> =
          tab === "focus"
            ? getFocusHistory(page, 20)
            : tab === "reviews"
              ? getReviewHistory(page)
              : tab === "practice"
                ? listPractices(page)
                : getCheckins(range, page, planId);
        return request;
      })
      .then((result) => {
        if (live) setData(result);
      })
      .catch((cause) => {
        if (live)
          setError(
            cause instanceof Error
              ? cause.message
              : messages.common.loadFailedRetry,
          );
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, [tab, range, planId, page, revision]);

  const checkins =
    tab === "checkins" ? (data as HistoryPage<CheckinRecord> | null) : null;
  const focus = tab === "focus" ? (data as FocusHistory | null) : null;
  const reviews =
    tab === "reviews" ? (data as HistoryPage<ReviewRecord> | null) : null;
  const practices = tab === "practice" ? (data as PracticeList | null) : null;
  const grouped = useMemo(() => {
    const groups = new Map<string, CheckinRecord[]>();
    for (const record of checkins?.items ?? []) {
      const day = record.recorded_at.slice(0, 10);
      groups.set(day, [...(groups.get(day) ?? []), record]);
    }
    return [...groups.entries()];
  }, [checkins]);
  const total =
    tab === "checkins"
      ? checkins?.total
      : tab === "focus"
        ? focus?.total
        : tab === "reviews"
          ? reviews?.total
          : practices?.total;
  const totalPages = Math.max(
    1,
    Math.ceil((total ?? 0) / (tab === "practice" ? 10 : 20)),
  );
  const refresh = () => setRevision((value) => value + 1);
  const chooseTab = (value: Tab) => {
    setTab(value);
    setPage(1);
    setError("");
  };

  return (
    <div className="workspace-page history-page">
      <header className="history-page-header">
        <div>
          <h1>{messages.navigation.history}</h1>
          <p>{messages.history.subtitle}</p>
        </div>
        <button
          className="history-refresh"
          type="button"
          onClick={refresh}
          disabled={loading}
        >
          {messages.history.refresh}
        </button>
      </header>
      <nav className="history-tabs" aria-label={messages.navigation.history}>
        {(["checkins", "focus", "reviews", "practice"] as const).map(
          (value) => (
            <button
              key={value}
              type="button"
              aria-current={tab === value ? "page" : undefined}
              onClick={() => chooseTab(value)}
            >
              {value === "checkins"
                ? messages.history.checkinsTab
                : value === "focus"
                  ? messages.history.focusTab
                  : value === "reviews"
                    ? messages.history.reviewsTab
                    : messages.history.practiceTab}
            </button>
          ),
        )}
      </nav>
      {error && (
        <div
          role="alert"
          className="workspace-feedback workspace-feedback--error"
        >
          {error}{" "}
          <button type="button" onClick={refresh}>
            {messages.common.retry}
          </button>
        </div>
      )}
      {tab === "checkins" && summaryError && (
        <div
          role="alert"
          className="workspace-feedback workspace-feedback--error"
        >
          {summaryError}{" "}
          <button type="button" onClick={refresh}>
            {messages.common.retry}
          </button>
        </div>
      )}
      {tab === "checkins" && (
        <div className="history-toolbar">
          <div
            className="history-filters"
            data-range={range}
            role="group"
            aria-label={messages.history.rangeLabel}
          >
            {([7, 30, "all"] as const).map((value) => (
              <button
                key={value}
                type="button"
                aria-pressed={range === value}
                onClick={() => {
                  setRange(value);
                  setPage(1);
                }}
              >
                {value === "all"
                  ? messages.common.all
                  : messages.common.recentDays(value)}
              </button>
            ))}
          </div>
          <label>
            {messages.history.planFilter}
            <select
              value={planId ?? ""}
              onChange={(event) => {
                setPlanId(
                  event.target.value ? Number(event.target.value) : null,
                );
                setPage(1);
              }}
            >
              <option value="">{messages.history.allPlans}</option>
              {summary?.plans.map((plan) => (
                <option key={plan.id} value={plan.id}>
                  {plan.name}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}
      {loading ? (
        <p role="status" className="workspace-loading">
          {messages.history.loading}
        </p>
      ) : error ? null : tab === "checkins" ? (
        <div className="history-layout">
          <section
            className="history-panel"
            aria-labelledby="history-timeline-title"
          >
            <div className="history-panel-title">
              <div>
                <h2 id="history-timeline-title">
                  {messages.history.recordsTitle}
                </h2>
                <p>{messages.history.checkinCount(checkins?.total ?? 0)}</p>
              </div>
            </div>
            {grouped.length === 0 ? (
              <p className="history-empty">{messages.history.emptyRange}</p>
            ) : (
              <div
                className="history-timeline"
                key={`${range}-${page}-${planId}`}
              >
                {grouped.map(([day, records]) => (
                  <section className="history-day" key={day}>
                    <div className="history-day-heading">
                      <h3>
                        <time dateTime={day}>
                          {formatHistoryDate(day, today)}
                        </time>
                      </h3>
                      <span>
                        {messages.history.checkinCount(records.length)}
                      </span>
                    </div>
                    <ul>
                      {records.map((record) => (
                        <li className="history-entry" key={record.id}>
                          <span
                            className="history-entry-icon"
                            aria-hidden="true"
                          >
                            <Check size={16} strokeWidth={2.4} />
                          </span>
                          <div>
                            <strong>
                              {record.content || record.step_name}
                            </strong>
                            <p>
                              {record.plan_name} /{" "}
                              {summary
                                ? stepPath(record.step_id, summary.steps)
                                : record.step_name}
                            </p>
                            <small>
                              {record.event_type === "BOOLEAN_COMPLETE"
                                ? messages.tasks.booleanCheckin
                                : messages.tasks.recordedTotal(
                                    record.recorded_value ?? 0,
                                  )}
                              {record.task_deleted_at &&
                                ` · ${messages.history.taskDeleted}`}
                            </small>
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
          <section
            className="history-panel"
            aria-labelledby="history-plans-title"
          >
            <div className="history-panel-title">
              <div>
                <h2 id="history-plans-title">{messages.history.plansTitle}</h2>
                <p>{messages.history.plansSubtitle}</p>
              </div>
            </div>
            <p className="history-explanation">
              {messages.history.streakExplanation}
            </p>
            <div className="history-plans">
              {summary?.plans.map((plan) => {
                const counts = countDays(
                  summary.dates
                    .filter((item) => item.plan_id === plan.id)
                    .map((item) => item.checkin_date),
                  today,
                );
                return (
                  <details className="history-plan" key={plan.id}>
                    <summary>
                      <span className="history-plan-name">{plan.name}</span>
                      <span className="history-plan-metrics">
                        <span>
                          <strong>{counts.total}</strong>
                          <small>{messages.history.totalDays}</small>
                        </span>
                        <span>
                          <strong>{counts.streak}</strong>
                          <small>{messages.history.streakDays}</small>
                        </span>
                      </span>
                      <ChevronDown
                        className="history-plan-chevron"
                        size={16}
                        aria-hidden="true"
                      />
                    </summary>
                    <div className="history-plan-body">
                      <ul>
                        {summary.steps
                          .filter(
                            (step) =>
                              step.plan_id === plan.id &&
                              (step.parent_id === null ||
                                !summary.steps.some(
                                  (parent) => parent.id === step.parent_id,
                                )),
                          )
                          .map((step) => (
                            <StepItem
                              key={step.id}
                              node={step}
                              summary={summary}
                              today={today}
                            />
                          ))}
                      </ul>
                    </div>
                  </details>
                );
              })}
            </div>
          </section>
        </div>
      ) : (
        <section className="history-panel history-secondary-panel">
          <div className="history-panel-title">
            <h2>
              {tab === "focus"
                ? messages.history.focusTab
                : tab === "reviews"
                  ? messages.history.reviewsTab
                  : messages.history.practiceTab}
            </h2>
          </div>
          <p>
            {tab === "focus"
              ? messages.history.focusCount(focus?.total ?? 0)
              : tab === "reviews"
                ? messages.history.reviewCount(reviews?.total ?? 0)
                : `${practices?.total ?? 0} ${aiPractice.historyTotal}`}
          </p>
          <ul className="history-secondary-list">
            {tab === "focus"
              ? focus?.items.map((item) => (
                  <li key={item.id}>
                    <strong>
                      {item.session_type === "POMODORO"
                        ? messages.focus.pomodoro
                        : messages.focus.stopwatch}
                    </strong>
                    <span>
                      {item.status === "COMPLETED"
                        ? messages.focus.completedStatus
                        : messages.focus.cancelled}{" "}
                      ·{" "}
                      {messages.focus.recordDuration(
                        Math.floor(item.focused_seconds / 60),
                      )}
                      {item.plan_id &&
                        ` · ${messages.history.relatedPlan(summary?.plans.find((plan) => plan.id === item.plan_id)?.name ?? `#${item.plan_id}`)}`}
                    </span>
                    <time>{item.focus_date}</time>
                  </li>
                ))
              : tab === "reviews"
                ? reviews?.items.map((item) => (
                    <li key={item.id}>
                      <strong>
                        {item.note_deleted_at ? (
                          item.note_title
                        ) : (
                          <Link href={`/knowledge/${item.note_id}`}>
                            {item.note_title}
                          </Link>
                        )}
                      </strong>
                      <span>
                        {item.note_deleted_at
                          ? messages.history.noteDeleted
                          : messages.history.reviewsTab}
                        {item.plan_id &&
                          ` · ${messages.history.relatedPlan(summary?.plans.find((plan) => plan.id === item.plan_id)?.name ?? `#${item.plan_id}`)}`}
                      </span>
                      <time>
                        {item.reviewed_at.slice(0, 16).replace("T", " ")}
                      </time>
                    </li>
                  ))
                : practices?.items.map((item) => (
                    <li key={item.id}>
                      <strong>
                        <Link href={`/ai/practice/history/${item.id}`}>
                          {item.note_title_snapshot}
                        </Link>
                      </strong>
                      <span>
                        {item.question_count} {aiPractice.questionUnit} ·{" "}
                        {item.score} / 100
                      </span>
                      <time>
                        {item.created_at.slice(0, 16).replace("T", " ")}
                      </time>
                    </li>
                  ))}
          </ul>
          {!total && (
            <p className="history-empty">{messages.history.emptyRecords}</p>
          )}
          {tab === "practice" && (
            <Link className="history-full-link" href="/ai/practice/history">
              {messages.history.openPractice} →
            </Link>
          )}
        </section>
      )}
      {!loading && !error && totalPages > 1 && (
        <nav
          className="history-pagination"
          aria-label={messages.navigation.history}
        >
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
          >
            {messages.history.previous}
          </button>
          <span>{messages.history.pagination(page, totalPages)}</span>
          <button
            type="button"
            disabled={page >= totalPages}
            onClick={() => setPage(page + 1)}
          >
            {messages.history.next}
          </button>
        </nav>
      )}
      <p className="history-footnote">{messages.history.dataScope}</p>
    </div>
  );
}

export default function HistoryPage() {
  return (
    <Suspense fallback={<p role="status">{messages.history.loading}</p>}>
      <HistoryContent />
    </Suspense>
  );
}
