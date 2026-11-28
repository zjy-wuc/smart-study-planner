"use client";

import { messages } from "@/messages";

import Link from "next/link";
import { useMemo, useState } from "react";

import { useDashboardData } from "@/hooks/useDashboardData";
import { isOpenTodayTask } from "@/lib/tasks/today-presentation";
import { PlanCard } from "@/components/dashboard/PlanCard";
import { WorkspaceIcon } from "@/components/ui/WorkspaceIcon";
import type { PlanStatus } from "@/types/plan";

import "@/components/css/PlansPage.css";


export default function PlansPage() {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<PlanStatus | "ALL">("ALL");
  const [sort, setSort] = useState<"UPDATED" | "START" | "END">("UPDATED");
  const {
    plans,
    tasks,
    plansError,
    loading,
    reload,
  } = useDashboardData();

  const visiblePlans = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return plans
      .filter((plan) =>
        (status === "ALL" || plan.status === status) &&
        plan.name.toLowerCase().includes(keyword),
      )
      .sort((left, right) => {
        const key = sort === "START" ? "start_date" : sort === "END" ? "end_date" : "updated_at";
        return right[key].localeCompare(left[key]);
      });
  }, [plans, search, sort, status]);

  const counts = useMemo(() => ({
    active: plans.filter((plan) => plan.status === "ACTIVE").length,
    ended: plans.filter((plan) => plan.status === "ENDED").length,
  }), [plans]);

  return (
    <section className="workspace-page plans-page">
      <div className="workspace-page-heading">
        <div>
          <h1 className="text-2xl font-bold">{messages.navigation.plans}</h1>
          <p className="mt-2 text-slate-500">{messages.plans.listDescription}</p>
        </div>

        <div className="workspace-heading-actions">
          <label className="workspace-search-field plans-search">
            <WorkspaceIcon name="search" />
            <input
              type="search"
              className="workspace-search"
              aria-label={messages.navigation.searchLabel}
              placeholder={messages.navigation.searchPlaceholder}
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </label>
          <button type="button" onClick={reload} className="workspace-button workspace-button--secondary">
            <WorkspaceIcon name="refresh" />{messages.common.refresh}</button>
          <Link href="/plans/new" className="workspace-button workspace-button--primary">
            <WorkspaceIcon name="plus" />{messages.plans.create}</Link>
        </div>
      </div>

      {!loading && !plansError && (
        <>
          <section className="plans-overview" aria-label={messages.plans.listDescription}>
            <article><span>{messages.plans.overviewActive}</span><strong>{counts.active}</strong></article>
            <article><span>{messages.plans.overviewToday}</span><strong>{tasks.filter(isOpenTodayTask).length}</strong></article>
            <article><span>{messages.plans.overviewEnded}</span><strong>{counts.ended}</strong></article>
          </section>
          <div className="plans-toolbar">
            <div className="plans-filter" role="group" aria-label={messages.plans.filterLabel}>
              {(["ALL", "ACTIVE", "DRAFT", "ENDED"] as const).map((value) => <button key={value} type="button" aria-pressed={status === value} onClick={() => setStatus(value)}>{value === "ALL" ? messages.plans.filterAll : value === "ACTIVE" ? messages.common.statusActive : value === "DRAFT" ? messages.plans.statusDraft : messages.plans.statusEnded}</button>)}
            </div>
            <label className="plans-sort"><span>{messages.plans.sortLabel}</span><select value={sort} onChange={(event) => setSort(event.target.value as typeof sort)}><option value="UPDATED">{messages.plans.sortUpdated}</option><option value="START">{messages.plans.sortStart}</option><option value="END">{messages.plans.sortEnd}</option></select></label>
          </div>
          {search.trim() && <p className="plans-search-count" role="status">{messages.plans.searchResultCount(visiblePlans.length)}</p>}
        </>
      )}

      {loading ? (
        <p role="status" className="workspace-loading">{messages.plans.loading}</p>
      ) : plansError ? (
        <p role="alert" className="workspace-feedback workspace-feedback--error">
          {plansError}
        </p>
      ) : visiblePlans.length === 0 ? (
        <p className="workspace-empty-state">{plans.length ? messages.plans.noFilteredPlans : messages.plans.empty}</p>
      ) : (
        <div className="workspace-plan-grid">
          {visiblePlans.map((plan) => (
            <PlanCard key={plan.id} plan={plan} variant="list" />
          ))}
        </div>
      )}

      <Link href="/" className="workspace-text-link workspace-back-link">{messages.navigation.backHome}</Link>
    </section>
  );
}
