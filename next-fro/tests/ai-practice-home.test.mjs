import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import ts from "typescript";

test("AI home module evaluates with its extracted copy and exposes four entries", () => {
  const copy = { title: "AI 学习助手", subtitle: "描述", organize: "整理", organizeDesc: "整理说明", qa: "问答", qaDesc: "问答说明", practice: "练习", practiceDesc: "练习说明", history: "历史", historyDesc: "历史说明", go: "进入" };
  const source = fs.readFileSync(new URL("../app/(workspace)/ai/page.tsx", import.meta.url), "utf8");
  const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } }).outputText;
  const module = { exports: {} };
  const dependencies = {
    "next/link": () => null,
    "@/messages/zh-CN/ai-practice": { aiPractice: copy },
    "@/components/css/AiPractice.css": {},
    "react/jsx-runtime": { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) },
  };
  new Function("require", "module", "exports", output)((name) => {
    if (!(name in dependencies)) throw new Error(`Unexpected import: ${name}`);
    return dependencies[name];
  }, module, module.exports);
  const tree = module.exports.default();
  assert.equal(tree.type, "main");
  assert.equal(tree.props.children[1].props.children.length, 4);
});
