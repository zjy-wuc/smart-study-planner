"use client";

import { messages } from "@/messages";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowRight, Ellipsis, Play, Trash2 } from "lucide-react";

import { DraftScheduleEditor } from
  "@/components/plans/DraftScheduleEditor";

import { startPlan } from "@/services/plans.service";

import { PlanForm } from "@/components/plans/PlanForm";
import { PlanWorkflowNav, useDraftPlanView } from "@/components/plans/PlanWorkflowNav";
import { StepTreeEditor } from "@/components/plans/StepTreeEditor";
import {
  getPlan,
  updatePlan,
  deletePlan,
} from "@/services/plans.service";

import type {
  Plan,
  PlanCreate,
  PlanUpdate,
} from "@/types/plan";


import { PlanTasksPanel } from
  "@/components/tasks/PlanTasksPanel";

import { ActiveStepManager } from
  "@/components/plans/ActiveStepManager";

import { PlanLifecyclePanel } from
  "@/components/plans/PlanLifecyclePanel";
import { PlanReadOnlyOverview } from
  "@/components/plans/PlanReadOnlyOverview";

import type { EndPlanResult } from "@/types/plan";

import "@/components/css/PlanDetail.css";
const statusLabels = {
  DRAFT: messages.plans.statusDraft,
  ACTIVE: messages.common.statusActive,
  ENDED: messages.plans.statusEnded,
};


