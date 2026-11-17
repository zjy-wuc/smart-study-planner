"use client";

import { messages } from "@/messages";

import Link from "next/link";

import { useDashboardData } from "@/hooks/useDashboardData";
import { PlanCard } from "@/components/dashboard/PlanCard";
import { WorkspaceIcon } from "@/components/ui/WorkspaceIcon";
import { LandscapeScene } from "@/components/common/LandscapeScene";


export default function PlansPage() {
  const {
    plans,
    plansError,
    loading,
    reload,
  } = useDashboardData();

  return (
    <section className="workspace-page plans-landscape-page">
      <LandscapeScene variant="mountains" />
      <div className="workspace-page-heading">
        <div>
          <h1 className="text-2xl font-bold">{messages.navigation.plans}</h1>
          <p className="mt-2 text-slate-500">{messages.plans.listDescription}</p>
        </div>

        <div className="workspace-heading-actions">
          <button type="button" onClick={reload} className="workspace-button workspace-button--secondary">
            <WorkspaceIcon name="refresh" />{messages.common.refresh}</button>
          <Link href="/plans/new" className="workspace-button workspace-button--primary">
            <WorkspaceIcon name="plus" />{messages.plans.create}</Link>
        </div>
      </div>

      {loading ? (
        <p role="status" className="workspace-loading">{messages.plans.loading}</p>
      ) : plansError ? (
        <p role="alert" className="workspace-feedback workspace-feedback--error">
          {plansError}
        </p>
      ) : plans.length === 0 ? (
        <p className="workspace-empty-state">{messages.plans.empty}</p>
      ) : (
        <div className="workspace-plan-grid">
          {plans.map((plan) => (
            <PlanCard key={plan.id} plan={plan} />
          ))}
        </div>
      )}

      <Link href="/" className="workspace-text-link workspace-back-link">{messages.navigation.backHome}</Link>
    </section>
  );
}
