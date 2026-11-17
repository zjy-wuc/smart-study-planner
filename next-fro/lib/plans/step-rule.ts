import { messages } from "@/messages";

import type { StepRule } from "@/types/step";

export type RuleMode =
  | "BOOLEAN_REPEAT"
  | "BOOLEAN_DAILY_CUSTOM"
  | "NUMERIC_AUTO_DISTRIBUTE"
  | "NUMERIC_DAILY_MANUAL";

export function buildStepRule(
  mode: RuleMode,
  repeatContent: string,
  totalText: string,
): StepRule {
  if (mode === "BOOLEAN_REPEAT") {
    const content = repeatContent.trim();

    if (!content) {
      throw new Error(messages.validation.repeatContentRequired);
    }

    return {
      task_type: "BOOLEAN",
      schedule_mode: "REPEAT",
      repeat_content: content,
    };
  }

  if (mode === "BOOLEAN_DAILY_CUSTOM") {
    return {
      task_type: "BOOLEAN",
      schedule_mode: "DAILY_CUSTOM",
    };
  }

  // NUMERIC 只接受非负安全整数。
  // 避免 JavaScript number 出现精度丢失。
  if (!/^\d+$/.test(totalText.trim())) {
    throw new Error(messages.validation.totalIntegerRequired);
  }

  const total = Number(totalText.trim());

  if (!Number.isSafeInteger(total)) {
    throw new Error(messages.validation.totalTooLarge);
  }

  return {
    task_type: "NUMERIC",
    schedule_mode:
      mode === "NUMERIC_AUTO_DISTRIBUTE"
        ? "AUTO_DISTRIBUTE"
        : "DAILY_MANUAL",
    total_target: total,
  };
}
