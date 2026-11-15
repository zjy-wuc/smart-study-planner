
"use client";

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


const statusLabels = {
  DRAFT: "草稿",
  ACTIVE: "进行中",
  ENDED: "已结束",
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
    `确定开始「${plan.name}」吗？\n\n` +
    "后端将生成整个计划周期的每日任务。\n" +
    "开始后不能再修改计划起止日期，" +
    "草稿节点编辑规则也将受到限制。",
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
      `计划启动成功，已生成 ${result.generated_count} 条每日任务`,
    );

    // 再获取数据库的最新计划详情
    try {
      const updated = await getPlan(plan.id);
      setPlan(updated);
    } catch {
      setNotice(
        `计划已经启动，生成了 ${result.generated_count} 条任务。` +
        "但详情刷新失败，请刷新页面确认最新数据。",
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
        : "计划启动失败",
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
        setError("无效的计划 ID");
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

        if (err instanceof ApiError && err.status === 401) {
          router.replace("/login");
          return;
        }

        setError(
          err instanceof Error
            ? err.message
            : "获取计划失败",
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
    setNotice("计划修改成功");
  }


  // 删除计划
  async function handleDelete() {
    if (!plan || deleting) {
      return;
    }

    const confirmed = window.confirm(
      `确定删除学习计划「${plan.name}」吗？\n\n` +
      "计划将从当前有效列表中移除，" +
      "相关历史数据不会自动恢复。",
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
          : "删除计划失败",
      );

    } finally {
      setDeleting(false);
    }
  }


  if (loading) {
    return <p>正在加载计划详情...</p>;
  }

  if (!plan) {
    return (
      <div className="space-y-4">
        <p role="alert" className="text-red-600">
          {error ?? "计划不存在"}
        </p>

        <Link href="/plans" className="text-blue-700">
          返回计划列表
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <Link
        href="/plans"
        className="text-sm text-blue-700"
      >
        返回我的计划
      </Link>

      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">
            {plan.name}
          </h1>

          <p className="mt-2 text-slate-500">
            状态：{statusLabels[plan.status]}
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
          <h2 className="font-semibold">计划已结束</h2>

          <p className="mt-3 text-slate-600">
            执行周期：{plan.start_date}
            {" ～ "}
            {plan.end_date}
          </p>

          <p className="mt-3 text-sm text-slate-500">
            已结束的计划不能继续编辑。
            当前版本不显示最终完成率。
          </p>
        </div>
      ) : (
        <>
          <h2 className="text-xl font-semibold">
            {plan.status === "DRAFT"
              ? "编辑草稿计划"
              : "编辑计划基本信息"}
          </h2>

          <PlanForm
            key={`${plan.id}-${plan.updated_at}`}
            initialPlan={plan}
            onSubmit={handleSave}
            submitLabel="保存修改"
            datesLocked={plan.status === "ACTIVE"}
          />
        </>
      )}

    
<section className="rounded-xl border bg-white p-6">
  <StepTreeEditor
    planId={plan.id}
    status={plan.status}
    onChanged={() => {
      setTreeRevision((value) => value + 1);
    }}
  />
</section>

{plan.status === "DRAFT" && (
  <>
    <DraftScheduleEditor
      planId={plan.id}
      startDate={plan.start_date}
      endDate={plan.end_date}
      treeRevision={treeRevision}
    />

    <section className="space-y-4 rounded-xl border p-6">
      <h2 className="text-xl font-semibold">
        正式开始计划
      </h2>

      <p className="text-sm">
        开始前请检查：
        树形步骤完整、叶子规则正确，
        每日自定义安排已经填写完成，
        NUMERIC 手动安排的数量合计等于总目标。
      </p>

      <p className="text-sm">
        点击开始后，FastAPI 会再次完成全部校验。
        如果有缺失或冲突，计划不会进入 ACTIVE。
      </p>

      <button
        type="button"
        disabled={starting}
        onClick={() => void handleStartPlan()}
        className="rounded bg-blue-600 px-5 py-3 text-white disabled:opacity-50"
      >
        {starting ? "正在启动计划..." : "开始执行计划"}
      </button>
    </section>
  </>
)}

      <section className="rounded-xl border border-red-200 bg-white p-6">
        <h2 className="font-semibold text-red-700">
          删除计划
        </h2>

        <p className="mt-2 text-sm text-slate-600">
          删除采用逻辑删除方式。
          请先确认不再需要在当前计划列表中使用它。
        </p>

        <button
          type="button"
          disabled={deleting}
          onClick={handleDelete}
          className="mt-4 rounded-lg border border-red-300 px-4 py-2 text-red-700 disabled:opacity-50"
        >
          {deleting ? "正在删除..." : "删除计划"}
        </button>
      </section>
    </div>
  );
}
