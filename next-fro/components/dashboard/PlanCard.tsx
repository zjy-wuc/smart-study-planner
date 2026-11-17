"use client";

import { messages } from "@/messages";
import Link from "next/link";
import { useEffect, useState } from "react";

import { getPlanProgress } from "@/services/progress.service";
import type { Plan } from "@/types/plan";
import type { PlanProgress } from "@/types/progress";
import { WorkspaceIcon } from "@/components/ui/WorkspaceIcon";


const statusLabels = {
  DRAFT: messages.plans.statusDraft,
  ACTIVE: messages.common.statusActive,
  ENDED: messages.plans.statusEnded,
};


function PlanProgressView({ plan }: { plan: Plan }) {
  const [progress, setProgress] =
    useState<PlanProgress | null>(null);

  const [progressLoading, setProgressLoading] =
    useState(true);

  const [progressError, setProgressError] =
    useState(false);

  useEffect(() => {
    let cancelled = false;

    getPlanProgress(plan.id)
      .then((result) => {
        if (!cancelled) {
          setProgress(result);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setProgressError(true);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setProgressLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [plan.id]);

  const percent = progress?.progress_percent ?? null;

  return (
    <div className="workspace-plan-progress">
      {progressLoading ? (
        <p className="workspace-muted">{messages.progress.loading}</p>
      ) : progressError ? (
        <p className="workspace-inline-error">{messages.progress.unavailable}</p>
      ) : percent === null ? (
        <p className="workspace-muted">{messages.progress.notComputable}</p>
      ) : (
        <>
          <p className="workspace-progress-label"><span>{messages.progress.current}</span><strong>{percent}%</strong></p>
          <div
            className="workspace-progress-track"
            role="progressbar"
            aria-label={messages.progress.planLabel(plan.name)}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={percent}
          >
            <div className="workspace-progress-fill" style={{ width: `${Math.min(100, Math.max(0, percent))}%` }} />
          </div>
          <p className="workspace-progress-caption">
            {messages.progress.leafCount(progress?.computable_leaf_count, progress?.leaf_count)}</p>
        </>
      )}
    </div>
  );
}

export function PlanCard({ plan }: { plan: Plan }) {
  return (
    <article className="workspace-plan-card" data-status={plan.status}>
      <div className="workspace-plan-card-heading">
        <h3>
          <Link href={`/plans/${plan.id}`} className="workspace-plan-link">
            {plan.name}
          </Link>
        </h3>

        <span className="workspace-plan-status" data-status={plan.status}>
          {statusLabels[plan.status]}
        </span>
      </div>

      <p className="workspace-plan-date">
        <WorkspaceIcon name="calendar" />
        {plan.start_date} ～ {plan.end_date}
      </p>

      {plan.status === "ACTIVE" && (
        <PlanProgressView key={plan.id} plan={plan} />
      )}

      {plan.status === "DRAFT" && (
        <p className="workspace-plan-note">{messages.plans.notStarted}</p>
      )}

      {plan.status === "ENDED" && (
        <p className="workspace-plan-note">{messages.plans.endedTitle}</p>
      )}
    </article>
  );
}
