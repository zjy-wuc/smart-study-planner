import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import ts from "typescript";

const compiled = { exports: {} };
const source = fs.readFileSync(new URL("../lib/statistics/plan-consistency.ts", import.meta.url), "utf8");
const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
new Function("exports", output)(compiled.exports);
const { buildPlanConsistency } = compiled.exports;
const summary = (dates) => ({ plans: [{ id: 1, name: "数学" }, { id: 2, name: "英语" }], steps: [], dates });
const record = (plan_id, step_id, checkin_date) => ({ plan_id, step_id, checkin_date });

test("plan days deduplicate multiple steps, keep plans separate, and ignore future records", () => {
  const result = buildPlanConsistency(summary([
    record(1, 1, "2026-11-28"), record(1, 2, "2026-11-28"),
    record(1, 1, "2026-11-27"), record(1, 1, "2026-11-29"),
    record(2, 3, "2026-11-26"),
  ]), "2026-11-28");
  assert.equal(result[0].totalDays, 2);
  assert.equal(result[0].streak, 2);
  assert.equal(result[0].checkedToday, true);
  assert.equal(result[1].totalDays, 1);
  assert.equal(result[1].streak, 0);
});

test("streak starts yesterday when today is empty, and breaks at a missed day", () => {
  const dates = [record(1, 1, "2026-11-27"), record(1, 1, "2026-11-26"), record(1, 1, "2026-11-24")];
  const [plan, emptyPlan] = buildPlanConsistency(summary(dates), "2026-11-28");
  assert.equal(plan.streak, 2);
  assert.equal(plan.checkedToday, false);
  assert.equal(plan.totalDays, 3);
  assert.equal(emptyPlan.streak, 0);
  assert.equal(emptyPlan.totalDays, 0);
  assert.equal(emptyPlan.week.length, 7);
  assert.ok(emptyPlan.week.every((day) => !day.checked));
});

test("the seven-day window crosses month and year boundaries without timezone drift", () => {
  const [plan] = buildPlanConsistency(summary([record(1, 1, "2025-12-31"), record(1, 2, "2026-01-01")]), "2026-01-01");
  assert.equal(plan.streak, 2);
  assert.deepEqual(plan.week.map((day) => day.date), ["2025-12-26", "2025-12-27", "2025-12-28", "2025-12-29", "2025-12-30", "2025-12-31", "2026-01-01"]);
  assert.deepEqual(plan.week.map((day) => day.checked), [false, false, false, false, false, true, true]);
  assert.deepEqual(buildPlanConsistency({ plans: [], dates: [], steps: [] }, "2026-01-01"), []);
});
