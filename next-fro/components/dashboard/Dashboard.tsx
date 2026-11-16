
"use client";

import Link from "next/link";
import { useMemo } from "react";

import { useDashboardData } from "@/hooks/useDashboardData";
import { useWorkspaceSearch } from "@/components/layout/WorkspaceShell";

import { PlanCard } from "@/components/dashboard/PlanCard";
import { TodayTaskList } from "@/components/dashboard/TodayTaskList";
import { StepPreview } from "@/components/dashboard/StepPreview";
import { WorkspaceIcon } from "@/components/ui/WorkspaceIcon";


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
      <div className="workspace-page-heading">
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
          className="workspace-button workspace-button--secondary"
        >
          <WorkspaceIcon name="refresh" />
          刷新数据
        </button>
      </div>

      <section aria-labelledby="today-heading" className="workspace-panel workspace-dashboard-today">
        <div className="workspace-section-heading">
          <div className="workspace-section-title">
            <span className="workspace-section-icon"><WorkspaceIcon name="tasks" /></span>
            <div>
              <h2 id="today-heading">今日任务</h2>
              <p>从今天的安排开始</p>
            </div>
          </div>

          <Link href="/task/today" className="workspace-text-link text-blue-700">
            查看全部
            <WorkspaceIcon name="arrow" />
          </Link>
        </div>

        {loading ? (
          <p role="status" className="workspace-loading">正在获取今日任务...</p>
        ) : tasksError ? (
          <p role="alert" className="workspace-feedback workspace-feedback--error">
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
          <div className="workspace-section-heading">
            <div className="workspace-section-title">
              <span className="workspace-section-icon"><WorkspaceIcon name="calendar" /></span>
              <div>
                <h2 id="plans-heading">我的计划</h2>
                <p>查看计划与完成进度</p>
              </div>
            </div>

            <Link
              href="/plans"
              className="workspace-text-link text-blue-700"
            >
              查看全部计划
              <WorkspaceIcon name="arrow" />
            </Link>
          </div>

          {loading ? (
            <p role="status" className="workspace-loading">正在获取计划...</p>
          ) : plansError ? (
            <p role="alert" className="workspace-feedback workspace-feedback--error">
              计划加载失败：{plansError}
            </p>
          ) : filteredPlans.length === 0 ? (
            <p className="workspace-empty-state">
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
                <p className="workspace-summary-note">
                  匹配 {filteredPlans.length} 个计划，
                  首页显示前 3 个。
                </p>
              )}
            </>
          )}
        </section>

        <section
          aria-labelledby="steps-heading"
          className="workspace-panel workspace-dashboard-steps"
        >
          <div className="workspace-section-heading">
            <div className="workspace-section-title">
              <span className="workspace-section-icon"><WorkspaceIcon name="steps" /></span>
              <div>
                <h2 id="steps-heading">学习步骤预览</h2>
                <p>按计划查看步骤层级</p>
              </div>
            </div>
          </div>

          {loading ? (
            <p role="status" className="workspace-loading">正在准备步骤预览...</p>
          ) : plansError ? (
            <p className="workspace-feedback workspace-feedback--error">
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
