"use client";

import { messages } from "@/messages";

import { useState } from "react";

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

  const [ending, setEnding] = useState(false);
  const [error, setError] = useState<string | null>(null);


  async function handleEnd() {
    if (plan.status !== "ACTIVE" || ending) {
      return;
    }

    const confirmed = window.confirm(
      messages.plans.endConfirm(plan.name),
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
        err.status === 409
      ) {
        setError(
          messages.plans.stateChangedRefresh(err.message),
        );
        return;
      }

      setError(
        err instanceof Error
          ? err.message
          : messages.plans.endFailed,
      );

    } finally {
      setEnding(false);
    }
  }


  if (plan.status !== "ACTIVE") {
    return null;
  }

  return (
    <section className="plan-lifecycle-panel">
      <div>
        <h2 className="text-xl font-semibold">{messages.plans.endTitle}</h2>

        <p className="mt-2 text-sm text-slate-600">{messages.plans.endDescription}</p>
      </div>

      <p className="text-sm text-slate-600">{messages.plans.expirationDescription}</p>

      {error && (
        <p role="alert" className="text-sm text-red-700">
          {error}
        </p>
      )}

      <button
        type="button"
        disabled={ending}
        onClick={() => void handleEnd()}
        className="plan-detail-delete-button"
      >
        {ending ? messages.plans.ending : messages.plans.endEarly}
      </button>
    </section>
  );
}
