
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
    <section className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">我的计划</h1>
          <p className="mt-2 text-slate-500">
            查看全部学习计划
          </p>
        </div>

        <button type="button" onClick={reload}>
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
        <p>暂无学习计划</p>
      ) : (
        <div className="grid gap-4 lg:grid-cols-3">
          {plans.map((plan) => (
            <PlanCard key={plan.id} plan={plan} />
          ))}
        </div>
      )}

      <Link href="/" className="text-blue-700">
        返回首页
      </Link>
    </section>
  );
}
