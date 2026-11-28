"use client";

import { messages } from "@/messages";

import Link from "next/link";
import Image from "next/image";

import { useDashboardData } from "@/hooks/useDashboardData";
import { isOpenTodayTask } from "@/lib/tasks/today-presentation";

import { PlanCard } from "@/components/dashboard/PlanCard";
import { TodayTaskList } from "@/components/dashboard/TodayTaskList";
import { StepPreview } from "@/components/dashboard/StepPreview";
import { WorkspaceIcon } from "@/components/ui/WorkspaceIcon";
import "@/components/css/DashboardRefresh.css";


export default function Dashboard() {
  const {
    plans,
    tasks,
    plansError,
    tasksError,
    loading,
    reload,
  } = useDashboardData();

  // 首页只展示最多 3 个，完整列表在 /plans
  const featuredPlans = plans.slice(0, 3);
  const pendingTasks = tasks.filter(isOpenTodayTask).length;
  const previewTasks = [...tasks].sort((left, right) =>
    Number(isOpenTodayTask(right)) - Number(isOpenTodayTask(left)),
  ).slice(0, 5);
  const activePlans = plans.filter((plan) => plan.status === "ACTIVE").length;

  return (
    <div className="workspace-dashboard dashboard-refresh">
      <div className="workspace-page-heading">
        <div>
          <h1 className="text-3xl font-bold">{messages.dashboard.greeting}</h1>

          <p className="mt-2 text-slate-600">{messages.dashboard.welcomeDescription}</p>
        </div>
        <Image className="dashboard-welcome-art" src="/illustrations/workspace-books.svg" alt="" width={190} height={125} />
        <button
          type="button"
          onClick={reload}
          className="workspace-button workspace-button--secondary"
        >
          <WorkspaceIcon name="refresh" />{messages.common.refreshData}</button>
      </div>

      <section aria-labelledby="today-heading" className="workspace-panel workspace-dashboard-today">
        <div className="workspace-section-heading">
          <div className="workspace-section-title">
            <span className="workspace-section-icon"><WorkspaceIcon name="tasks" /></span>
            <div>
              <h2 id="today-heading">{messages.navigation.today}{" "}{!loading && !tasksError && <span className="dashboard-count">{messages.dashboard.pendingCount(pendingTasks)}</span>}</h2>
              <p>{messages.dashboard.todaySubtitle}</p>
            </div>
          </div>

          <Link href="/task/today" className="workspace-text-link text-blue-700">{messages.common.viewAll}<WorkspaceIcon name="arrow" />
          </Link>
        </div>

        {loading ? (
          <p role="status" className="workspace-loading">{messages.tasks.loadingToday}</p>
        ) : tasksError ? (
          <p role="alert" className="workspace-feedback workspace-feedback--error">{messages.dashboard.tasksError(tasksError)}
          </p>
        ) : (
          <TodayTaskList tasks={previewTasks} plans={plans} onChanged={reload} />
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
              <h2 id="plans-heading">{messages.navigation.plans}{" "}{!loading && !plansError && <span className="dashboard-count">{messages.dashboard.activeCount(activePlans)}</span>}</h2>
                <p>{messages.dashboard.plansSubtitle}</p>
              </div>
            </div>

            <div className="dashboard-plan-links">
            <Link href="/plans/new" className="workspace-text-link">{messages.plans.create}</Link>
            <Link
              href="/plans"
              className="workspace-text-link text-blue-700"
            >{messages.plans.viewAll}<WorkspaceIcon name="arrow" />
            </Link>
            </div>
          </div>

          {loading ? (
            <p role="status" className="workspace-loading">{messages.dashboard.loadingPlans}</p>
          ) : plansError ? (
            <p role="alert" className="workspace-feedback workspace-feedback--error">{messages.dashboard.plansError(plansError)}
            </p>
          ) : plans.length === 0 ? (
            <p className="workspace-empty-state">
              {messages.dashboard.noPlans}
            </p>
          ) : (
            <div className="workspace-plan-grid">
              {featuredPlans.map((plan) => (
                <PlanCard key={plan.id} plan={plan} />
              ))}
            </div>
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
                <h2 id="steps-heading">{messages.dashboard.stepsTitle}</h2>
                <p>{messages.dashboard.stepsSubtitle}</p>
              </div>
            </div>
          </div>

          {loading ? (
            <p role="status" className="workspace-loading">{messages.dashboard.loadingSteps}</p>
          ) : plansError ? (
            <p className="workspace-feedback workspace-feedback--error">{messages.dashboard.stepsUnavailable}</p>
          ) : (
            <StepPreview plans={plans} />
          )}
        </section>
      </div>
    </div>
  );
}
