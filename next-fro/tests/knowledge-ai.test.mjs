import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import ts from "typescript";

function load(file, dependencies = {}) {
  const output = ts.transpileModule(fs.readFileSync(new URL(file, import.meta.url), "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const cjsModule = { exports: {} };
  new Function("require", "module", "exports", output)((name) => {
    if (!(name in dependencies)) throw new Error(`Unexpected import: ${name}`);
    return dependencies[name];
  }, cjsModule, cjsModule.exports);
  return cjsModule.exports;
}

function chunkedStream(chunks) {
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(chunk);
      controller.close();
    },
  });
}

test("SSE parser handles UTF-8 splits, CRLF, multiline data, and arbitrary chunks", async () => {
  const { readSseEvents } = load("../lib/api/sse.ts");
  const bytes = new TextEncoder().encode(
    'event: delta\r\ndata: {"text":"学习"}\r\n\r\nevent: done\ndata: {"status":\n' +
    'data: "success"}\n\n',
  );
  const events = [];
  for await (const event of readSseEvents(chunkedStream([
    bytes.slice(0, 24), bytes.slice(24, 27), bytes.slice(27, 55), bytes.slice(55),
  ]))) events.push(event);
  assert.deepEqual(events, [
    { event: "delta", data: { text: "学习" } },
    { event: "done", data: { status: "success" } },
  ]);
});

