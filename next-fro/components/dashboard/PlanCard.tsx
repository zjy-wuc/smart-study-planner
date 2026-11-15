
"use client";

import { useEffect, useState } from "react";

import { getPlanProgress } from "@/services/progress.service";
import type { Plan } from "@/types/plan";
import type { PlanProgress } from "@/types/progress";


const statusLabels = {
  DRAFT: "草稿",
  ACTIVE: "进行中",
  ENDED: "已结束",
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
    <div className="mt-4">
      {progressLoading ? (
        <p className="text-sm text-slate-500">正在加载完成率...</p>
      ) : progressError ? (
        <p className="text-sm text-red-600">进度暂时无法获取</p>
      ) : percent === null ? (
        <p className="text-sm text-slate-500">暂无可计算进度</p>
      ) : (
        <>
          <p className="text-sm">当前可统计进度：{percent}%</p>
          <div
            className="mt-2 h-2 overflow-hidden rounded-full bg-slate-200"
            role="progressbar"
            aria-label={`${plan.name}的可统计进度`}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={percent}
          >
            <div className="h-full rounded-full bg-blue-600" style={{ width: `${Math.min(100, Math.max(0, percent))}%` }} />
          </div>
          <p className="mt-2 text-xs text-slate-500">
            {progress?.computable_leaf_count}/{progress?.leaf_count} 个叶子参与计算
          </p>
        </>
      )}
    </div>
  );
}

export function PlanCard({ plan }: { plan: Plan }) {
  return (
    <article className="rounded-xl border border-slate-200 bg-white p-5">
      <div className="flex items-start justify-between gap-3">
        <h3 className="font-semibold">
          {plan.name}
        </h3>

        <span className="rounded-md bg-slate-100 px-2 py-1 text-xs">
          {statusLabels[plan.status]}
        </span>
      </div>

      <p className="mt-3 text-sm text-slate-500">
        {plan.start_date} ～ {plan.end_date}
      </p>

      {plan.status === "ACTIVE" && (
        <PlanProgressView key={plan.id} plan={plan} />
      )}

      {plan.status === "DRAFT" && (
        <p className="mt-4 text-sm text-slate-500">
          计划尚未开始
        </p>
      )}

      {plan.status === "ENDED" && (
        <p className="mt-4 text-sm text-slate-500">
          计划已结束
        </p>
      )}
    </article>
  );
}
