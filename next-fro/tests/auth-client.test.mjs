import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import ts from "typescript";
import axios from "axios";

function clientFor(adapter, refreshAdapter, race = {}) {
  const source = fs.readFileSync(new URL("../lib/api/client.ts", import.meta.url), "utf8");
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  const module = { exports: {} };
  let cleared = 0;
  let access = "access";
  const token = { getAccessToken: () => access, getAuthGeneration: () => 0, clearAccessToken: () => { access = null; cleared += 1; } };
  let refreshes = 0;
  const axiosModule = {
    default: {
      ...axios,
      create(config) {
        const instance = axios.create(config);
        instance.defaults.adapter = refreshes++ === 0 ? refreshAdapter ?? adapter : adapter;
        return instance;
      },
    },
    AxiosHeaders: axios.AxiosHeaders,
  };
  new Function("require", "module", "exports", code)((name) => ({
    axios: axiosModule,
    "@/messages": { messages: { common: { httpRequestFailed: (status) => `HTTP ${status}` } } },
    "@/lib/auth/coordinator": {
      authEpoch: () => race.epoch?.current ?? null,
      sameAuthEpoch: (expected) => (race.epoch?.current ?? null) === expected,
      refreshAccessToken: race.refreshAccessToken ?? (async (_used, refresh) => { access = await refresh(); return access; }),
    },
    "@/lib/auth/token": token,
  })[name], module, module.exports);
  module.exports.httpClient.defaults.adapter = adapter;
  return { client: module.exports, cleared: () => cleared, access: () => access, setAccess: (value) => { access = value; } };
}

function rejected(config, status, detail) {
  const response = { status, data: { detail }, config, headers: {} };
  return new axios.AxiosError("request failed", "ERR_BAD_REQUEST", config, null, response);
}

test("Axios adds bearer, CSRF and activity headers to a learning action", async () => {
  let sent;
  const { client } = clientFor(async (config) => {
    sent = config;
    return { status: 200, data: { code: 200, data: { id: 7 } }, config, headers: {} };
  });
  const result = await client.apiFetch("/plans", { method: "POST", body: JSON.stringify({ name: "数学" }) });
  assert.equal(result.data.id, 7);
  assert.equal(sent.headers.get("Authorization"), "Bearer access");
  assert.equal(sent.headers.get("X-CSRF-Protection"), "1");
  assert.equal(sent.headers.get("X-User-Activity"), "1");
  assert.match(sent.headers.get("Content-Type"), /application\/json/);
});

test("validation and password errors preserve the session", async () => {
  const { client, cleared } = clientFor(async (config) => {
    const status = config.url === "/auth/login" ? 401 : 422;
    const body = status === 401 ? { detail: { code: "INVALID_CREDENTIALS", message: "密码错误" } }
      : { detail: [{ loc: ["body", "name"], msg: "请输入名称", type: "missing" }] };
    const response = { status, data: body, config, headers: {} };
    throw new axios.AxiosError("request failed", "ERR_BAD_REQUEST", config, null, response);
  });
  await assert.rejects(client.apiFetch("/auth/login", { method: "POST", skipAuthRefresh: true }), (error) => error.code === "INVALID_CREDENTIALS" && error.message === "密码错误");
  await assert.rejects(client.apiFetch("/plans", { method: "POST" }), (error) => error.status === 422 && error.validationIssues[0].msg === "请输入名称");
  assert.equal(cleared(), 0);
});

test("an expired access token refreshes once and retries with the new token", async () => {
  let refreshCalls = 0;
  let businessCalls = 0;
  const { client, cleared } = clientFor(async (config) => {
    businessCalls += 1;
    if (businessCalls === 1) throw rejected(config, 401, { code: "ACCESS_EXPIRED", message: "expired" });
    assert.equal(config.headers.get("Authorization"), "Bearer fresh");
    return { status: 200, data: { code: 200, data: { id: 9 } }, config, headers: {} };
  }, async (config) => {
    refreshCalls += 1;
    assert.equal(config.url, "/auth/refresh");
    assert.equal(config.headers.get("X-CSRF-Protection"), "1");
    return { status: 200, data: { data: { access_token: "fresh" } }, config, headers: {} };
  });
  assert.equal((await client.apiFetch("/plans")).data.id, 9);
  assert.equal(refreshCalls, 1);
  assert.equal(businessCalls, 2);
  assert.equal(cleared(), 0);
});

test("refresh rejection does not recurse and clears only confirmed invalid sessions", async () => {
  let refreshCalls = 0;
  const { client, cleared } = clientFor(async (config) => {
    throw rejected(config, 401, { code: "ACCESS_EXPIRED", message: "expired" });
  }, async (config) => {
    refreshCalls += 1;
    throw rejected(config, 401, { code: "REFRESH_INVALID", message: "session invalid" });
  });
  await assert.rejects(client.apiFetch("/plans"), (error) => error.code === "REFRESH_INVALID");
  assert.equal(refreshCalls, 1);
  assert.equal(cleared(), 1);
});

test("network failures leave the current session intact", async () => {
  const { client, cleared } = clientFor(async (config) => {
    throw new axios.AxiosError("network down", "ERR_NETWORK", config);
  });
  await assert.rejects(client.apiFetch("/plans"), (error) => error.status === 0);
  assert.equal(cleared(), 0);
});

test("a disabled account is cleared on the backend's HTTP 403 code", async () => {
  const { client, cleared } = clientFor(async (config) => {
    throw rejected(config, 403, { code: "ACCOUNT_DISABLED", message: "disabled" });
  });
  await assert.rejects(client.apiFetch("/plans"), (error) => error.code === "ACCOUNT_DISABLED");
  assert.equal(cleared(), 1);
});