test("authenticated requests share one refresh and retry each request once", async () => {
  const accessToken = "expired";
  let refreshCalls = 0;
  let apiCalls = 0;
  let sharedRefresh;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, init = {}) => {
    apiCalls += 1;
    const authorization = new Headers(init.headers).get("Authorization");
    return authorization === "Bearer fresh"
      ? Response.json({ ok: true })
      : Response.json({ detail: { code: "ACCESS_EXPIRED" } }, { status: 401 });
  };

  try {
    const client = load("../lib/api/client.ts", {
      axios: { default: { create: () => ({ interceptors: { request: { use() {} }, response: { use() {} } }, post: async () => {
        refreshCalls += 1;
        await Promise.resolve();
        return { data: { data: { access_token: "fresh" } } };
      } }) } },
      "@/messages": { messages: { common: { httpRequestFailed: (status) => String(status) } } },
      "@/lib/auth/coordinator": {
        authEpoch: () => null,
        sameAuthEpoch: () => true,
        refreshAccessToken: (_token, request) => {
          if (!sharedRefresh) sharedRefresh = request().finally(() => { sharedRefresh = null; });
          return sharedRefresh;
        },
      },
      "@/lib/auth/token": {
        getAccessToken: () => accessToken,
        getAuthGeneration: () => 0,
      },
    });
    const responses = await Promise.all([client.authenticatedFetch("/a"), client.authenticatedFetch("/b")]);
    assert.equal(refreshCalls, 1);
    assert.equal(apiCalls, 4);
    assert.deepEqual(await Promise.all(responses.map((response) => response.json())), [{ ok: true }, { ok: true }]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("AI stream rejects EOF without a terminal event", async () => {
  const sse = load("../lib/api/sse.ts");
  const service = load("../services/knowledge-ai.service.ts", {
    "@/lib/api/client": {
      ApiError: class ApiError extends Error {},
      assertSseSession: () => {},
      authenticatedFetch: async () => new Response('event: delta\ndata: {"text":"partial"}\n\n', {
        headers: { "Content-Type": "text/event-stream" },
      }),
    },
    "@/lib/api/sse": sse,
  });
  await assert.rejects(
    service.streamKnowledgeAi({ operation: "generate", topic: "测试" }, () => {}, new AbortController().signal),
    /提前结束/,
  );
});

test("AI stream cancellation aborts the active read", async () => {
  const sse = load("../lib/api/sse.ts");
  const service = load("../services/knowledge-ai.service.ts", {
    "@/lib/api/client": {
      ApiError: class ApiError extends Error {},
      assertSseSession: () => {},
      authenticatedFetch: async (_path, options) => new Response(new ReadableStream({
        start(controller) {
          controller.enqueue(new TextEncoder().encode('event: start\ndata: {}\n\n'));
          options.signal.addEventListener("abort", () => controller.error(new DOMException("Aborted", "AbortError")), { once: true });
        },
      })),
    },
    "@/lib/api/sse": sse,
  });
  const controller = new AbortController();
  const pending = service.streamKnowledgeAi({ operation: "generate", topic: "测试" }, () => {}, controller.signal);
  controller.abort();
  await assert.rejects(pending, { name: "AbortError" });
});

test("knowledge QA sends the note route and only its explicit history payload", async () => {
  const sse = load("../lib/api/sse.ts");
  let call;
  const service = load("../services/knowledge-ai.service.ts", {
    "@/lib/api/client": {
      ApiError: class ApiError extends Error {},
      assertSseSession: () => {},
      authenticatedFetch: async (path, options) => {
        call = { path, options };
        return new Response('event: done\ndata: {"status":"success","mode":"ask","markdown":"回答"}\n\n');
      },
    },
    "@/lib/api/sse": sse,
  });
  const history = [{ question: "上一问", answer: "上一答" }];
  const terminal = await service.streamKnowledgeAi(
    { operation: "ask", noteId: 7, question: "为什么？", history },
    () => {},
    new AbortController().signal,
  );
  assert.equal(call.path, "/notes/7/ai/ask");
  assert.deepEqual(JSON.parse(call.options.body), { question: "为什么？", history });
  assert.equal(terminal.event, "done");
});

test("knowledge QA history keeps only the latest three successes in the current context", () => {
  const { recentSuccessfulQaHistory } = load("../lib/knowledge-qa.ts");
  const make = (id, status, contextId = 2) => ({
    id, contextId, status, question: `q${id}`, answer: `a${id}`, historySnapshot: [],
  });
  const selected = recentSuccessfulQaHistory([
    make(1, "success", 1), make(2, "success"), make(3, "error"),
    make(4, "success"), make(5, "cancelled"), make(6, "success"), make(7, "success"),
  ], 2);
  assert.deepEqual(selected, [
    { question: "q4", answer: "a4" },
    { question: "q6", answer: "a6" },
    { question: "q7", answer: "a7" },
  ]);
});

test("knowledge QA counts Unicode code points without native maxlength truncation", () => {
  const { unicodeLength } = load("../lib/knowledge-qa.ts");
  assert.equal(unicodeLength("中文😀"), 3);
  assert.equal(unicodeLength("😀".repeat(1000)), 1000);
  assert.equal(unicodeLength("😀".repeat(1001)), 1001);
});

test("AI HTTP errors support FastAPI 422 detail arrays and existing detail forms", () => {
  const service = load("../services/knowledge-ai.service.ts", {
    "@/lib/api/client": { ApiError: class ApiError extends Error {} },
    "@/lib/api/sse": { readSseEvents: async function* () {} },
  });
  assert.equal(service.aiResponseErrorMessage({ detail: [
    { loc: ["body", "question"], msg: "问题不能为空", type: "string_too_short" },
    { loc: ["body", "history"], msg: "历史格式无效", type: "list_type" },
  ] }, 422), "问题不能为空；历史格式无效");
  assert.equal(service.aiResponseErrorMessage({ detail: "输入可能包含敏感凭据" }, 422), "输入可能包含敏感凭据");
  assert.equal(service.aiResponseErrorMessage({ detail: { message: "请求过于频繁", stack: "internal" } }, 429), "请求过于频繁");
  assert.equal(service.aiResponseErrorMessage({ detail: [{ stack: "internal" }] }, 422), "AI 请求失败（422）");
});

test("knowledge QA recognizes both NOTE_CHANGED and STALE as invalid context", () => {
  const { isKnowledgeQaStale } = load("../lib/knowledge-qa.ts");
  assert.equal(isKnowledgeQaStale({ event: "error", data: { code: "NOTE_CHANGED" } }), true);
  assert.equal(isKnowledgeQaStale({ event: "error", data: { status: "STALE" } }), true);
  assert.equal(isKnowledgeQaStale({ event: "error", data: { code: "AI_INTERNAL_ERROR" } }), false);
  assert.equal(isKnowledgeQaStale({ event: "blocked", data: { status: "STALE" } }), false);
});
