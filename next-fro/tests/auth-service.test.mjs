import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import ts from "typescript";

function authService(reply, coordination = {}) {
  const source = fs.readFileSync(new URL("../services/auth.service.ts", import.meta.url), "utf8");
  const code = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const module = { exports: {} };
  const requests = [];
  const events = [];
  new Function("require", "module", "exports", code)((name) => ({
    "@/lib/api/client": { apiFetch: async (path, options) => {
      requests.push({ path, options });
      return reply(path, options);
    } },
    "@/lib/auth/coordinator": {
      withAuthLock: coordination.withAuthLock ?? ((work) => work()),
      authEpoch: coordination.authEpoch ?? (() => "login:mock"),
      sameAuthEpoch: coordination.sameAuthEpoch ?? (() => true),
      announceAuthChange: (type) => { events.push(type); return "login:mock"; },
    },
    "@/lib/auth/token": {
      setAccessToken: (token, epoch) => events.push(`access:${token}@${epoch}`),
      clearAccessToken: () => events.push("clear"),
      getAuthGeneration: () => 0,
    },
  })[name], module, module.exports);
  return { service: module.exports, requests, events };
}

const loginResponse = {
  code: 200,
  data: { access_token: "test-access", user: { id: 1, username: "student" } },
};

test("registration consumes its login response without another login request", async () => {
  const { service, requests, events } = authService(() => loginResponse);
  const result = await service.registerUser({ username: "student", email: "student@example.test", code: "123456", password: "placeholder" });
  assert.deepEqual(requests.map((request) => request.path), ["/users"]);
  assert.deepEqual(events, ["login", "access:test-access@login:mock"]);
  assert.equal(result.authEpoch, "login:mock");
});

function exclusiveLock() {
  let occupied = false;
  const waiting = [];
  return async function withAuthLock(work) {
    return new Promise((resolve, reject) => {
      const run = async () => {
        occupied = true;
        try { resolve(await work()); }
        catch (error) { reject(error); }
        finally { occupied = false; waiting.shift()?.(); }
      };
      if (occupied) waiting.push(run);
      else void run();
    });
  };
}

test("expired Access during logout-all does not recursively wait for its own exclusive lock", async () => {
  const withAuthLock = exclusiveLock();
  let expired = true;
  let refreshes = 0;
  const { service, requests, events } = authService(async (path, options) => {
    if (path === "/users/me") {
      if (expired) await withAuthLock(async () => { expired = false; refreshes += 1; });
      return { data: { id: 1, email: "student@example.test" } };
    }
    if (expired && !options.skipAuthRefresh)
      await withAuthLock(async () => { expired = false; refreshes += 1; });
    return { data: { revoked_count: 1 } };
  }, { withAuthLock });
  await Promise.race([
    service.logoutAllSessions("placeholder"),
    new Promise((_, reject) => setTimeout(() => reject(new Error("nested lock timed out")), 100)),
  ]);
  assert.equal(refreshes, 1);
  assert.equal(requests.at(-1).options.skipAuthRefresh, true);
  assert.deepEqual(events, ["clear", "logout"]);
});

test("queued logout operations cannot run after another account has logged in", async () => {
  for (const operation of ["logoutUser", "logoutAllSessions"]) {
    const withAuthLock = exclusiveLock();
    let release;
    let epoch = "login:account-one";
    const blocker = withAuthLock(() => new Promise((resolve) => { release = resolve; }));
    const { service, requests, events } = authService(async (path) =>
      path === "/users/me" ? { data: { id: 1 } } : { data: { session_revoked: true, revoked_count: 1 } },
    { withAuthLock, authEpoch: () => epoch, sameAuthEpoch: (expected) => epoch === expected });
    const pending = operation === "logoutUser" ? service.logoutUser() : service.logoutAllSessions("placeholder");
    epoch = "login:account-two";
    release();
    await blocker;
    await assert.rejects(pending, /登录状态已变化/);
    assert.equal(requests.filter(({ path }) => path.startsWith("/auth/logout")).length, 0);
    assert.deepEqual(events, []);
  }
});

test("password login uses form data and email code login uses JSON", async () => {
  const { service, requests } = authService(() => loginResponse);
  await service.loginUser({ username: "student", password: "placeholder" });
  await service.loginWithEmail({ email: "student@example.test", code: "123456" });
  assert.equal(requests[0].path, "/auth/login");
  assert.equal(requests[0].options.body.get("username"), "student");
  assert.equal(requests[0].options.headers["Content-Type"], "application/x-www-form-urlencoded");
  assert.equal(requests[1].path, "/auth/login/email");
  assert.deepEqual(JSON.parse(requests[1].options.body), { email: "student@example.test", code: "123456" });
});

test("current-device logout clears local auth only after server confirms revocation", async () => {
  const rejected = authService(() => ({ code: 200, data: { session_revoked: false } }));
  await rejected.service.logoutUser();
  assert.deepEqual(rejected.events, []);

  const confirmed = authService(() => ({ code: 200, data: { session_revoked: true } }));
  await confirmed.service.logoutUser();
  assert.deepEqual(confirmed.events, ["clear", "logout"]);
  assert.equal(confirmed.requests.find(({ path }) => path === "/auth/logout").options.skipAuthRefresh, true);
});

test("wrong password on logout-all preserves the current session", async () => {
  const { service, events } = authService(async (path) => {
    if (path === "/users/me") return { data: { id: 1 } };
    throw Object.assign(new Error("密码错误"), { status: 401, code: "INVALID_PASSWORD" });
  });
  await assert.rejects(service.logoutAllSessions("wrong"), /密码错误/);
  assert.deepEqual(events, []);
});
