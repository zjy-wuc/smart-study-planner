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
  let accessToken = "expired";
  let refreshToken = "refresh";
  let refreshCalls = 0;
  let apiCalls = 0;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, init = {}) => {
    if (String(url).endsWith("/auth/refresh")) {
      refreshCalls += 1;
      await Promise.resolve();
      return Response.json({ data: { access_token: "fresh", refresh_token: "refresh-2" } });
    }
    apiCalls += 1;
    const authorization = new Headers(init.headers).get("Authorization");
    return authorization === "Bearer fresh"
      ? Response.json({ ok: true })
      : Response.json({ detail: { code: "ACCESS_EXPIRED" } }, { status: 401 });
  };

  try {
    const client = load("../lib/api/client.ts", {
      "@/messages": { messages: { common: { httpRequestFailed: (status) => String(status) } } },
      "@/lib/auth/token": {
        getAccessToken: () => accessToken,
        getRefreshToken: () => refreshToken,
        setTokenPair: (access, refresh) => { accessToken = access; refreshToken = refresh; },
        removeTokenPair: () => { accessToken = ""; refreshToken = ""; },
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
