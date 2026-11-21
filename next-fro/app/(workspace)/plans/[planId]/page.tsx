"use client";

import { messages } from "@/messages";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";

import { DraftScheduleEditor } from
  "@/components/plans/DraftScheduleEditor";

import { startPlan } from "@/services/plans.service";

import { PlanForm } from "@/components/plans/PlanForm";
import { ApiError } from "@/lib/api/client";
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

import type { EndPlanResult } from "@/types/plan";
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
    if (err instanceof ApiError && err.status === 401) {
      router.replace("/login");
      return;
    }

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
          if (window.sessionStorage.getItem("new-plan-id") === String(result.id)) {
            window.sessionStorage.removeItem("new-plan-id");
            setNotice(messages.plans.draftCreated);
            window.setTimeout(() => document.getElementById("plan-steps")?.scrollIntoView({ behavior: "smooth", block: "start" }), 0);
          }
        }

      } catch (err) {
        if (cancelled) {
          return;
        }

        if (err instanceof ApiError && err.status === 401) {
          router.replace("/login");
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
      if (err instanceof ApiError && err.status === 401) {
        router.replace("/login");
        return;
      }

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

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <Link
        href="/plans"
        className="text-sm text-blue-700"
      >{messages.plans.backToMyPlans}</Link>

      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">
            {plan.name}
          </h1>

          <p className="mt-2 text-slate-500">{messages.plans.statusText(statusLabels[plan.status])}
          </p>
        </div>
      </div>

      {notice && (
        <p role="status" className="text-green-700">
          {notice}
        </p>
      )}

      {error && (
        <p role="alert" className="text-red-600">
          {error}
        </p>
      )}

      {plan.status === "ENDED" ? (
        <div className="rounded-xl border bg-white p-6">
          <h2 className="font-semibold">{messages.plans.endedTitle}</h2>

          <p className="mt-3 text-slate-600">{messages.plans.period(plan.start_date, plan.end_date)}
          </p>

          <p className="mt-3 text-sm text-slate-500">{messages.plans.endedDescription}</p>
        </div>
      ) : (
        <>
          <h2 className="text-xl font-semibold">
            {plan.status === "DRAFT"
              ? messages.plans.editDraft
              : messages.plans.editDetails}
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

    

{plan.status === "ACTIVE" ? (
  <ActiveStepManager
    plan={plan}
    onChanged={() =>
      setTreeRevision((value) => value + 1)
    }
  />
) : (
  <section id="plan-steps" className="rounded-xl border bg-white p-6 scroll-mt-6">
    <StepTreeEditor
      planId={plan.id}
      status={plan.status}
      onChanged={() =>
        setTreeRevision((value) => value + 1)
      }
    />
  </section>
)}


{plan.status === "DRAFT" && (
  <>
    <DraftScheduleEditor
      planId={plan.id}
      startDate={plan.start_date}
      endDate={plan.end_date}
      treeRevision={treeRevision}
    />

    <section className="space-y-4 rounded-xl border p-6">
      <h2 className="text-xl font-semibold">{messages.plans.startTitle}</h2>

      <p className="text-sm">{messages.plans.startChecklist}</p>

      <p className="text-sm">{messages.plans.startValidation}</p>

      <button
        type="button"
        disabled={starting}
        onClick={() => void handleStartPlan()}
        className="rounded bg-blue-600 px-5 py-3 text-white disabled:opacity-50"
      >
        {starting ? messages.plans.starting : messages.plans.start}
      </button>
    </section>
  </>
)}

{plan.status !== "DRAFT" && (
  <PlanTasksPanel
    key={`${plan.id}-${treeRevision}`}
    planId={plan.id}
    planStatus={plan.status}
  />
)}


{plan.status === "ACTIVE" && (
  <PlanLifecyclePanel
    plan={plan}
    onEnded={handlePlanEnded}
  />
)}


      <section className="rounded-xl border border-red-200 bg-white p-6">
        <h2 className="font-semibold text-red-700">{messages.plans.delete}</h2>

        <p className="mt-2 text-sm text-slate-600">{messages.plans.deleteDescription}</p>

        <button
          type="button"
          disabled={deleting}
          onClick={handleDelete}
          className="mt-4 rounded-lg border border-red-300 px-4 py-2 text-red-700 disabled:opacity-50"
        >
          {deleting ? messages.common.deleting : messages.plans.delete}
        </button>
      </section>
    </div>
  );
}
