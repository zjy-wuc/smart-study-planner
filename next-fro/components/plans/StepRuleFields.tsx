
"use client";

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
        >
          执行方式
        </label>

        <select
          id="rule-mode"
          value={mode}
          onChange={(event) =>
            onModeChange(event.target.value as RuleMode)
          }
          className="w-full rounded border p-2"
        >
          <option value="BOOLEAN_REPEAT">
            完成型 · 每天重复
          </option>

          <option value="BOOLEAN_DAILY_CUSTOM">
            完成型 · 每日自定义
          </option>

          <option value="NUMERIC_AUTO_DISTRIBUTE">
            数量型 · 自动分配
          </option>

          <option value="NUMERIC_DAILY_MANUAL">
            数量型 · 每日手动安排
          </option>
        </select>
      </div>

      {isBooleanRepeat && (
        <div>
          <label
            htmlFor="repeat-content"
            className="mb-1 block font-medium"
          >
            每天重复的内容
          </label>

          <input
            id="repeat-content"
            value={repeatContent}
            onChange={(event) =>
              onRepeatContentChange(event.target.value)
            }
            maxLength={255}
            placeholder="例如：阅读一篇英语文章"
            className="w-full rounded border p-2"
          />
        </div>
      )}

      {isNumeric && (
        <div>
          <label
            htmlFor="total-target"
            className="mb-1 block font-medium"
          >
            总目标数量
          </label>

          <input
            id="total-target"
            type="number"
            min="0"
            step="1"
            value={totalText}
            onChange={(event) =>
              onTotalTextChange(event.target.value)
            }
            placeholder="例如：100"
            className="w-full rounded border p-2"
          />

          <p className="mt-1 text-sm text-slate-500">
            {mode === "NUMERIC_AUTO_DISTRIBUTE"
              ? "开始计划后，系统会把数量分配到每天。"
              : "后续需要填写每一天的目标数量。"}
          </p>
        </div>
      )}

      {mode === "BOOLEAN_DAILY_CUSTOM" && (
        <p className="text-sm text-slate-500">
          创建叶子后，需要在逐日安排中填写每一天的任务内容。
        </p>
      )}
    </div>
  );
}
