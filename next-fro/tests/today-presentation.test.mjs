import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import ts from "typescript";

const source = fs.readFileSync(new URL("../lib/tasks/today-presentation.ts", import.meta.url), "utf8");
const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
const module = { exports: {} };
new Function("require", "module", "exports", output)(() => { throw new Error("Unexpected runtime import"); }, module, module.exports);
const { isOpenTodayTask, isSettledNumericTask } = module.exports;

test("today pending count excludes completed, rolled over and inactive tasks", () => {
  const task = { plan_status: "ACTIVE", status: "IN_PROGRESS", is_rolled_over: false, has_rollover: 0, rollover_out_quantity: 0 };
  assert.equal(isOpenTodayTask(task), true);
  for (const change of [{ status: "COMPLETED" }, { status: "ENDED" }, { plan_status: "ENDED" }, { is_rolled_over: true }, { has_rollover: 1 }, { rollover_out_quantity: 40 }]) {
    assert.equal(isOpenTodayTask({ ...task, ...change }), false);
  }
});

test("read-only plan preview does not mistake numeric rollover settlement for actual completion", () => {
  const task = { task_type: "NUMERIC", status: "COMPLETED", target_quantity: 100, actual_quantity: 60 };
  assert.equal(isSettledNumericTask(task), true);
  assert.equal(isSettledNumericTask({ ...task, actual_quantity: 100 }), false);
  assert.equal(isSettledNumericTask({ ...task, task_type: "BOOLEAN" }), false);
});
