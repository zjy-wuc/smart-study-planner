
"use client";

import Link from "next/link";

import { useDashboardData } from "@/hooks/useDashboardData";
import { PlanCard } from "@/components/dashboard/PlanCard";


export default function PlansPage() {
  const {
    plans,
    plansError,
    loading,
    reload,
  } = useDashboardData();

  return (
    <section className="workspace-page space-y-5">
      <div className="workspace-page-heading workspace-plans-heading flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">我的计划</h1>
          <Link
  href="/plans/new"
  className="workspace-button workspace-button--primary rounded-lg bg-blue-600 px-4 py-2 text-white"
>
  创建计划
</Link>
          <p className="mt-2 text-slate-500">
            查看全部学习计划
          </p>
        </div>

        <button type="button" onClick={reload} className="workspace-button workspace-button--secondary">
          刷新
        </button>
      </div>

      {loading ? (
        <p>正在加载计划...</p>
      ) : plansError ? (
        <p role="alert" className="text-red-600">
          {plansError}
        </p>
      ) : plans.length === 0 ? (
        <p className="workspace-empty-state">暂无学习计划</p>
      ) : (
        <div className="workspace-plan-grid grid gap-4 lg:grid-cols-3">
          {plans.map((plan) => (
            <PlanCard key={plan.id} plan={plan} />
          ))}
        </div>
      )}

      <Link href="/" className="workspace-text-link text-blue-700">
        返回首页
      </Link>
    </section>
  );
}
