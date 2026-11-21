"use client";

import { messages } from "@/messages";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { ApiError } from "@/lib/api/client";
import { getBusinessToday } from "@/lib/plans/business-date";

import "@/components/css/PlanForm.css";

import type {
  Plan,
  PlanCreate,
} from "@/types/plan";


type PlanFormProps = {
  initialPlan?: Plan;
  onSubmit: (data: PlanCreate) => Promise<void>;
  submitLabel?: string;
  datesLocked?: boolean;
  cancelHref?: string;
  onDirtyChange?: (dirty: boolean) => void;
};

function addDays(dateValue: string, days: number): string {
  const [year, month, day] = dateValue.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day + days));
  return date.toISOString().slice(0, 10);
}

function countInclusiveDays(startDate: string, endDate: string): number | null {
  if (!startDate || !endDate || startDate > endDate) return null;
  const start = Date.parse(`${startDate}T00:00:00Z`);
  const end = Date.parse(`${endDate}T00:00:00Z`);
  return Math.floor((end - start) / 86_400_000) + 1;
}


export function PlanForm({
  initialPlan,
  onSubmit,
  submitLabel = messages.plans.save,
  datesLocked = false,
  cancelHref,
  onDirtyChange,
}: PlanFormProps) {

  const [name, setName] = useState(
    initialPlan?.name ?? "",
  );

  const [description, setDescription] = useState(
    initialPlan?.description ?? "",
  );

  const [startDate, setStartDate] = useState(
    initialPlan?.start_date ?? getBusinessToday(),
  );

  const [endDate, setEndDate] = useState(
    initialPlan?.end_date ?? "",
  );

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [fieldErrors, setFieldErrors] = useState<
    Record<string, string>
  >({});
  const durationDays = countInclusiveDays(startDate, endDate);

  function markDirty() {
    onDirtyChange?.(true);
  }

  function clearFieldError(field: string) {
    setFieldErrors((current) => {
      if (!current[field]) return current;
      const next = { ...current };
      delete next[field];
      return next;
    });
  }

  function choosePeriod(days: number) {
    const start = startDate || getBusinessToday();
    setStartDate(start);
    setEndDate(addDays(start, days - 1));
    clearFieldError("start_date");
    clearFieldError("end_date");
    markDirty();
  }


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
    const validationErrors: Record<string, string> = {};
    if (!cleanedName) validationErrors.name = messages.plans.nameRequired;
    if (!startDate) validationErrors.start_date = messages.plans.startDateRequired;
    if (!endDate) validationErrors.end_date = messages.plans.endDateRequired;
    if (startDate && endDate && startDate > endDate) validationErrors.end_date = messages.plans.invalidDateOrder;

    if (Object.keys(validationErrors).length > 0) {
      setFieldErrors(validationErrors);
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
      onDirtyChange?.(false);

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
      className="plan-form"
      noValidate
    >
      {error && <div role="alert" className="plan-form-error">{error}</div>}

      <p className="plan-form-draft-note">{messages.plans.draftExplanation}</p>

      <fieldset disabled={submitting}>
      <div className="plan-form-field">
        <div className="plan-form-label-row"><label htmlFor="plan-name">{messages.plans.name}</label><span>{messages.plans.nameCount(name.length)}</span></div>

        <input
          id="plan-name"
          type="text"
          required
          value={name}
          onChange={(event) => { setName(event.target.value); clearFieldError("name"); markDirty(); }}
          onBlur={() => { if (!name.trim()) setFieldErrors((current) => ({ ...current, name: messages.plans.nameRequired })); }}
          maxLength={100}
          className="plan-form-control"
          placeholder={messages.plans.namePlaceholder}
          autoFocus={!initialPlan}
          aria-invalid={fieldErrors.name ? "true" : undefined}
          aria-describedby={fieldErrors.name ? "plan-name-error" : undefined}
        />

        {fieldErrors.name && (
          <p id="plan-name-error" className="plan-form-field-error">
            {fieldErrors.name}
          </p>
        )}
      </div>

      <div className="plan-form-field">
        <div className="plan-form-label-row"><label htmlFor="plan-description">{messages.plans.description}</label><span>{messages.plans.descriptionCount(description.length)}</span></div>

        <textarea
          id="plan-description"
          value={description}
          onChange={(event) => { setDescription(event.target.value); markDirty(); }}
          rows={4}
          maxLength={2000}
          className="plan-form-control plan-form-textarea"
          placeholder={messages.plans.descriptionPlaceholder}
        />
      </div>

      <section className="plan-form-period" aria-labelledby="plan-period-title">
        <div className="plan-form-period-heading"><div><h2 id="plan-period-title">{messages.plans.choosePeriod}</h2><p>{messages.plans.dateInclusiveHint}</p></div>{!datesLocked && <button type="button" onClick={() => { const today = getBusinessToday(); setStartDate(today); if (endDate && endDate < today) setEndDate(today); clearFieldError("start_date"); markDirty(); }}>{messages.plans.startToday}</button>}</div>

        {!datesLocked && <div className="plan-form-presets" aria-label={messages.plans.choosePeriod}>{[7, 30, 90].map((days) => <button key={days} type="button" onClick={() => choosePeriod(days)}>{messages.plans.periodDays(days)}</button>)}</div>}

        <div className="plan-form-date-grid">
        <div className="plan-form-field">
          <label htmlFor="plan-start-date">{messages.plans.startDate}</label>

          <input
            id="plan-start-date"
            type="date"
            required
            disabled={datesLocked}
            value={startDate}
            onChange={(event) => { const value = event.target.value; setStartDate(value); if (endDate && value > endDate) setEndDate(value); clearFieldError("start_date"); clearFieldError("end_date"); markDirty(); }}
            className="plan-form-control"
            aria-invalid={fieldErrors.start_date ? "true" : undefined}
            aria-describedby={fieldErrors.start_date ? "plan-start-error" : undefined}
          />
          {fieldErrors.start_date && <p id="plan-start-error" className="plan-form-field-error">{fieldErrors.start_date}</p>}
        </div>

        <div className="plan-form-field">
          <label htmlFor="plan-end-date">{messages.plans.endDate}</label>

          <input
            id="plan-end-date"
            type="date"
            required
            disabled={datesLocked}
            value={endDate}
            min={startDate || undefined}
            onChange={(event) => { const value = event.target.value; setEndDate(value); clearFieldError("end_date"); markDirty(); }}
            className="plan-form-control"
            aria-invalid={fieldErrors.end_date ? "true" : undefined}
            aria-describedby={fieldErrors.end_date ? "plan-end-error" : undefined}
          />

          {fieldErrors.end_date && (
            <p id="plan-end-error" className="plan-form-field-error">
              {fieldErrors.end_date}
            </p>
          )}
        </div>
        </div>

        <p className={`plan-form-duration${durationDays ? " is-ready" : ""}`} aria-live="polite">{durationDays ? messages.plans.durationSummary(startDate, endDate, durationDays) : messages.plans.durationPending}</p>
      </section>

      {datesLocked && (
        <p className="plan-form-locked-note">{messages.plans.datesLocked}</p>
      )}
      </fieldset>

      <footer className="plan-form-actions">
        {cancelHref && (submitting ? <span className="plan-form-cancel is-disabled" aria-disabled="true">{messages.plans.cancelCreate}</span> : <Link href={cancelHref} className="plan-form-cancel">{messages.plans.cancelCreate}</Link>)}
        <button type="submit" disabled={submitting} className="plan-form-submit">{submitting ? messages.plans.savingDraft : submitLabel}<ArrowRight size={16} aria-hidden="true" /></button>
      </footer>
    </form>
  );
}
