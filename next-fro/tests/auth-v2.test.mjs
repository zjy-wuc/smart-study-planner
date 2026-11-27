import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import ts from "typescript";

function load(file, dependencies = {}) {
  const source = fs.readFileSync(new URL(file, import.meta.url), "utf8");
  const code = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  const module = { exports: {} };
  new Function("require", "module", "exports", code)(
    (name) => {
      if (!(name in dependencies))
        throw new Error(`Unexpected import: ${name}`);
      return dependencies[name];
    },
    module,
    module.exports,
  );
  return module.exports;
}

function browser() {
  const values = new Map();
  const storage = {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  };
  const previous = {
    window: globalThis.window,
    navigator: globalThis.navigator,
    localStorage: globalThis.localStorage,
  };
  globalThis.window = { BroadcastChannel: undefined };
  globalThis.localStorage = storage;
  let queue = Promise.resolve();
  Object.defineProperty(globalThis, "navigator", {
    configurable: true,
    value: {
      locks: {
        request(_name, _options, work) {
          const next = queue.then(work);
          queue = next.catch(() => {});
          return next;
        },
      },
    },
  });
  return {
    storage,
    restore() {
      globalThis.window = previous.window;
      globalThis.localStorage = previous.localStorage;
      Object.defineProperty(globalThis, "navigator", {
        configurable: true,
        value: previous.navigator,
      });
    },
  };
}

test("Access Token stays in memory and legacy keys are removed", () => {
  const env = browser();
  try {
    const token = load("../lib/auth/token.ts");
    env.storage.setItem("access_token", "old");
    env.storage.setItem("refresh_token", "old");
    token.setAccessToken("new");
    assert.equal(token.getAccessToken(), "new");
    assert.equal(env.storage.getItem("access_token"), "old");
    token.clearLegacyTokens();
    assert.equal(env.storage.getItem("access_token"), null);
    assert.equal(env.storage.getItem("refresh_token"), null);
    token.clearAccessToken();
    assert.equal(token.getAccessToken(), null);
  } finally {
    env.restore();
  }
});

test("five expired requests share one refresh and reject a stale login generation", async () => {
  const env = browser();
  try {
    const token = load("../lib/auth/token.ts");
    token.setAccessToken("expired");
    const coordinator = load("../lib/auth/coordinator.ts", {
      "./token": token,
    });
    let calls = 0;
    const refresh = async () => {
      calls += 1;
      await Promise.resolve();
      return "fresh";
    };
    const results = await Promise.all(
      Array.from({ length: 5 }, () =>
        coordinator.refreshAccessToken("expired", refresh),
      ),
    );
    assert.deepEqual(results, Array(5).fill("fresh"));
    assert.equal(calls, 1);
    const pending = coordinator.refreshAccessToken("fresh", async () => {
      token.clearAccessToken();
      return "too-late";
    });
    await assert.rejects(pending, /登录状态已变化/);
    assert.equal(token.getAccessToken(), null);
  } finally {
    env.restore();
  }
});

test("without Web Locks refresh fails closed", async () => {
  const env = browser();
  try {
    Object.defineProperty(globalThis, "navigator", {
      configurable: true,
      value: {},
    });
    const token = load("../lib/auth/token.ts");
    const coordinator = load("../lib/auth/coordinator.ts", {
      "./token": token,
    });
    await assert.rejects(
      coordinator.refreshAccessToken(null, async () => "unsafe"),
      /Web Locks/,
    );
  } finally {
    env.restore();
  }
});

test("a new login does not inherit an older in-flight refresh", async () => {
  const env = browser();
  try {
    const token = load("../lib/auth/token.ts");
    token.setAccessToken("expired-old-account");
    const coordinator = load("../lib/auth/coordinator.ts", {
      "./token": token,
    });
    let releaseOld;
    let oldStarted;
    const gate = new Promise((resolve) => {
      releaseOld = resolve;
    });
    const started = new Promise((resolve) => {
      oldStarted = resolve;
    });
    const oldRefresh = coordinator.refreshAccessToken(
      "expired-old-account",
      async () => {
        oldStarted();
        await gate;
        return "stale-access";
      },
    );
    await started;
    token.clearAccessToken();
    coordinator.announceAuthChange("login");
    token.setAccessToken("new-account-access");
    let newCalls = 0;
    const newRefresh = coordinator.refreshAccessToken(
      "new-account-access",
      async () => {
        newCalls += 1;
        return "fresh-new-account";
      },
    );
    releaseOld();
    await assert.rejects(oldRefresh, /登录状态已变化/);
    assert.equal(await newRefresh, "fresh-new-account");
    assert.equal(newCalls, 1);
    assert.equal(token.getAccessToken(), "fresh-new-account");
  } finally {
    env.restore();
  }
});

