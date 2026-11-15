
"use client";

import Link from "next/link";
import { useMemo } from "react";

import { useDashboardData } from "@/hooks/useDashboardData";
import { useWorkspaceSearch } from "@/components/layout/WorkspaceShell";

import { PlanCard } from "@/components/dashboard/PlanCard";
import { TodayTaskList } from "@/components/dashboard/TodayTaskList";
import { StepPreview } from "@/components/dashboard/StepPreview";


export default function Dashboard() {
  const {
    plans,
    tasks,
    plansError,
    tasksError,
    loading,
    reload,
  } = useDashboardData();

  const { search } = useWorkspaceSearch();

  const filteredPlans = useMemo(() => {
    const keyword = search.trim().toLowerCase();

    if (!keyword) {
      return plans;
    }

    return plans.filter((plan) =>
      plan.name.toLowerCase().includes(keyword),
    );
  }, [plans, search]);

  // 首页只展示最多 3 个，完整列表在 /plans
  const featuredPlans = filteredPlans.slice(0, 3);

  return (
    <div className="workspace-dashboard">
      <div className="workspace-page-heading flex items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold">
            首页工作台
          </h1>

          <p className="mt-2 text-slate-600">
            学习计划与每日执行情况
          </p>
        </div>

        <button
          type="button"
          onClick={reload}
          className="workspace-button workspace-button--secondary rounded-lg border border-blue-600 px-4 py-2 text-blue-700"
        >
          刷新数据
        </button>
      </div>

      <section aria-labelledby="today-heading" className="workspace-panel workspace-dashboard-today">
        <div className="workspace-section-heading mb-4 flex items-center justify-between">
          <h2 id="today-heading" className="text-xl font-semibold">
            今日任务
          </h2>

          <Link href="/task/today" className="workspace-text-link text-blue-700">
            查看全部
          </Link>
        </div>

        {loading ? (
          <p>正在获取今日任务...</p>
        ) : tasksError ? (
          <p role="alert" className="text-red-600">
            今日任务加载失败：{tasksError}
          </p>
        ) : (
          <TodayTaskList tasks={tasks.slice(0, 5)} />
        )}
      </section>

      <div className="workspace-dashboard-grid">
        <section
          aria-labelledby="plans-heading"
          className="workspace-panel workspace-dashboard-plans"
        >
          <div className="workspace-section-heading mb-4 flex items-center justify-between">
            <h2
              id="plans-heading"
              className="text-xl font-semibold"
            >
              我的计划
            </h2>

            <Link
              href="/plans"
              className="workspace-text-link text-blue-700"
            >
              查看全部计划
            </Link>
          </div>

          {loading ? (
            <p>正在获取计划...</p>
          ) : plansError ? (
            <p role="alert" className="text-red-600">
              计划加载失败：{plansError}
            </p>
          ) : filteredPlans.length === 0 ? (
            <p className="workspace-empty-state rounded-xl border bg-white p-6 text-slate-500">
              {search.trim()
                ? "没有匹配的学习计划"
                : "还没有学习计划"}
            </p>
          ) : (
            <>
              <div className="workspace-plan-grid">
                {featuredPlans.map((plan) => (
                  <PlanCard key={plan.id} plan={plan} />
                ))}
              </div>

              {filteredPlans.length > 3 && (
                <p className="mt-3 text-sm text-slate-500">
                  匹配 {filteredPlans.length} 个计划，
                  首页显示前 3 个。
                </p>
              )}
            </>
          )}
        </section>

        <section
          aria-labelledby="steps-heading"
          className="workspace-panel rounded-xl border border-slate-200 bg-white p-5"
        >
          <h2
            id="steps-heading"
            className="text-xl font-semibold"
          >
            学习步骤预览
          </h2>

          {loading ? (
            <p className="mt-4">正在准备步骤预览...</p>
          ) : plansError ? (
            <p className="mt-4 text-red-600">
              当前无法加载计划步骤
            </p>
          ) : (
            <StepPreview plans={plans} />
          )}
        </section>
      </div>
    </div>
  );
}
