"use client";

import { useSyncExternalStore } from "react";
import Link from "next/link";
import { messages } from "@/messages";

import "@/components/css/PlanWorkflow.css";

type Step = "basic" | "steps" | "confirm";

type Props =
  | { view: "create"; planId?: never }
  | { view: "basic" | "confirm" | "steps"; planId: number; onLeave?: () => boolean };

function subscribe(listener: () => void) {
  window.addEventListener("hashchange", listener);
  window.addEventListener("popstate", listener);
  return () => {
    window.removeEventListener("hashchange", listener);
    window.removeEventListener("popstate", listener);
  };
}

function getHash() {
  return window.location.hash;
}

function getServerHash() {
  return "";
}

export function useDraftPlanView() {
  const hash = useSyncExternalStore(subscribe, getHash, getServerHash);
  return hash === "#plan-actions" || hash === "#plan-schedule" ? "confirm" : "basic";
}

export function PlanWorkflowNav(props: Props) {
  const { view, planId } = props;
  const current: Step = view === "create" ? "basic" : view;
  const detail = view === "basic" || view === "confirm" ? "" : `/plans/${planId}`;
  const items = [
    { step: "basic", label: messages.plans.workflowBasic, href: `${detail}#plan-basic` },
    { step: "steps", label: messages.plans.workflowSteps, href: view === "steps" ? "#plan-steps" : `/plans/${planId}/steps` },
    { step: "confirm", label: messages.plans.workflowConfirm, href: `${detail}#plan-actions` },
  ] as const;

  return (
    <nav className="plan-workflow-nav" data-view={view} aria-label={messages.plans.createTitle}>
      <ol className="plan-step-workflow">
        {items.map(({ step, label, href }) => {
          const active = step === current;
          return (
            <li key={step} data-state={step === "basic" && !active ? "done" : undefined}>
              {view === "create" || active ? (
                <span aria-current={active ? "step" : undefined} aria-disabled={active ? undefined : true}>
                  {label}
                </span>
              ) : href.startsWith("#") ? (
                <a href={href} aria-current={active ? "step" : undefined}>{label}</a>
              ) : (
                <Link href={href} onNavigate={(event) => {
                  if ("onLeave" in props && props.onLeave?.() === false) event.preventDefault();
                }}>{label}</Link>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
