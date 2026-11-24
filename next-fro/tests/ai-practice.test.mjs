import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import ts from "typescript";

function loadService(fetcher, apiFetcher = async () => ({ data: {} })) {
  const source = fs.readFileSync(new URL("../services/ai-practice.service.ts", import.meta.url), "utf8");
  const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  const parserSource = fs.readFileSync(new URL("../lib/api/sse.ts", import.meta.url), "utf8");
  const parserOutput = ts.transpileModule(parserSource, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  const parser = { exports: {} };
  new Function("require", "module", "exports", parserOutput)(() => ({}), parser, parser.exports);
  const service = { exports: {} };
  const dependencies = {
    "@/lib/api/client": { ApiError: class ApiError extends Error { constructor(message, status) { super(message); this.status = status; } }, authenticatedFetch: fetcher, apiFetch: apiFetcher },
    "@/lib/api/sse": parser.exports,
    "@/services/knowledge-ai.service": { aiResponseErrorMessage: (body, status) => body?.detail || `请求失败 ${status}` },
  };
  new Function("require", "module", "exports", output)((name) => dependencies[name], service, service.exports);
  return service.exports;
}

function stream(events) {
  return new Response(new ReadableStream({ start(controller) {
    for (const [name, data] of events) controller.enqueue(new TextEncoder().encode(`event: ${name}\ndata: ${JSON.stringify(data)}\n\n`));
    controller.close();
  } }), { headers: { "Content-Type": "text/event-stream" } });
}

test("generation sends only note and count, then parses reviewed public questions", async () => {
  let request;
  const service = loadService(async (path, options) => {
    request = { path, body: JSON.parse(options.body), signal: options.signal };
    return stream([["start", {}], ["reviewing", {}], ["done", { status: "success", questions: [{ id: "q1", type: "SINGLE_CHOICE", stem: "?", options: { A: "a" } }], practice_ticket: "opaque" }]]);
  });
  const controller = new AbortController();
  const seen = [];
  const terminal = await service.generatePractice(12, 5, controller.signal, (event) => seen.push(event.event));
  assert.deepEqual(request, { path: "/ai/practices/generate", body: { note_id: 12, question_count: 5 }, signal: controller.signal });
  assert.deepEqual(seen, ["start", "reviewing", "done"]);
  assert.equal(terminal.data.practice_ticket, "opaque");
});

test("grading accepts done without start and retry sends only submission ticket", async () => {
  const requests = [];
  const service = loadService(async (path, options) => {
    requests.push({ path, body: JSON.parse(options.body) });
    return stream([["done", { status: "success", record: { score: 80, questions: [] }, already_saved: true }]]);
  });
  const event = await service.submitPractice({ submission_ticket: "opaque-locked" }, new AbortController().signal, () => {});
  assert.equal(event.event, "done");
  assert.equal(event.data.already_saved, true);
  assert.deepEqual(requests[0], { path: "/ai/practices/submit", body: { submission_ticket: "opaque-locked" } });
});

test("SSE blocked remains terminal and HTTP validation retains backend detail", async () => {
  const blocked = loadService(async () => stream([["blocked", { message: "额度不足" }]]));
  assert.equal((await blocked.generatePractice(1, 5, new AbortController().signal, () => {})).data.message, "额度不足");
  const invalid = loadService(async () => Response.json({ detail: "笔记不存在" }, { status: 404 }));
  await assert.rejects(invalid.generatePractice(1, 5, new AbortController().signal, () => {}), /笔记不存在/);
});

test("history uses pagination and note filter, detail and delete paths", async () => {
  const paths = [];
  const service = loadService(async () => { throw new Error("unexpected stream"); }, async (path, options) => {
    paths.push([path, options?.method]);
    return { data: { items: [], total: 0, page: 2, page_size: 10 } };
  });
  assert.equal((await service.listPractices(2, 12)).page, 2);
  await service.getPractice(18);
  await service.deletePractice(18);
  assert.deepEqual(paths, [["/ai/practices?page=2&page_size=10&note_id=12", undefined], ["/ai/practices/18", undefined], ["/ai/practices/18", "DELETE"]]);
});
