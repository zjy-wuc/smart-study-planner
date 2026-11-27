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
      jsx: ts.JsxEmit.ReactJSX,
    },
  }).outputText;
  const loaded = { exports: {} };
  new Function("require", "module", "exports", code)(
    (name) => {
      if (!(name in dependencies))
        throw new Error(`Unexpected import: ${name}`);
      return dependencies[name];
    },
    loaded,
    loaded.exports,
  );
  return loaded.exports;
}

test("admin API uses the existing client and sends only the selected action payload", async () => {
  const calls = [];
  const apiFetch = async (path, options) => {
    calls.push({ path, options });
    return { data: { items: [], total: 0, changed: true } };
  };
  const service = load("../services/admin.service.ts", {
    "@/lib/api/client": { apiFetch, ApiError: class ApiError extends Error {} },
  });
  await service.getAdminUsers({
    page: 2,
    page_size: 50,
    keyword: "张三",
    status: "ACTIVE",
  });
  await service.actOnAdminUser(7, "BAN_USER", "违规使用");
  await service.updateAdminAIConfig({
    user_daily_limit: 20,
    reason: "调整额度",
  });
  assert.equal(
    calls[0].path,
    "/admin/users?page=2&page_size=50&keyword=%E5%BC%A0%E4%B8%89&status=ACTIVE",
  );
  assert.equal(calls[1].path, "/admin/users/7/ban");
  assert.equal(calls[1].options.method, "POST");
  assert.deepEqual(JSON.parse(calls[1].options.body), { reason: "违规使用" });
  assert.equal(calls[2].options.method, "PATCH");
  assert.deepEqual(JSON.parse(calls[2].options.body), {
    user_daily_limit: 20,
    reason: "调整额度",
  });
});

test("ADMIN_REQUIRED notifies the guard without turning a business 403 into logout", async () => {
  const previousWindow = globalThis.window;
  let notices = 0;
  globalThis.window = {
    dispatchEvent: () => {
      notices += 1;
    },
  };
  try {
    class ApiError extends Error {
      constructor(code) {
        super(code);
        this.code = code;
      }
    }
    const service = load("../services/admin.service.ts", {
      "@/lib/api/client": {
        apiFetch: async () => {
          throw new ApiError("ADMIN_REQUIRED");
        },
        ApiError,
      },
    });
    await assert.rejects(service.getAdminDashboard(), {
      code: "ADMIN_REQUIRED",
    });
    assert.equal(notices, 1);
  } finally {
    globalThis.window = previousWindow;
  }
});

test("admin identity check does not treat every 401 as a confirmed logout", async () => {
  const effects = [];
  const redirects = [];
  const errors = [];
  class ApiError extends Error {
    constructor() {
      super("请稍后重试");
      this.status = 401;
      this.code = "BUSINESS_REJECTED";
    }
  }
  const { AdminShell } = load("../components/admin/AdminShell.tsx", {
    "react": {
      useEffect: (effect) => effects.push(effect),
      useState: (initial) => [initial, (value) => errors.push(value)],
    },
    "react/jsx-runtime": { jsx: () => null, jsxs: () => null },
    "next/link": {},
    "next/navigation": {
      usePathname: () => "/admin",
      useRouter: () => ({ replace: (path) => redirects.push(path) }),
    },
    "lucide-react": {},
    "@/contexts/AuthContext": {
      useAuth: () => ({ status: "authenticated", user: { id: 1, role: "ADMIN" } }),
    },
    "@/services/auth.service": {
      getCurrentUser: async () => { throw new ApiError(); },
    },
    "@/lib/api/client": { ApiError },
    "@/messages": { messages: { admin: {}, auth: {}, common: {} } },
    "@/components/css/Admin.css": {},
  });
  AdminShell({ children: null });
  effects[1]();
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(redirects, []);
  assert.ok(errors.includes("请稍后重试"));
});

test("audit comparison distinguishes removed, added, null, false and zero fields", () => {
  const { auditChanges } = load("../lib/admin/audit.ts");
  const before = {
    unchanged: 0,
    removed: false,
    nullable: null,
    switched: false,
  };
  const after = { unchanged: 0, nullable: false, switched: 0, result_count: 0 };
  assert.deepEqual(auditChanges(before, after), {
    changed: ["removed", "nullable", "switched"],
    resultOnly: ["result_count"],
  });
});
