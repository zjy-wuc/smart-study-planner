import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import ts from "typescript";

const question = { id: "q1", type: "SINGLE_CHOICE", stem: "?", options: { A: "a", B: "b" } };
const short = { id: "q2", type: "SHORT_ANSWER", stem: "Explain" };
const paper = { status: "success", note_id: 1, note_title: "笔记", question_count: 2, questions: [question, short], practice_ticket: "opaque", expires_in_seconds: 3600 };
const record = { id: 1, score: 50, question_count: 2, questions: [] };

function harness(api) {
  const values = [];
  const refs = [];
  let index = 0;
  let refIndex = 0;
  const react = {
    useState(initial) {
      const at = index++;
      if (!(at in values)) values[at] = initial;
      return [values[at], (value) => { values[at] = typeof value === "function" ? value(values[at]) : value; }];
    },
    useRef(initial) { const at = refIndex++; if (!(at in refs)) refs[at] = { current: initial }; return refs[at]; },
    useCallback(value) { return value; },
    useEffect() {},
  };
  const source = fs.readFileSync(new URL("../hooks/useAiPractice.ts", import.meta.url), "utf8");
  const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  const module = { exports: {} };
  const dependencies = {
    react,
    "@/services/ai-practice.service": api,
    "@/messages/zh-CN/ai-practice": { aiPractice: { generating: "生成中", reviewing: "校验中", grading: "批改中", failed: "失败", blocked: "拦截", expired: "过期", answerTooLong: "太长", gradeFailed: "批改失败" } },
  };
  new Function("require", "module", "exports", output)((name) => dependencies[name], module, module.exports);
  return () => { index = 0; refIndex = 0; return module.exports.useAiPractice(); };
}

test("preview has no answers, submitting locks the original answers and retry uses locked ticket", async () => {
  const submissions = [];
  let attempt = 0;
  const render = harness({
    generatePractice: async () => ({ event: "done", data: paper }),
    submitPractice: async (body, _signal, onEvent) => {
      submissions.push(body);
      if (++attempt === 1) { onEvent({ event: "start", data: { submission_ticket: "locked" } }); return { event: "error", data: { message: "AI unavailable" } }; }
      return { event: "done", data: { status: "success", record, already_saved: false } };
    },
  });
  await render().generate(1, 5);
  assert.equal(render().phase, "preview");
  assert.deepEqual(render().answers, {});
  render().begin();
  render().answer(question, "A");
  await render().grade();
  assert.equal(render().phase, "grading_failed");
  render().answer(question, "B");
  assert.equal(render().answers.q1, "A");
  await render().grade();
  assert.equal(render().phase, "completed");
  assert.deepEqual(submissions, [
    { practice_ticket: "opaque", answers: [{ id: "q1", answer: "A" }, { id: "q2", answer: null }] },
    { submission_ticket: "locked" },
  ]);
});

test("failure before start retries identical answers; direct done is accepted", async () => {
  const submissions = [];
  const render = harness({
    generatePractice: async () => ({ event: "done", data: paper }),
    submitPractice: async (body) => {
      submissions.push(body);
      return submissions.length === 1 ? { event: "blocked", data: { message: "额度不足" } } : { event: "done", data: { status: "success", record, already_saved: true } };
    },
  });
  await render().generate(1, 5);
  render().begin();
  render().answer(short, "first");
  await render().grade();
  assert.equal(render().error, "额度不足");
  await render().grade();
  assert.deepEqual(submissions[0], submissions[1]);
  assert.equal(render().result.score, 50);
});

test("cancel generation ignores a late success, preserving configuration state", async () => {
  let finish;
  const render = harness({
    generatePractice: () => new Promise((resolve) => { finish = resolve; }),
    submitPractice: async () => { throw new Error("not called"); },
  });
  const pending = render().generate(1, 10);
  assert.equal(render().phase, "generating");
  render().cancelGeneration();
  finish({ event: "done", data: paper });
  await pending;
  assert.equal(render().phase, "configuring");
  assert.equal(render().paper, null);
});

test("expired paper refuses grading without calling the API", async () => {
  let submits = 0;
  const render = harness({
    generatePractice: async () => ({ event: "done", data: { ...paper, expires_in_seconds: 0 } }),
    submitPractice: async () => { submits += 1; },
  });
  await render().generate(1, 5);
  render().begin();
  await render().grade();
  assert.equal(submits, 0);
  assert.equal(render().error, "过期");
});
