import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import ts from "typescript";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import Markdown from "react-markdown";

// 加载真实 TypeScript 实现，仅替换 API 传输层；不把此测试当作数据库联调。
function load(file, dependencies = {}) {
  const output = ts.transpileModule(fs.readFileSync(new URL(file, import.meta.url), "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  const module = { exports: {} };
  new Function("require", "module", "exports", output)((name) => {
    if (!(name in dependencies)) throw new Error(`Unexpected import: ${name}`);
    return dependencies[name];
  }, module, module.exports);
  return module.exports;
}
const { knowledge } = load("../messages/zh-CN/knowledge.ts");
const rules = load("../lib/knowledge.ts", { "@/messages": { messages: { knowledge } } });

test("tags trim, deduplicate, and enforce limits", () => {
  assert.deepEqual(rules.parseKnowledgeTags("React, react， SQL "), ["React", "SQL"]);
  assert.deepEqual(rules.parseKnowledgeTags(""), []);
  assert.throws(() => rules.parseKnowledgeTags("x".repeat(51)));
  assert.throws(() => rules.parseKnowledgeTags(Array.from({ length: 21 }, (_, i) => `tag${i}`).join(",")));
});

test("only leaves are selectable with parent paths", () => {
  assert.deepEqual(rules.knowledgeLeaves([{ id: 1, name: "Group", node_type: "GROUP", children: [
    { id: 2, name: "Leaf", node_type: "LEAF", children: [] },
  ] }]), [{ id: 2, name: "Group / Leaf" }]);
});

test("PATCH preserves omitted association and emits explicit null when detached", () => {
  const before = { title: "Title", content_md: "# Original", tags: [], plan_id: 1, step_id: 2 };
  assert.deepEqual(rules.knowledgeChanges(before, { ...before, content_md: "# Changed" }), { content_md: "# Changed" });
  assert.deepEqual(rules.knowledgeChanges(before, { ...before, plan_id: null, step_id: null }), { plan_id: null, step_id: null });
  assert.deepEqual(rules.knowledgeChanges(before, { ...before, plan_id: 3, step_id: null }), { plan_id: 3, step_id: null });
  assert.deepEqual(rules.knowledgeChanges(before, before), {});
});

test("all nine note endpoints use expected methods and preserve Markdown", async () => {
  const calls = [];
  const api = load("../services/knowledge.service.ts", {
    "@/lib/api/client": { apiFetch: async (path, options = {}) => { calls.push({ path, ...options }); return { data: { id: 8 } }; } },
  });
  const payload = { title: "Title", content_md: "# Hi\n\n```js\nconst a = 1;\n```", tags: [], plan_id: null, step_id: null };
  await api.createNote(payload);
  await api.listNotes({ page: 2, page_size: 12, keyword: "a & b", tag: "SQL", plan_id: 3 });
  await api.listNotes({ page: 1, page_size: 12, keyword: "ignored", tag: "ignored", plan_id: 3 }, true);
  await api.getNote(8);
  await api.updateNote(8, { step_id: null });
  await api.deleteNote(8);
  await api.restoreNote(8);
  await api.addReview(8);
  await api.getReviews(8);
  assert.equal(calls.length, 9);
  assert.equal(calls[0].method, "POST");
  assert.deepEqual(JSON.parse(calls[0].body), payload);
  assert.equal(calls[1].path, "/notes?page=2&page_size=12&keyword=a+%26+b&tag=SQL&plan_id=3");
  assert.equal(calls[2].path, "/notes/trash?page=1&page_size=12");
  assert.equal(calls[3].path, "/notes/8");
  assert.equal(calls[4].method, "PATCH");
  assert.deepEqual(JSON.parse(calls[4].body), { step_id: null });
  assert.equal(calls[5].method, "DELETE");
  assert.deepEqual(calls.slice(6).map(({ path, method }) => [path, method ?? "GET"]), [
    ["/notes/8/restore", "POST"], ["/notes/8/reviews", "POST"], ["/notes/8/reviews", "GET"],
  ]);
});

test("Markdown renders common syntax and blocks raw HTML and script URLs", () => {
  const html = renderToStaticMarkup(React.createElement(Markdown, { skipHtml: true },
    '# Title\n\n- item\n\n> quote\n\n```js\nconst x = 1;\n```\n\n[bad](javascript:alert%281%29)\n\n<script>alert(1)</script>\n\n<img src=x onerror=alert(1)>'));
  assert.match(html, /<h1>Title<\/h1>/);
  assert.match(html, /<li>item<\/li>/);
  assert.match(html, /<blockquote>/);
  assert.match(html, /<pre><code/);
  assert.doesNotMatch(html, /<script|onerror|javascript:/);
});
