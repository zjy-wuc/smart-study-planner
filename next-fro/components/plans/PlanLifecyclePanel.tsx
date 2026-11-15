
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { ApiError } from "@/lib/api/client";
import { endPlan } from "@/services/plans.service";

import type {
  Plan,
  EndPlanResult,
} from "@/types/plan";


type Props = {
  plan: Plan;
  onEnded: (result: EndPlanResult) => void;
};


export function PlanLifecyclePanel({
  plan,
  onEnded,
}: Props) {
  const router = useRouter();

  const [ending, setEnding] = useState(false);
  const [error, setError] = useState<string | null>(null);


  async function handleEnd() {
    if (plan.status !== "ACTIVE" || ending) {
      return;
    }

    const confirmed = window.confirm(
      `确定提前结束「${plan.name}」吗？\n\n` +
      "已完成的任务和历史记录将保留。\n" +
      "已开始但未完成的任务会停止执行，" +
      "尚未开始的任务可能被逻辑删除。\n\n" +
      "结束后不能继续打卡、顺延或修改此计划。",
    );

    if (!confirmed) {
      return;
    }

    setEnding(true);
    setError(null);

    try {
      const result = await endPlan(plan.id);

      // 只有后端明确返回成功，才通知父组件
      onEnded(result);

    } catch (err) {
      if (
        err instanceof ApiError &&
        err.status === 401
      ) {
        router.replace("/login");
        return;
      }

      if (
        err instanceof ApiError &&
        err.status === 409
      ) {
        setError(
          `计划状态可能已经改变：${err.message}。` +
          "请刷新页面后查看最新状态。",
        );
        return;
      }

      setError(
        err instanceof Error
          ? err.message
          : "结束计划失败，请稍后重试",
      );

    } finally {
      setEnding(false);
    }
  }


  if (plan.status !== "ACTIVE") {
    return null;
  }

  return (
    <section className="space-y-4 rounded-xl border border-amber-200 bg-white p-6">
      <div>
        <h2 className="text-xl font-semibold">
          结束学习计划
        </h2>

        <p className="mt-2 text-sm text-slate-600">
          当前计划处于执行状态。
          结束计划后，不能继续执行原有每日任务。
        </p>
      </div>

      <p className="text-sm text-slate-600">
        如果计划已经超过结束日期，
        后端会按正常到期规则处理。
        具体结束方式以接口返回结果为准。
      </p>

      {error && (
        <p role="alert" className="text-sm text-red-700">
          {error}
        </p>
      )}

      <button
        type="button"
        disabled={ending}
        onClick={() => void handleEnd()}
        className="rounded-lg border border-red-500 px-5 py-3 text-red-700 disabled:opacity-50"
      >
        {ending ? "正在结束计划..." : "提前结束计划"}
      </button>
    </section>
  );
}
