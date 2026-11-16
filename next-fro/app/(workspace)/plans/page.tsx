
"use client";

import Link from "next/link";

import { useDashboardData } from "@/hooks/useDashboardData";
import { PlanCard } from "@/components/dashboard/PlanCard";
import { WorkspaceIcon } from "@/components/ui/WorkspaceIcon";


export default function PlansPage() {
  const {
    plans,
    plansError,
    loading,
    reload,
  } = useDashboardData();

  return (
    <section className="workspace-page">
      <div className="workspace-page-heading">
        <div>
          <h1 className="text-2xl font-bold">我的计划</h1>
          <p className="mt-2 text-slate-500">
            查看全部学习计划
          </p>
        </div>

        <div className="workspace-heading-actions">
          <button type="button" onClick={reload} className="workspace-button workspace-button--secondary">
            <WorkspaceIcon name="refresh" />
            刷新
          </button>
          <Link href="/plans/new" className="workspace-button workspace-button--primary">
            <WorkspaceIcon name="plus" />
            创建计划
          </Link>
        </div>
      </div>

      {loading ? (
        <p role="status" className="workspace-loading">正在加载计划...</p>
      ) : plansError ? (
        <p role="alert" className="workspace-feedback workspace-feedback--error">
          {plansError}
        </p>
      ) : plans.length === 0 ? (
        <p className="workspace-empty-state">暂无学习计划</p>
      ) : (
        <div className="workspace-plan-grid">
          {plans.map((plan) => (
            <PlanCard key={plan.id} plan={plan} />
          ))}
        </div>
      )}

      <Link href="/" className="workspace-text-link workspace-back-link">
        返回首页
      </Link>
    </section>
  );
}
