"use client";

import { messages } from "@/messages";

import type { RuleMode } from "@/lib/plans/step-rule";

type Props = {
  mode: RuleMode;
  onModeChange: (value: RuleMode) => void;

  repeatContent: string;
  onRepeatContentChange: (value: string) => void;

  totalText: string;
  onTotalTextChange: (value: string) => void;
};

export function StepRuleFields({
  mode,
  onModeChange,
  repeatContent,
  onRepeatContentChange,
  totalText,
  onTotalTextChange,
}: Props) {
  const isBooleanRepeat = mode === "BOOLEAN_REPEAT";
  const isNumeric = mode.startsWith("NUMERIC_");

  return (
    <div className="space-y-4">
      <div>
        <label
          htmlFor="rule-mode"
          className="mb-1 block font-medium"
        >{messages.steps.executionMode}</label>

        <select
          id="rule-mode"
          value={mode}
          onChange={(event) =>
            onModeChange(event.target.value as RuleMode)
          }
          className="w-full rounded border p-2"
        >
          <option value="BOOLEAN_REPEAT">{messages.steps.booleanRepeat}</option>

          <option value="BOOLEAN_DAILY_CUSTOM">{messages.steps.booleanCustom}</option>

          <option value="NUMERIC_AUTO_DISTRIBUTE">{messages.steps.numericAuto}</option>

          <option value="NUMERIC_DAILY_MANUAL">{messages.steps.numericManual}</option>
        </select>
      </div>

      {isBooleanRepeat && (
        <div>
          <label
            htmlFor="repeat-content"
            className="mb-1 block font-medium"
          >{messages.steps.repeatContent}</label>

          <input
            id="repeat-content"
            value={repeatContent}
            onChange={(event) =>
              onRepeatContentChange(event.target.value)
            }
            maxLength={255}
            placeholder={messages.steps.contentPlaceholder}
            className="w-full rounded border p-2"
          />
        </div>
      )}

      {isNumeric && (
        <div>
          <label
            htmlFor="total-target"
            className="mb-1 block font-medium"
          >{messages.steps.totalTarget}</label>

          <input
            id="total-target"
            type="number"
            min="0"
            step="1"
            value={totalText}
            onChange={(event) =>
              onTotalTextChange(event.target.value)
            }
            placeholder={messages.steps.targetPlaceholder}
            className="w-full rounded border p-2"
          />

          <p className="mt-1 text-sm text-slate-500">
            {mode === "NUMERIC_AUTO_DISTRIBUTE"
              ? messages.steps.autoAllocationHint
              : messages.steps.manualAllocationHint}
          </p>
        </div>
      )}

      {mode === "BOOLEAN_DAILY_CUSTOM" && (
        <p className="text-sm text-slate-500">{messages.steps.customContentHint}</p>
      )}
    </div>
  );
}
