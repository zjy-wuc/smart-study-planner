"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Check } from "lucide-react";

import { ActiveStepManager } from "@/components/plans/ActiveStepManager";
import { StepTreeEditor } from "@/components/plans/StepTreeEditor";
import { SaveSuccessDialog } from "@/components/ui/SaveSuccessDialog";
import { PlanWorkflowNav } from "@/components/plans/PlanWorkflowNav";
import { messages } from "@/messages";
import { getPlan } from "@/services/plans.service";

import type { Plan } from "@/types/plan";

import "@/components/css/PlanDetail.css";

const statusLabels = {
  DRAFT: messages.plans.statusDraft,
  ACTIVE: messages.common.statusActive,
  ENDED: messages.plans.statusEnded,
};

export default function PlanStepsPage() {
  const router = useRouter();
  const params = useParams<{ planId: string }>();
  const planId = Number(params.planId);

  const [plan, setPlan] = useState<Plan | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadPlan() {
      if (!Number.isSafeInteger(planId) || planId <= 0) {
        setError(messages.plans.invalidId);
        setLoading(false);
        return;
      }

      try {
        const result = await getPlan(planId);
        if (cancelled) return;

        setPlan(result);
        if (window.sessionStorage.getItem("new-plan-id") === String(result.id)) {
          window.sessionStorage.removeItem("new-plan-id");
          setNotice(messages.plans.draftCreated);
        }
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : messages.plans.fetchFailed);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadPlan();
    return () => {
      cancelled = true;
    };
  }, [planId, router]);

  if (loading) {
    return <p>{messages.plans.loadingDetails}</p>;
  }

  if (!plan) {
    return (
      <div className="space-y-4">
        <p role="alert" className="text-red-600">{error ?? messages.plans.notFound}</p>
        <Link href="/plans" className="text-blue-700">{messages.plans.backToList}</Link>
      </div>
    );
  }

  const detailHref = `/plans/${plan.id}`;
  const isDraft = plan.status === "DRAFT";
  const finishHref = isDraft ? `${detailHref}#plan-actions` : detailHref;

  return (
    <div className={isDraft ? "plan-step-workspace plan-workflow-page" : "plan-step-workspace"}>
      {isDraft ? (
        <header className="plan-workflow-header">
          <div>
            <Link href={`${detailHref}#plan-basic`} className="plan-step-workspace-back">
              <ArrowLeft size={15} aria-hidden="true" />{messages.plans.workflowBasic}
            </Link>
            <div className="plan-workflow-title">
              <h1>{plan.name}</h1>
              <span>{statusLabels.DRAFT}</span>
            </div>
          </div>
        </header>
      ) : (
      <header className="plan-step-workspace-header">
        <div>
          <Link href={detailHref} className="plan-step-workspace-back">
            <ArrowLeft size={15} aria-hidden="true" />
            {messages.plans.backToPlan}
          </Link>
          <h1>{messages.plans.stepWorkspaceTitle}</h1>
          <p>{messages.plans.stepWorkspaceDescription}</p>
        </div>

        <Link href={finishHref} className="plan-step-workspace-finish">
          <Check size={17} aria-hidden="true" />
          {messages.plans.finishStepSetup}
        </Link>
      </header>
      )}

      {isDraft && <PlanWorkflowNav view="steps" planId={plan.id} />}

      {!isDraft && <div className="plan-step-context">
        <strong>{plan.name}</strong>
        <span>{statusLabels[plan.status]}</span>
        <small>{messages.plans.period(plan.start_date, plan.end_date)}</small>
      </div>}

      {error && <p role="alert" className="plan-detail-error">{error}</p>}

      {plan.status === "ACTIVE" ? (
        <ActiveStepManager plan={plan} />
      ) : (
        <StepTreeEditor planId={plan.id} status={plan.status} />
      )}
      {isDraft && (
        <footer className="plan-workflow-footer">
          <Link href={finishHref} className="plan-step-workspace-finish">
            <Check size={17} aria-hidden="true" />{messages.plans.finishStepSetup}
          </Link>
        </footer>
      )}
      <SaveSuccessDialog message={notice} onClose={() => setNotice(null)} />
    </div>
  );
}
