"use client";

import { messages } from "@/messages";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { PlanForm } from "@/components/plans/PlanForm";
import { createPlan } from "@/services/plans.service";

import type { PlanCreate } from "@/types/plan";


export default function CreatePlanPage() {
  const router = useRouter();
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (!dirty) return;

    function handleBeforeUnload(event: BeforeUnloadEvent) {
      event.preventDefault();
    }

    function handleLinkClick(event: MouseEvent) {
      const target = event.target;
      if (!(target instanceof Element)) return;
      const anchor = target.closest("a");
      if (!anchor || anchor.target || anchor.hasAttribute("download")) return;

      const destination = new URL(anchor.href, window.location.href);
      if (destination.origin !== window.location.origin) return;
      if (`${destination.pathname}${destination.search}${destination.hash}` === `${window.location.pathname}${window.location.search}${window.location.hash}`) return;

      event.preventDefault();
      event.stopPropagation();
      if (!window.confirm(messages.plans.unsavedConfirm)) return;

      setDirty(false);
      router.push(`${destination.pathname}${destination.search}${destination.hash}`);
    }

    function handleHistoryNavigation() {
      if (window.confirm(messages.plans.unsavedConfirm)) {
        setDirty(false);
        return;
      }
      window.history.go(1);
    }

    window.addEventListener("beforeunload", handleBeforeUnload);
    window.addEventListener("popstate", handleHistoryNavigation);
    document.addEventListener("click", handleLinkClick, true);
    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload);
      window.removeEventListener("popstate", handleHistoryNavigation);
      document.removeEventListener("click", handleLinkClick, true);
    };
  }, [dirty, router]);

  async function handleCreate(data: PlanCreate) {
    const created = await createPlan(data);

    setDirty(false);
    window.sessionStorage.setItem("new-plan-id", String(created.id));
    router.push(`/plans/${created.id}#plan-steps`);
  }

  return (
    <div className="plan-create-page">
      <header className="plan-create-header">
        <Link href="/plans" className="plan-create-back">{messages.plans.backToMyPlans}</Link>
        <h1>{messages.plans.createTitle}</h1>
        <p>{messages.plans.createDescription}</p>
      </header>

      <ol className="plan-create-progress" aria-label={messages.plans.createTitle}>
        {[messages.plans.workflowBasic, messages.plans.workflowSteps, messages.plans.workflowConfirm].map((label, index) => (
          <li key={label} aria-current={index === 0 ? "step" : undefined}>
            <span>{index + 1}</span>
            <div><strong>{label}</strong>{index === 0 && <small>{messages.plans.currentWorkflowStep}</small>}</div>
          </li>
        ))}
      </ol>

      <PlanForm
        onSubmit={handleCreate}
        submitLabel={messages.plans.createAndContinue}
        cancelHref="/plans"
        onDirtyChange={setDirty}
      />
    </div>
  );
}
