
"use client";
import Link from "next/link";
import { useEffect, useState } from "react";

import { getPlanProgress } from "@/services/progress.service";
import type { Plan } from "@/types/plan";
import type { PlanProgress } from "@/types/progress";
import { WorkspaceIcon } from "@/components/ui/WorkspaceIcon";


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
    <div className="workspace-plan-progress">
      {progressLoading ? (
        <p className="workspace-muted">正在加载完成率...</p>
      ) : progressError ? (
        <p className="workspace-inline-error">进度暂时无法获取</p>
      ) : percent === null ? (
        <p className="workspace-muted">暂无可计算进度</p>
      ) : (
        <>
          <p className="workspace-progress-label"><span>当前可统计进度</span><strong>{percent}%</strong></p>
          <div
            className="workspace-progress-track"
            role="progressbar"
            aria-label={`${plan.name}的可统计进度`}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={percent}
          >
            <div className="workspace-progress-fill" style={{ width: `${Math.min(100, Math.max(0, percent))}%` }} />
          </div>
          <p className="workspace-progress-caption">
            {progress?.computable_leaf_count}/{progress?.leaf_count} 个叶子参与计算
          </p>
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
        <p className="workspace-plan-note">
          计划尚未开始
        </p>
      )}

      {plan.status === "ENDED" && (
        <p className="workspace-plan-note">
          计划已结束
        </p>
      )}
    </article>
  );
}