export default function PlanDetailPage() {
  const router = useRouter();
  const params = useParams<{ planId: string }>();

  const planId = Number(params.planId);

  const [plan, setPlan] = useState<Plan | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [notice, setNotice] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [draftDirty, setDraftDirty] = useState(false);
  const [managing, setManaging] = useState(false);
  const [stepCount, setStepCount] = useState<number | null>(null);
  const draftView = useDraftPlanView();


const [treeRevision, setTreeRevision] = useState(0);
const [starting, setStarting] = useState(false);


// 启动计划：从 DRAFT 进入 ACTIVE
async function handleStartPlan() {
  if (!plan || plan.status !== "DRAFT" || starting) {
    return;
  }

  const confirmed = window.confirm(
    messages.plans.startConfirm(plan.name),
  );

  if (!confirmed) {
    return;
  }

  setStarting(true);
  setError(null);
  setNotice(null);

  try {
    const result = await startPlan(plan.id);

    // 后端已确认启动成功，先更新本地状态
    setPlan((current) =>
      current
        ? { ...current, status: "ACTIVE" }
        : current,
    );

    setNotice(
      messages.plans.startSuccess(result.generated_count),
    );

    // 再获取数据库的最新计划详情
    try {
      const updated = await getPlan(plan.id);
      setPlan(updated);
    } catch {
      setNotice(
        messages.plans.startRefreshFailed(result.generated_count),
      );
    }

  } catch (err) {
    setError(
      err instanceof Error
        ? err.message
        : messages.plans.startFailed,
    );
  } finally {
    setStarting(false);
  }
}



  // 页面打开后获取计划详情
  useEffect(() => {
    let cancelled = false;

    async function loadPlan() {
      setLoading(true);
      setError(null);
      setPlan(null);
      setNotice(null);

      if (!Number.isSafeInteger(planId) || planId <= 0) {
        setError(messages.plans.invalidId);
        setLoading(false);
        return;
      }

      try {
        const result = await getPlan(planId);

        if (!cancelled) {
          setPlan(result);
        }

      } catch (err) {
        if (cancelled) {
          return;
        }


        setError(
          err instanceof Error
            ? err.message
            : messages.plans.fetchFailed,
        );

      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadPlan();

    return () => {
      cancelled = true;
    };
  }, [planId, router]);

  const isDraft = plan?.status === "DRAFT";
  useEffect(() => {
    if (isDraft && window.location.hash) window.scrollTo({ top: 0 });
  }, [draftView, isDraft]);



function handlePlanEnded(result: EndPlanResult) {
  // POST /end 已成功，使用后端确认的状态更新页面
  setPlan((current) =>
    current
      ? { ...current, status: result.status }
      : current,
  );

  // 让计划任务列表重新加载
  setTreeRevision((current) => current + 1);

  const message =
    result.end_mode === "EARLY"
      ? messages.plans.endedEarly(result.ended_task_count, result.deleted_task_count)
      : messages.plans.endedNormally;

  setNotice(message);
  setError(null);

  // 从后端重新读取最新计划详情
  void getPlan(result.plan_id)
    .then((updated) => {
      setPlan((current) =>
        current?.id === updated.id ? updated : current,
      );
    })
    .catch(() => {
      setNotice(
        messages.plans.latestDetailsFailed(message),
      );
    });
}


  // 修改计划
  async function handleSave(values: PlanCreate) {
    if (!plan) {
      return;
    }

    setNotice(null);

    const data: PlanUpdate = {
      name: values.name,
      description: values.description,
    };

    // ACTIVE 计划不能修改日期
    // 因此不向后端发送日期字段
    if (plan.status === "DRAFT") {
      data.start_date = values.start_date;
      data.end_date = values.end_date;
    }

    await updatePlan(planId, data);

    // 以数据库最新结果为准，避免页面显示旧状态
    const updated = await getPlan(planId);

    setPlan(updated);
    setNotice(messages.plans.updateSuccess);
  }


  // 删除计划
  async function handleDelete() {
    if (!plan || deleting) {
      return;
    }

    const confirmed = window.confirm(
      messages.plans.deleteConfirm(plan.name),
    );

    if (!confirmed) {
      return;
    }

    try {
      setDeleting(true);
      setError(null);

      await deletePlan(plan.id);

      router.replace("/plans");

    } catch (err) {

      setError(
        err instanceof Error
          ? err.message
          : messages.plans.deleteFailed,
      );

    } finally {
      setDeleting(false);
    }
  }


  if (loading) {
    return <p>{messages.plans.loadingDetails}</p>;
  }

  if (!plan) {
    return (
      <div className="space-y-4">
        <p role="alert" className="text-red-600">
          {error ?? messages.plans.notFound}
        </p>

        <Link href="/plans" className="text-blue-700">{messages.plans.backToList}</Link>
      </div>
    );
  }

  if (plan.status === "DRAFT") {
    const stepsHref = `/plans/${plan.id}/steps`;
    const allowLeave = () => !draftDirty || window.confirm(messages.plans.unsavedConfirm);

    return (
      <div className="plan-detail-page plan-workflow-page">
        <header className="plan-workflow-header">
          <div>
            <Link href="/plans" className="plan-step-workspace-back" onNavigate={(event) => {
              if (!allowLeave()) event.preventDefault();
            }}>{messages.plans.backToMyPlans}</Link>
            <div className="plan-workflow-title">
              <h1>{plan.name}</h1>
              <span>{messages.plans.statusDraft}</span>
            </div>
          </div>
          <details className="plan-workflow-menu">
            <summary aria-label={messages.plans.moreActions}><Ellipsis size={19} aria-hidden="true" /></summary>
            <div>
              <button type="button" disabled={deleting || starting} onClick={(event) => {
                event.currentTarget.closest("details")?.removeAttribute("open");
                void handleDelete();
              }}><Trash2 size={15} aria-hidden="true" />{messages.plans.delete}</button>
            </div>
          </details>
        </header>

        <PlanWorkflowNav view={draftView} planId={plan.id} onLeave={allowLeave} />

        {notice && <p role="status" className="plan-detail-notice">{notice}</p>}
        {error && <p role="alert" className="plan-detail-error">{error}</p>}

        <div hidden={draftView !== "basic"} className="plan-workflow-stage">
          <PlanForm
            key={`${plan.id}-${plan.updated_at}`}
            initialPlan={plan}
            onSubmit={handleSave}
            submitLabel={messages.common.saveChanges}
            onDirtyChange={setDraftDirty}
            footerAction={
              <Link href={stepsHref} className="plan-form-submit" onNavigate={(event) => {
                if (!allowLeave()) event.preventDefault();
              }}>{messages.plans.workflowSteps}<ArrowRight size={15} aria-hidden="true" /></Link>
            }
          />
        </div>

        <div hidden={draftView !== "confirm"} className="plan-workflow-stage">
          <section className="plan-workflow-card">
            <h2>{messages.plans.workflowConfirm}</h2>
            <p>{messages.plans.period(plan.start_date, plan.end_date)}</p>
            {stepCount !== null && <p>{messages.steps.stepCount(stepCount)}</p>}
          </section>
          <DraftScheduleEditor
            planId={plan.id}
            startDate={plan.start_date}
            endDate={plan.end_date}
            treeRevision={treeRevision}
            onStepCount={setStepCount}
          />
          <footer className="plan-workflow-footer">
            <button type="button" disabled={starting || deleting} onClick={() => {
              if (allowLeave()) void handleStartPlan();
            }} className="plan-detail-start-button">
              <Play size={17} fill="currentColor" aria-hidden="true" />
              {starting ? messages.plans.starting : messages.plans.start}
            </button>
          </footer>
        </div>
      </div>
    );
  }

  if (!managing) {
    return (
      <PlanReadOnlyOverview
        plan={plan}
        onManage={() => setManaging(true)}
      />
    );
  }

  return (
    <div className="plan-detail-page">
      <div className="plan-detail-navigation">
        <Link href="/plans">{messages.plans.backToMyPlans}</Link>
        <button type="button" onClick={() => setManaging(false)}>
          {messages.plans.backToPreview}
        </button>
      </div>

      <div className="plan-detail-heading">
        <div>
          <h1 className="text-2xl font-bold">
            {plan.name}
          </h1>

          <p className="mt-2 text-slate-500">{messages.plans.statusText(statusLabels[plan.status])}
          </p>
        </div>
      </div>


      {notice && <p role="status" className="plan-detail-notice">{notice}</p>}

      {error && <p role="alert" className="plan-detail-error">{error}</p>}

      {plan.status === "ENDED" ? (
        <div className="rounded-xl border bg-white p-6">
          <h2 className="font-semibold">{messages.plans.endedTitle}</h2>

          <p className="mt-3 text-slate-600">{messages.plans.period(plan.start_date, plan.end_date)}
          </p>

          <p className="mt-3 text-sm text-slate-500">{messages.plans.endedDescription}</p>
        </div>
      ) : (
        <>
          <h2 id="plan-basic" className="plan-detail-anchor text-xl font-semibold">
            {messages.plans.editDetails}
          </h2>

          <PlanForm
            key={`${plan.id}-${plan.updated_at}`}
            initialPlan={plan}
            onSubmit={handleSave}
            submitLabel={messages.common.saveChanges}
            datesLocked={plan.status === "ACTIVE"}
          />
        </>
      )}

      <section id="plan-actions" className="plan-detail-action-card plan-detail-anchor" aria-labelledby="plan-action-title">
        <div className="plan-detail-action-copy">
          <span data-status={plan.status}>{statusLabels[plan.status]}</span>
          <h2 id="plan-action-title">{messages.plans.actionTitle}</h2>
          <p>{plan.status === "ACTIVE" ? messages.plans.actionActiveDescription : messages.plans.actionEndedDescription}</p>
        </div>

        <div className="plan-detail-action-buttons">
          <button type="button" disabled={deleting} onClick={handleDelete} className="plan-detail-delete-button">
            <Trash2 size={17} aria-hidden="true" />
            {deleting ? messages.common.deleting : messages.plans.delete}
          </button>
        </div>
      </section>

{plan.status === "ACTIVE" ? (
  <ActiveStepManager
    plan={plan}
    manageHref={`/plans/${plan.id}/steps`}
    onChanged={() =>
      setTreeRevision((value) => value + 1)
    }
  />
) : (
  <StepTreeEditor
    planId={plan.id}
    status={plan.status}
    onChanged={() =>
      setTreeRevision((value) => value + 1)
    }
  />
)}


  <PlanTasksPanel
    key={`${plan.id}-${treeRevision}`}
    planId={plan.id}
    planStatus={plan.status}
  />


{plan.status === "ACTIVE" && (
  <PlanLifecyclePanel
    plan={plan}
    onEnded={handlePlanEnded}
  />
)}

    </div>
  );
}