test("two tabs serialize refresh and share only an in-memory Access Token", async () => {
  const env = browser();
  const previousChannel = globalThis.BroadcastChannel;
  const channels = new Set();
  class Channel {
    listeners = new Set();
    constructor() {
      channels.add(this);
    }
    addEventListener(_type, listener) {
      this.listeners.add(listener);
    }
    removeEventListener(_type, listener) {
      this.listeners.delete(listener);
    }
    postMessage(data) {
      for (const channel of channels)
        if (channel !== this)
          queueMicrotask(() =>
            channel.listeners.forEach((listener) => listener({ data })),
          );
    }
    close() {
      channels.delete(this);
    }
  }
  globalThis.BroadcastChannel = Channel;
  globalThis.window.BroadcastChannel = Channel;
  try {
    const firstToken = load("../lib/auth/token.ts");
    const secondToken = load("../lib/auth/token.ts");
    firstToken.setAccessToken("expired");
    secondToken.setAccessToken("expired");
    const first = load("../lib/auth/coordinator.ts", { "./token": firstToken });
    const second = load("../lib/auth/coordinator.ts", {
      "./token": secondToken,
    });
    const unsubscribe = second.onAuthMessage(() => {});
    let calls = 0;
    const request = async () => {
      calls += 1;
      await Promise.resolve();
      return "fresh";
    };
    const results = await Promise.all([
      first.refreshAccessToken("expired", request),
      second.refreshAccessToken("expired", request),
    ]);
    assert.deepEqual(results, ["fresh", "fresh"]);
    assert.equal(calls, 1);
    assert.equal(secondToken.getAccessToken(), "fresh");
    assert.equal(env.storage.getItem("access_token"), null);
    unsubscribe();
  } finally {
    channels.forEach((channel) => channel.close());
    globalThis.BroadcastChannel = previousChannel;
    env.restore();
  }
});

test("a token from the previous account is unavailable as soon as the shared epoch changes", () => {
  const env = browser();
  try {
    const token = load("../lib/auth/token.ts");
    const coordinator = load("../lib/auth/coordinator.ts", { "./token": token });
    token.setAccessToken("account-one-token");
    coordinator.announceAuthChange("login");
    assert.equal(token.getAccessToken(), null);
  } finally { env.restore(); }
});

test("stale and duplicate auth broadcasts cannot change the current session", () => {
  const env = browser();
  const previousChannel = globalThis.BroadcastChannel;
  let channel;
  class Channel {
    listeners = new Set();
    constructor() { channel = this; }
    addEventListener(_type, listener) { this.listeners.add(listener); }
    removeEventListener(_type, listener) { this.listeners.delete(listener); }
    postMessage() {}
    deliver(data) { for (const listener of this.listeners) listener({ data }); }
  }
  globalThis.BroadcastChannel = Channel;
  globalThis.window.BroadcastChannel = Channel;
  try {
    const token = load("../lib/auth/token.ts");
    const coordinator = load("../lib/auth/coordinator.ts", { "./token": token });
    const received = [];
    const unsubscribe = coordinator.onAuthMessage((type) => received.push(type));
    env.storage.setItem("ssp-auth-epoch", "current");
    token.setAccessToken("current-token");
    channel.deliver({ type: "logout", epoch: "old" });
    channel.deliver({ type: "login", epoch: "old" });
    channel.deliver({ type: "login", epoch: "current" });
    channel.deliver({ type: "login", epoch: "current" });
    assert.deepEqual(received, ["login"]);
    token.clearAccessToken();
    channel.deliver({ type: "token", epoch: "current", token: "late-token" });
    assert.equal(token.getAccessToken(), null);
    unsubscribe();
  } finally {
    globalThis.BroadcastChannel = previousChannel;
    env.restore();
  }
});

test("storage events keep tabs synchronized when BroadcastChannel is unavailable", () => {
  const env = browser();
  const listeners = new Map();
  globalThis.window.addEventListener = (type, listener) => listeners.set(type, listener);
  globalThis.window.removeEventListener = (type) => listeners.delete(type);
  try {
    const token = load("../lib/auth/token.ts");
    const coordinator = load("../lib/auth/coordinator.ts", { "./token": token });
    const events = [];
    const unsubscribe = coordinator.onAuthMessage((type) => events.push(type));
    env.storage.setItem("ssp-auth-epoch", "logout:later");
    listeners.get("storage")({ key: "ssp-auth-epoch", newValue: "logout:later" });
    listeners.get("storage")({ key: "ssp-auth-epoch", newValue: "logout:later" });
    assert.deepEqual(events, ["logout"]);
    unsubscribe();
    assert.equal(listeners.has("storage"), false);
  } finally { env.restore(); }
});