test("a failed refresh from the old account cannot clear a newer login", async () => {
  const race = { epoch: { current: "account-one" } };
  let rejectRefresh;
  let refreshStarted;
  const started = new Promise((resolve) => { refreshStarted = resolve; });
  race.refreshAccessToken = () => {
    refreshStarted();
    return new Promise((_resolve, reject) => { rejectRefresh = reject; });
  };
  const { client, cleared, access, setAccess } = clientFor(async (config) => {
    throw rejected(config, 401, { code: "ACCESS_EXPIRED", message: "expired" });
  }, undefined, race);
  const pending = client.apiFetch("/plans", { method: "POST", body: "{}" });
  await started;
  race.epoch.current = "account-two";
  setAccess("new-account-access");
  rejectRefresh(new client.ApiError("old session revoked", 401, [], "REFRESH_INVALID"));
  await assert.rejects(pending, (error) => error.code === "REFRESH_INVALID");
  assert.equal(cleared(), 0);
  assert.equal(access(), "new-account-access");
});

test("a stream cannot deliver old-account chunks after an account switch", async () => {
  const race = { epoch: { current: "account-one" } };
  const { client, setAccess } = clientFor(async () => { throw new Error("Unexpected Axios request"); }, undefined, race);
  const originalFetch = globalThis.fetch;
  let streamController;
  globalThis.fetch = async () => new Response(new ReadableStream({
    start(controller) { streamController = controller; },
  }), { status: 200, headers: { "Content-Type": "text/event-stream" } });
  try {
    const response = await client.authenticatedFetch("/notes/1/ai/ask", { method: "POST", body: "{}" });
    const reader = response.body.getReader();
    streamController.enqueue(new TextEncoder().encode("event: start\n\n"));
    assert.equal((await reader.read()).done, false);
    race.epoch.current = "account-two";
    setAccess("new-account-access");
    streamController.enqueue(new TextEncoder().encode("event: delta\ndata: old\n\n"));
    await assert.rejects(reader.read(), /登录状态已变化/);
    await reader.cancel().catch(() => {});
  } finally { globalThis.fetch = originalFetch; }
});

test("decoded buffered SSE events are rejected before reaching the new account UI", async () => {
  const race = { epoch: { current: "account-one" } };
  const { client } = clientFor(async () => { throw new Error("Unexpected Axios request"); }, undefined, race);
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response("event: done\ndata: {}\n\n", {
    headers: { "Content-Type": "text/event-stream" },
  });
  try {
    const response = await client.authenticatedFetch("/notes/1/ai/ask", { method: "POST", body: "{}" });
    race.epoch.current = "account-two";
    assert.throws(() => client.assertSseSession(response), (error) => error.code === "SESSION_MISMATCH");
  } finally { globalThis.fetch = originalFetch; }
});

test("an old business mutation is rejected before Axios reaches the adapter", async () => {
  const race = { epoch: { current: "account-one" } };
  let sent = 0;
  const { client, setAccess } = clientFor(async (config) => {
    sent += 1;
    return { status: 200, data: { code: 200, data: null }, config, headers: {} };
  }, undefined, race);
  const pending = client.apiFetch("/plans", { method: "POST", body: "{}" });
  race.epoch.current = "account-two";
  setAccess("account-two-token");
  await assert.rejects(pending, (error) => error.code === "SESSION_MISMATCH");
  assert.equal(sent, 0);
});

test("an expired old-account request is never retried with the new account token", async () => {
  const race = { epoch: { current: "account-one" } };
  let releaseRefresh;
  let startedRefresh;
  const started = new Promise((resolve) => { startedRefresh = resolve; });
  race.refreshAccessToken = () => {
    startedRefresh();
    return new Promise((resolve) => { releaseRefresh = resolve; });
  };
  let businessCalls = 0;
  const { client, setAccess } = clientFor(async (config) => {
    businessCalls += 1;
    throw rejected(config, 401, { code: "ACCESS_EXPIRED", message: "expired" });
  }, undefined, race);
  const pending = client.apiFetch("/plans", { method: "POST", body: "{}" });
  await started;
  race.epoch.current = "account-two";
  setAccess("account-two-access");
  releaseRefresh("account-two-access");
  await assert.rejects(pending, (error) => error.code === "SESSION_MISMATCH");
  assert.equal(businessCalls, 1);
});

test("a request without a current token does not retain a supplied stale Authorization header", async () => {
  let sent;
  const { client, setAccess } = clientFor(async (config) => {
    sent = config;
    return { status: 200, data: {}, config, headers: {} };
  });
  setAccess(null);
  await client.apiFetch("/plans", { headers: { Authorization: "Bearer old" } });
  assert.equal(sent.headers.has("Authorization"), false);
});

test("SSE error parsing cannot refresh after the account epoch changes", async () => {
  const race = { epoch: { current: "account-one" } };
  let refreshes = 0;
  race.refreshAccessToken = async () => { refreshes += 1; return "fresh"; };
  const { client } = clientFor(async () => { throw new Error("Unexpected Axios request"); }, undefined, race);
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => {
    const response = Response.json({ detail: { code: "ACCESS_EXPIRED" } }, { status: 401 });
    const originalClone = response.clone.bind(response);
    response.clone = () => {
      const copy = originalClone();
      const originalJson = copy.json.bind(copy);
      copy.json = async () => { const body = await originalJson(); race.epoch.current = "account-two"; return body; };
      return copy;
    };
    return response;
  };
  try {
    await assert.rejects(client.authenticatedFetch("/notes/1/ai/ask"), (error) => error.code === "SESSION_MISMATCH");
    assert.equal(refreshes, 0);
  } finally { globalThis.fetch = originalFetch; }
});
