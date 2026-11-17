"use client";

import { messages } from "@/messages";

import { useState, type FormEvent } from "react";

import { ApiError } from "@/lib/api/client";

import type {
  Plan,
  PlanCreate,
} from "@/types/plan";


type PlanFormProps = {
  initialPlan?: Plan;
  onSubmit: (data: PlanCreate) => Promise<void>;
  submitLabel?: string;
  datesLocked?: boolean;
};


export function PlanForm({
  initialPlan,
  onSubmit,
  submitLabel = messages.plans.save,
  datesLocked = false,
}: PlanFormProps) {

  const [name, setName] = useState(
    initialPlan?.name ?? "",
  );

  const [description, setDescription] = useState(
    initialPlan?.description ?? "",
  );

  const [startDate, setStartDate] = useState(
    initialPlan?.start_date ?? "",
  );

  const [endDate, setEndDate] = useState(
    initialPlan?.end_date ?? "",
  );

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [fieldErrors, setFieldErrors] = useState<
    Record<string, string>
  >({});


  async function handleSubmit(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();

    if (submitting) {
      return;
    }

    setError(null);
    setFieldErrors({});

    const cleanedName = name.trim();

    // 前端先给用户提供友好的校验反馈
    if (!cleanedName) {
      setFieldErrors({
        name: messages.plans.nameRequired,
      });
      return;
    }

    if (!startDate || !endDate) {
      setError(messages.plans.datesRequired);
      return;
    }

    if (startDate > endDate) {
      setFieldErrors({
        end_date: messages.plans.invalidDateOrder,
      });
      return;
    }

    const data: PlanCreate = {
      name: cleanedName,
      description: description.trim() || null,
      start_date: startDate,
      end_date: endDate,
    };

    try {
      setSubmitting(true);

      await onSubmit(data);

    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);

        if (err.status === 422) {
          const errors: Record<string, string> = {};

          for (const issue of err.validationIssues) {
            const field = String(
              issue.loc.at(-1) ?? "",
            );

            if (!errors[field]) {
              errors[field] = issue.msg;
            }
          }

          setFieldErrors(errors);
        }

      } else {
        setError(
          err instanceof Error
            ? err.message
            : messages.common.operationFailedLater,
        );
      }

    } finally {
      setSubmitting(false);
    }
  }


  return (
    <form
      onSubmit={handleSubmit}
      className="space-y-5 rounded-xl border border-slate-200 bg-white p-6"
    >
      <div>
        <label
          htmlFor="plan-name"
          className="mb-2 block font-medium"
        >{messages.plans.name}</label>

        <input
          id="plan-name"
          type="text"
          required
          value={name}
          onChange={(event) => setName(event.target.value)}
          maxLength={100}
          className="w-full rounded-lg border border-slate-300 px-3 py-2"
          placeholder={messages.plans.namePlaceholder}
        />

        {fieldErrors.name && (
          <p className="mt-1 text-sm text-red-600">
            {fieldErrors.name}
          </p>
        )}
      </div>

      <div>
        <label
          htmlFor="plan-description"
          className="mb-2 block font-medium"
        >{messages.plans.description}</label>

        <textarea
          id="plan-description"
          value={description}
          onChange={(event) =>
            setDescription(event.target.value)
          }
          rows={3}
          maxLength={255}
          className="w-full rounded-lg border border-slate-300 px-3 py-2"
          placeholder={messages.plans.descriptionPlaceholder}
        />
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label
            htmlFor="plan-start-date"
            className="mb-2 block font-medium"
          >{messages.plans.startDate}</label>

          <input
            id="plan-start-date"
            type="date"
            required
            disabled={datesLocked}
            value={startDate}
            onChange={(event) =>
              setStartDate(event.target.value)
            }
            className="w-full rounded-lg border border-slate-300 px-3 py-2 disabled:bg-slate-100"
          />
        </div>

        <div>
          <label
            htmlFor="plan-end-date"
            className="mb-2 block font-medium"
          >{messages.plans.endDate}</label>

          <input
            id="plan-end-date"
            type="date"
            required
            disabled={datesLocked}
            value={endDate}
            onChange={(event) =>
              setEndDate(event.target.value)
            }
            className="w-full rounded-lg border border-slate-300 px-3 py-2 disabled:bg-slate-100"
          />

          {fieldErrors.end_date && (
            <p className="mt-1 text-sm text-red-600">
              {fieldErrors.end_date}
            </p>
          )}
        </div>
      </div>

      {datesLocked && (
        <p className="text-sm text-slate-500">{messages.plans.datesLocked}</p>
      )}

      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={submitting}
        className="rounded-lg bg-blue-600 px-5 py-3 font-medium text-white disabled:opacity-50"
      >
        {submitting ? messages.common.saving : submitLabel}
      </button>
    </form>
  );
}