test("storage access failure blocks auth operations before Cookie changes", async () => {
  const env = browser();
  try {
    env.storage.getItem = () => { throw new Error("storage blocked"); };
    const token = load("../lib/auth/token.ts");
    const coordinator = load("../lib/auth/coordinator.ts", { "./token": token });
    assert.throws(() => token.getAccessToken(), /storage blocked/);
    let worked = false;
    await assert.rejects(coordinator.withAuthLock(async () => { worked = true; }), /storage blocked/);
    assert.equal(worked, false);
  } finally { env.restore(); }
});

test("a late earlier refresh broadcast cannot overwrite a newer access token", async () => {
  const env = browser();
  const previousChannel = globalThis.BroadcastChannel;
  const channels = [];
  const queued = [];
  class Channel {
    listeners = new Set();
    constructor() { channels.push(this); }
    addEventListener(_type, listener) { this.listeners.add(listener); }
    removeEventListener(_type, listener) { this.listeners.delete(listener); }
    postMessage(data) { queued.push({ sender: this, data }); }
    close() {}
  }
  globalThis.BroadcastChannel = Channel;
  globalThis.window.BroadcastChannel = Channel;
  try {
    const firstToken = load("../lib/auth/token.ts");
    const secondToken = load("../lib/auth/token.ts");
    firstToken.setAccessToken("old-access");
    secondToken.setAccessToken("old-access");
    const first = load("../lib/auth/coordinator.ts", { "./token": firstToken });
    const second = load("../lib/auth/coordinator.ts", { "./token": secondToken });
    const unsubscribe = second.onAuthMessage(() => {});
    await first.refreshAccessToken("old-access", async () => "first-access");
    await second.refreshAccessToken("old-access", async () => "newest-access");
    const earlier = queued.find((message) => message.data.type === "token");
    for (const channel of channels) if (channel !== earlier.sender)
      for (const listener of channel.listeners) listener({ data: earlier.data });
    assert.equal(secondToken.getAccessToken(), "newest-access");
    unsubscribe();
  } finally {
    globalThis.BroadcastChannel = previousChannel;
    env.restore();
  }
});

test("an uncertain refresh result is not retried against a possibly rotated Cookie", async () => {
  const env = browser();
  try {
    const token = load("../lib/auth/token.ts");
    token.setAccessToken("expired");
    const coordinator = load("../lib/auth/coordinator.ts", { "./token": token });
    let calls = 0;
    await assert.rejects(coordinator.refreshAccessToken("expired", async () => {
      calls += 1;
      throw Object.assign(new Error("network timeout"), { status: 0 });
    }), /network timeout/);
    await assert.rejects(coordinator.refreshAccessToken("expired", async () => {
      calls += 1;
      return "unsafe-retry";
    }), /刷新结果不确定/);
    assert.equal(calls, 1);
  } finally { env.restore(); }
});

test("late BroadcastChannel delivery after Web Lock grant cannot cause a second refresh", async () => {
  const env = browser();
  const previousChannel = globalThis.BroadcastChannel;
  class DelayedChannel {
    listeners = new Set();
    addEventListener(_type, listener) { this.listeners.add(listener); }
    removeEventListener(_type, listener) { this.listeners.delete(listener); }
    postMessage() { /* Deliberately delivered after the lock grant. */ }
  }
  globalThis.BroadcastChannel = DelayedChannel;
  globalThis.window.BroadcastChannel = DelayedChannel;
  try {
    const firstToken = load("../lib/auth/token.ts");
    const secondToken = load("../lib/auth/token.ts");
    firstToken.setAccessToken("expired");
    secondToken.setAccessToken("expired");
    const first = load("../lib/auth/coordinator.ts", { "./token": firstToken });
    const second = load("../lib/auth/coordinator.ts", { "./token": secondToken });
    let calls = 0;
    const request = async () => { calls += 1; return "fresh"; };
    const results = await Promise.allSettled([
      first.refreshAccessToken("expired", request),
      second.refreshAccessToken("expired", request),
    ]);
    assert.equal(calls, 1);
    assert.equal(results.filter((result) => result.status === "fulfilled").length, 1);
  } finally {
    globalThis.BroadcastChannel = previousChannel;
    env.restore();
  }
});
