# Auth V2.0 前端现状审计

> 审计对象：`d:\project\next-fro`（Next.js 16.4.2 + React 19.3.0 + TypeScript）
> 审计时间：2026-11-24
> 审计方式：只读。仅阅读源码与配置文件。
> 未修改任何前端代码，未安装依赖，未执行构建。
> 敏感信息：`.env.local` 仅列出变量名，未输出任何值。

---

## 0. 结论摘要

| 项 | 现状 |
|---|---|
| 框架 | Next.js `16.4.2`（App Router）、React `19.3.0`、Tailwind 4 |
| 请求封装 | 自研 `lib/api/client.ts`：`apiFetch`（JSON）+ `authenticatedFetch`（原始 Response） |
| 双 Token 存储 | `localStorage`，键名 `access_token` / `refresh_token` |
| 自动刷新 | 仅当 401 且 `detail.code === "ACCESS_EXPIRED"` 时单飞刷新；用 `refreshPromise` 合并并发 |
| 认证状态管理 | **没有 AuthContext / Redux / Zustand**；页面各自调用 `getCurrentUser` |
| 路由守卫 | `WorkspaceShell` 仅在挂载时检查 `localStorage` 是否有 Access Token；不校验有效性 |
| SSE | `fetch` + `ReadableStream` + 自研 `lib/api/sse.ts` 解析器；`Authorization: Bearer` 头 |
| Axios | **未安装、未使用**（`package.json` 与源码均无） |
| 直接 `fetch` | 仅 3 处：`client.ts` 内部 2 处、`app/health-check/page.tsx` 1 处 |
| 直接读 Token | 仅 `lib/auth/token.ts` 与 3 个调用点（`WorkspaceShell`、`useDashboardData`、`client.ts`） |
| 接口规模 | 后端 67 个路由：61 个 JSON 接口 + 6 个 SSE 接口；前端服务层 50 处统一封装调用（48 处 `apiFetch`、2 处 `authenticatedFetch`，后者即 SSE 入口） |

---

## 1. 前端源码目录结构

排除 `node_modules`、`.next`、`.git`、`.pytest_cache`：

```text
next-fro/
├─ app/
│  ├─ layout.tsx
│  ├─ globals.css
│  ├─ (auth)/
│  │  ├─ login/page.tsx
│  │  └─ register/page.tsx
│  ├─ (workspace)/
│  │  ├─ layout.tsx
│  │  ├─ page.tsx
│  │  ├─ ai/page.tsx
│  │  ├─ ai/practice/page.tsx
│  │  ├─ ai/practice/history/page.tsx
│  │  ├─ ai/practice/history/[recordId]/page.tsx
│  │  ├─ focus/page.tsx
│  │  ├─ history/page.tsx
│  │  ├─ knowledge/page.tsx
│  │  ├─ knowledge/new/page.tsx
│  │  ├─ knowledge/trash/page.tsx
│  │  ├─ knowledge/[noteId]/page.tsx
│  │  ├─ plans/page.tsx
│  │  ├─ plans/new/page.tsx
│  │  ├─ plans/[planId]/page.tsx
│  │  ├─ plans/[planId]/steps/page.tsx
│  │  ├─ profile/page.tsx
│  │  ├─ reminders/page.tsx
│  │  ├─ statistics/page.tsx
│  │  └─ task/today/page.tsx
│  └─ health-check/page.tsx
├─ components/
│  ├─ auth/
│  │  ├─ LoginForm.tsx
│  │  └─ UsersProfile.tsx
│  ├─ RegisterForm.tsx
│  ├─ layout/WorkspaceShell.tsx
│  ├─ ai/{PracticeFlow,PracticeResult}.tsx
│  ├─ knowledge/{KnowledgeAiPanel,KnowledgeEditor,KnowledgeNoteList,KnowledgeQaPanel,...}.tsx
│  ├─ dashboard/, focus/, plans/, reminders/, statistics/, tasks/, ui/, common/, css/
├─ hooks/
│  ├─ useAiPractice.ts
│  ├─ useDailyCheckin.ts
│  ├─ useDashboardData.ts
│  ├─ useFocusSession.ts
│  ├─ useFocusStatistics.ts
│  ├─ useKnowledge.ts
│  ├─ useKnowledgeAi.ts
│  ├─ useKnowledgeQa.ts
│  ├─ useStatistics.ts
│  └─ useTodayTasks.ts
├─ lib/
│  ├─ api/
│  │  ├─ client.ts
│  │  └─ sse.ts
│  ├─ auth/token.ts
│  ├─ knowledge.ts
│  ├─ knowledge-ai-draft.ts
│  ├─ knowledge-qa.ts
│  └─ plans/{business-date,date-range,step-rule}.ts
├─ services/
│  ├─ auth.service.ts
│  ├─ ai-practice.service.ts
│  ├─ focus.service.ts
│  ├─ knowledge.service.ts
│  ├─ knowledge-ai.service.ts
│  ├─ plans.service.ts
│  ├─ progress.service.ts
│  ├─ schedules.service.ts
│  ├─ statistics.service.ts
│  ├─ steps.service.ts
│  └─ tasks.service.ts
├─ types/
│  ├─ auth.ts
│  ├─ api.ts
│  ├─ ai-practice.ts
│  ├─ knowledge.ts
│  ├─ knowledge-ai.ts
│  ├─ plan.ts
│  ├─ progress.ts
│  ├─ reminder.ts
│  ├─ schedule.ts
│  ├─ statistics.ts
│  ├─ step.ts
│  └─ task.ts
├─ messages/
│  ├─ index.ts
│  ├─ types.ts
│  └─ zh-CN/*.ts（含 auth.ts、profile.ts、common.ts 等）
├─ tests/
│  ├─ ai-practice-flow.test.mjs
│  ├─ ai-practice-home.test.mjs
│  ├─ ai-practice.test.mjs
│  ├─ knowledge-ai.test.mjs
│  └─ knowledge.test.mjs
├─ next.config.ts
├─ tsconfig.json
├─ package.json
├─ eslint.config.mjs
└─ .env.local（仅变量名见第 9 节）
```

---

## 2. `package.json`（全文）

```json
{
  "name": "next-fro",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "eslint"
  },
  "dependencies": {
    "lucide-react": "^1.73.0",
    "next": "16.4.2",
    "react": "19.3.0",
    "react-dom": "19.3.0",
    "react-markdown": "^10.1.0",
    "recharts": "^3.10.1"
  },
  "devDependencies": {
    "@tailwindcss/turbopack": "^4",
    "@types/node": "^20",
    "@types/react": "^19",
    "@types/react-dom": "^19",
    "eslint": "^9",
    "eslint-config-next": "16.4.2",
    "tailwindcss": "^4",
    "typescript": "^5"
  },
  "allowScripts": {
    "unrs-resolver@1.12.2": true
  }
}
```

要点：

- 依赖中没有 `axios`、没有状态管理库、没有表单库、没有 UI 组件库。
- `next 16.4.2` 的 `next.config.ts` 启用了 `cacheComponents`、`partialPrefetching`、`experimental.agentFeedback` 与 Tailwind Turbopack 规则。
- 测试脚本不在 `package.json` 中；`tests/*.mjs` 需用 Node 直接运行或由外部测试器执行。

---

## 3. HTTP 请求封装 `lib/api/client.ts`（全文）

```ts
import { messages } from "@/messages";
import {
  getAccessToken,
  getRefreshToken,
  setTokenPair,
  removeTokenPair,
} from "@/lib/auth/token";

import type {
  ApiResponse,
  TokenPair,
} from "@/types/auth";

import type { ValidationIssue } from "@/types/api";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

// 携带 HTTP 状态码的请求错误，便于调用方按状态处理

export class ApiError extends Error {
  status: number;
  validationIssues: ValidationIssue[];

  constructor(
    message: string,
    status: number,
    validationIssues: ValidationIssue[] = [],
  ) {
    super(message);

    this.name = "ApiError";
    this.status = status;
    this.validationIssues = validationIssues;
  }
}

// 保存当前正在进行的刷新任务
// 多个请求可以共享同一个 Promise
let refreshPromise: Promise<string | null> | null = null;


// 刷新 Access Token
async function refreshAccessToken(): Promise<string | null> {
  // 如果已经有刷新任务，就直接等待它
  if (refreshPromise) {
    return refreshPromise;
  }

  refreshPromise = (async () => {
    const refreshToken = getRefreshToken();

    if (!refreshToken) {
      return null;
    }

    try {
      // 注意：这里直接使用 fetch
      // 不能再调用 apiFetch，否则可能产生递归刷新
      const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          refresh_token: refreshToken,
        }),
      });

      const body: ApiResponse<TokenPair> = await response.json();

      if (
        !response.ok ||
        !body.data?.access_token ||
        !body.data?.refresh_token
      ) {
        return null;
      }

      // 保存后端返回的新 Token Pair
      setTokenPair(
        body.data.access_token,
        body.data.refresh_token,
      );

      return body.data.access_token;

    } catch {
      return null;
    }
  })();

  try {
    return await refreshPromise;
  } finally {
    refreshPromise = null;
  }
}


// 发送一次 HTTP 请求
async function sendRequest(
  path: string,
  options: RequestInit,
  token: string | null,
): Promise<Response> {
  const headers = new Headers(options.headers);

  // 没有指定 Content-Type 时，默认使用 JSON
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  // 有 Access Token 才设置 Authorization
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  return fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  });
}


// API 请求的额外配置，用于控制是否跳过刷新
// 默认不跳过刷新
export interface ApiFetchOptions extends RequestInit {
  skipAuthRefresh?: boolean;
}

// 返回原始 Response，供 SSE 等非 JSON 接口复用同一套双 Token 刷新逻辑。
export async function authenticatedFetch(
  path: string,
  options: ApiFetchOptions = {},
): Promise<Response> {
  const originalToken = getAccessToken();
  const { skipAuthRefresh = false, ...requestOptions } = options;
  let response = await sendRequest(path, requestOptions, originalToken);

  let errorBody: unknown = null;
  if (response.status === 401) {
    try {
      errorBody = await response.clone().json();
    } catch {
      errorBody = null;
    }
  }

  const accessExpired =
    response.status === 401 &&
    (errorBody as { detail?: { code?: string } } | null)?.detail?.code === "ACCESS_EXPIRED";

  if (!accessExpired || skipAuthRefresh) return response;

  const currentToken = getAccessToken();
  const newAccessToken =
    originalToken && currentToken && originalToken !== currentToken
      ? currentToken
      : await refreshAccessToken();

  if (!newAccessToken) {
    removeTokenPair();
    return response;
  }

  response = await sendRequest(path, requestOptions, newAccessToken);
  return response;
}



// 统一 API 请求入口
export async function apiFetch<T>(
  path: string,
  options: ApiFetchOptions = {},
): Promise<T> {

  const response = await authenticatedFetch(path, options);
  const body = await response.json();

  // 最终响应仍然失败，就抛出错误
  
if (!response.ok) {
  const validationIssues: ValidationIssue[] =
    response.status === 422 && Array.isArray(body?.data)
      ? body.data
      : [];

  const message =
    typeof body?.message === "string"
      ? body.message
      : typeof body?.detail === "string"
        ? body.detail
        : typeof body?.detail?.message === "string"
          ? body.detail.message
          : messages.common.httpRequestFailed(response.status);

  throw new ApiError(
    message,
    response.status,
    validationIssues,
  );
}

  return body as T;
}
```

关键行为梳理：

1. `API_BASE_URL` 来自 `NEXT_PUBLIC_API_BASE_URL`，缺省 `http://127.0.0.1:8000`，属于**浏览器跨源直连**。
2. `apiFetch<T>`：统一 JSON 入口；非 2xx 抛 `ApiError`，从 `message` / `detail` / `detail.message` 依次取文案，422 时把 `data` 作为字段校验问题。
3. `authenticatedFetch`：返回原始 `Response`，供 SSE 复用；只在 `401 + detail.code === "ACCESS_EXPIRED"` 时自动刷新。
4. 刷新单飞：模块级 `refreshPromise` 合并并发；刷新请求本身用裸 `fetch`，避免递归。
5. 刷新失败会 `removeTokenPair()` 并返回原始 401 响应，由调用方处理跳转。
6. 所有请求默认加 `Content-Type: application/json`（GET 也会加）；登录接口通过显式设置覆盖为 `application/x-www-form-urlencoded`。
7. 没有请求超时、没有重试、没有统一 401 跳转、没有 CSRF 头。

对 Auth V2.0 的影响：

- 若改为 HttpOnly Cookie，需要删除 `Authorization` 注入逻辑，改为 `credentials: "include"`，并新增 CSRF 头；`refreshAccessToken` 不能再读取 `refresh_token`，刷新接口应只依赖 Cookie。
- 若保持 Bearer，则只需扩展登录/注册/改密/换绑接口，`client.ts` 基本不动。
- 错误码 `ACCESS_EXPIRED` 是前后端契约，后端改造时不能随意改名。

---

## 4. SSE 封装 `lib/api/sse.ts`（全文）

```ts
import type { KnowledgeAiEvent } from "@/types/knowledge-ai";

function parseBlock(block: string): KnowledgeAiEvent | null {
  let event = "message";
  const data: string[] = [];

  for (const line of block.split("\n")) {
    if (!line || line.startsWith(":")) continue;
    const separator = line.indexOf(":");
    const field = separator === -1 ? line : line.slice(0, separator);
    let value = separator === -1 ? "" : line.slice(separator + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") event = value;
    if (field === "data") data.push(value);
  }

  if (!data.length || !["start", "delta", "reviewing", "done", "blocked", "error"].includes(event)) return null;
  return { event: event as KnowledgeAiEvent["event"], data: JSON.parse(data.join("\n")) as Record<string, unknown> };
}

export async function* readSseEvents(
  stream: ReadableStream<Uint8Array>,
): AsyncGenerator<KnowledgeAiEvent, void, void> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let exhausted = false;

  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      const trailingCarriageReturn = !done && buffer.endsWith("\r");
      const tail = trailingCarriageReturn ? "\r" : "";
      const normalizable = trailingCarriageReturn ? buffer.slice(0, -1) : buffer;
      buffer = normalizable.replace(/\r\n|\r/g, "\n") + tail;

      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const parsed = parseBlock(buffer.slice(0, boundary));
        buffer = buffer.slice(boundary + 2);
        if (parsed) yield parsed;
        boundary = buffer.indexOf("\n\n");
      }

      if (done) {
        exhausted = true;
        const parsed = parseBlock(buffer.replace(/\r\n|\r/g, "\n"));
        if (parsed) yield parsed;
        return;
      }
    }
  } finally {
    if (!exhausted) {
      try { await reader.cancel(); } catch { /* 请求取消时读取器可能已经关闭。 */ }
    }
    reader.releaseLock();
  }
}
```

要点：

- 手写 SSE 解析器，支持 `\r\n` / `\r` 归一化、跨 chunk 缓冲、`event:` 白名单（`start/delta/reviewing/done/blocked/error`）。
- 使用 `ReadableStream.getReader()`，不是 `EventSource`；因此**可以携带 Authorization 头**，未来也可以加 `credentials: "include"`。
- 解析失败（非 JSON 或未知 event）会跳过该块，不会中断整个流。
- 取消时会 `reader.cancel()` 并 `releaseLock()`。

---

## 5. Token 存储 `lib/auth/token.ts`（全文）

```ts
/**
 * 保存、读取、删除双 Token
 */

const ACCESS_TOKEN_KEY = "access_token";
const REFRESH_TOKEN_KEY = "refresh_token";

// 保存 Access Token
export function setAccessToken(token: string) {
  localStorage.setItem(ACCESS_TOKEN_KEY, token);
}

// 获取 Access Token
export function getAccessToken() {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

// 删除 Access Token
export function removeAccessToken() {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
}

// 保存 Refresh Token
export function setRefreshToken(token: string) {
  localStorage.setItem(REFRESH_TOKEN_KEY, token);
}

// 获取 Refresh Token
export function getRefreshToken() {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

// 删除 Refresh Token
export function removeRefreshToken() {
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

// 同时保存双 Token
export function setTokenPair(
  accessToken: string,
  refreshToken: string,
) {
  setAccessToken(accessToken);
  setRefreshToken(refreshToken);
}

// 同时清理双 Token
export function removeTokenPair() {
  removeAccessToken();
  removeRefreshToken();
}
```

要点：

- Access / Refresh 均存 `localStorage`，键名为 `access_token`、`refresh_token`。
- 没有任何过期时间记录、没有加密、没有跨标签页同步。
- 所有读写都直接访问 `localStorage`，在 SSR 环境下调用会抛错；现有调用点均在 `"use client"` 组件或浏览器请求路径中。
- 迁移到 HttpOnly Cookie 后，本文件将整体废弃（或仅保留「是否已登录」的内存标记）。

---

## 6. Auth Service 与 TypeScript 类型

`services/auth.service.ts`（全文）：

```ts
import { apiFetch } from "@/lib/api/client";
import { getRefreshToken, removeTokenPair } from "@/lib/auth/token";
import type {
  ApiResponse,
  RegisterData,
  RegisterRequest,
  LoginRequest,
  LoginResponse,
  RefreshRequest,
  User,
} from "@/types/auth";



// 调用后端 POST /users 注册用户
export function registerUser(payload: RegisterRequest) {
  return apiFetch<ApiResponse<RegisterData>>("/users", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// 调用后端 POST /auth/login 登录用户
export async function loginUser(
  data: LoginRequest
): Promise<ApiResponse<LoginResponse>> {
  const formData = new URLSearchParams();// 构建表单数据,因为login接口接受URL类型的数据，用了OAuth2PasswordRequestForm格式接收

  formData.append("username", data.username);
  formData.append("password", data.password);

  return apiFetch<ApiResponse<LoginResponse>>(
    "/auth/login",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: formData,
    }
  );
}


// 获取当前登录用户的信息
export async function getCurrentUser(): Promise<ApiResponse<User>> {
  return apiFetch<ApiResponse<User>>("/users/me");
}



// 调用后端 POST /auth/logout 退出当前会话
export async function logoutUser(): Promise<void> {
  const refreshToken = getRefreshToken();

  try {
    // 有 Refresh Token 才请求后端撤销会话
    if (refreshToken) {
      await apiFetch<ApiResponse<null>>(
        "/auth/logout",
        {
          method: "POST",
          body: JSON.stringify({
            refresh_token: refreshToken,
          } satisfies RefreshRequest),/*check type*/
        },
      );
    }
  } finally {
    // 无论后端请求成功还是失败，都清理本地双 Token
    removeTokenPair();
  }
}


// 调用后端 POST /auth/logout-all
// 撤销当前用户的所有登录会话
export async function logoutAllSessions(): Promise<void> {
  try {
    await apiFetch<ApiResponse<null>>(
      "/auth/logout-all",
      {
        method: "POST",
      },
    );
  } finally {
    // 无论请求成功还是失败，都清理当前设备的双 Token
    removeTokenPair();
  }
}
```

`types/auth.ts`（全文）：

```ts
// 后端统一响应结构
export interface ApiResponse<T> {
  code: number;
  message: string;
  data: T;
  detail?: {
    code?: string;
    message?: string;
  };
}
// 注册请求体
export interface RegisterRequest {
  username: string;
  password: string;
  nickname: string;
}

// 注册成功后返回的用户信息
export interface RegisterData {
  id: number;
  username: string;
  nickname: string;
}






 // 用户登录请求数据
 
export interface LoginRequest {
  username: string;
  password: string;
}


 
export interface LoginResponse extends TokenPair {
  user: User;
}

// 当前登录用户信息（GET /users/me 返回）
export interface User {
  id: number;
  username: string;
  nickname: string | null;
}




//用户登录成功返回的数据
 
export interface LoginResponse extends TokenPair {
  user: User;
}


// 双 Token 响应数据
export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

// Refresh Token 请求体
export interface RefreshRequest {
  refresh_token: string;
}
```

要点与问题：

- 注册：`POST /users`，JSON `{username,password,nickname}`；成功后组件立即用同一账号密码自动登录。
- 登录：`POST /auth/login`，`application/x-www-form-urlencoded`（`username`、`password`）。Auth V2.0 若改为邮箱验证码登录，需新增 JSON 接口或继续用 form。
- 当前用户：`GET /users/me`，返回 `{id,username,nickname,is_active}`（前端类型只声明了前三个）。
- 退出当前：`POST /auth/logout`，body 为 `{refresh_token}`；无论成败都清理本地 token。
- 退出全部：`POST /auth/logout-all`，仅 Bearer；同样清理本地 token。
- `types/auth.ts` 中 `LoginResponse` 被**重复声明两次**（第 39-41 行与第 55-57 行），内容一致，TypeScript 会合并，但属于冗余。
- `User` 类型没有 `email`、`avatar_url`、`email_verified_at`，无法支撑新资料页。

---


## 7. 认证页面、路由守卫与登录状态初始化

### 7.1 页面结构

- `/login` → `app/(auth)/login/page.tsx` → `components/auth/LoginForm.tsx`
- `/register` → `app/(auth)/register/page.tsx` → `components/RegisterForm.tsx`
- `(workspace)` 全部页面共享 `app/(workspace)/layout.tsx` → `components/layout/WorkspaceShell.tsx`

### 7.2 登录表单关键逻辑（`LoginForm.tsx`）

```tsx
const result = await loginUser(formData);
const accessToken = result.data.access_token;
const refreshToken = result.data.refresh_token;

setTokenPair(accessToken, refreshToken);
setMessage(messages.auth.loginSuccess);
router.replace("/");
```

现状：

- 仅支持用户名 + 密码；无邮箱、无验证码、无「忘记密码」入口。
- 登录成功后立即把双 Token 写入 `localStorage`。
- 已登录用户访问 `/login` 不会自动跳转（页面无守卫）。
- 错误文案直接取 `Error.message`（`ApiError.message` 已由 `apiFetch` 统一提取）。

### 7.3 注册表单关键逻辑（`RegisterForm.tsx`）

```tsx
await registerUser(formData);
setRegistered(true);

try {
  const result = await loginUser({
    username: formData.username,
    password: formData.password,
  });
  setTokenPair(result.data.access_token, result.data.refresh_token);
  router.replace("/");
} catch {
  setMessage(messages.auth.registerSuccessLoginFailed);
}
```

现状：

- 注册成功即自动登录，说明当前后端注册接口不要求邮箱验证。
- 若 Auth V2.0 改为「邮箱验证码注册」，该自动登录流程必须重写：注册 → 发码 → 校验 → 创建用户 → 再登录。

### 7.4 路由守卫（`WorkspaceShell.tsx`）

```tsx
useEffect(() => {
  if (!getAccessToken()) {
    router.replace("/login");
    return;
  }

  setAuthChecked(true);
}, [router]);
```

现状与缺口：

- **只判断 Access Token 是否存在**，不判断是否过期、不调用 `/users/me` 验证。
- 若 Access Token 已过期但 Refresh Token 有效，仍会放行；后续第一个 API 请求触发自动刷新。
- 若两个 Token 都失效，用户会先看到页面骨架，再在请求 401 后被各页面自行处理（不统一）。
- 没有全局「登录状态初始化」：没有 `AuthProvider`、没有 `useAuth`、没有用户信息缓存。
- `useDashboardData` 也重复做了同样的「无 token 就 replace('/login')」检查。

### 7.5 个人资料页（`components/auth/UsersProfile.tsx`）

- 挂载时调用 `getCurrentUser()` 获取用户；401 时清空 token 并跳转登录。
- 展示 `username`、`nickname`、`id`；头像用昵称/用户名首字符渲染，**不读取 `avatar_url`**。
- 提供「退出当前设备」「退出所有设备」两个操作，分别调用 `logoutUser` / `logoutAllSessions`。
- 没有修改昵称、修改密码、换绑邮箱、头像上传、会话列表等入口。

### 7.6 前端认证状态管理结论

- 当前是「无集中状态」：token 存 `localStorage`，用户信息按需请求。
- Auth V2.0 若引入 HttpOnly Cookie，需要重新设计「是否登录」的判断来源（例如 `/auth/session` 探针或 `/users/me`），不能再依赖 `getAccessToken()`。
- 若保持 Bearer，也建议引入轻量 `AuthContext`，统一处理：初始化、刷新、401 跳转、用户信息缓存、登出清理。

---

## 8. AI 流式接口的认证方式

### 8.1 `services/knowledge-ai.service.ts`（全文）

```ts
import { ApiError, authenticatedFetch } from "@/lib/api/client";
import { readSseEvents } from "@/lib/api/sse";
import type { KnowledgeAiDone, KnowledgeAiEvent, KnowledgeAiRequest } from "@/types/knowledge-ai";

type ErrorBody = {
  message?: unknown;
  detail?: unknown;
};

export function aiResponseErrorMessage(body: unknown, status: number): string {
  if (!body || typeof body !== "object") return `AI 请求失败（${status}）`;
  const { detail, message } = body as ErrorBody;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((issue) => issue && typeof issue === "object" ? (issue as { msg?: unknown }).msg : null)
      .filter((value): value is string => typeof value === "string" && Boolean(value.trim()));
    if (messages.length) return messages.join("；");
  }
  if (detail && typeof detail === "object") {
    const detailMessage = (detail as { message?: unknown }).message;
    if (typeof detailMessage === "string" && detailMessage.trim()) return detailMessage;
  }
  if (typeof message === "string" && message.trim()) return message;
  return `AI 请求失败（${status}）`;
}

async function responseError(response: Response): Promise<ApiError> {
  let body: unknown = null;
  try { body = await response.json(); } catch { /* 非 JSON 错误使用状态文案。 */ }
  return new ApiError(aiResponseErrorMessage(body, response.status), response.status);
}

export async function streamKnowledgeAi(
  request: KnowledgeAiRequest,
  onEvent: (event: KnowledgeAiEvent) => void,
  signal: AbortSignal,
): Promise<KnowledgeAiEvent> {
  const path = request.operation === "generate"
    ? "/notes/ai/generate"
    : `/notes/${request.noteId}/ai/${request.operation}`;
  const response = await authenticatedFetch(path, {
    method: "POST",
    body: request.operation === "generate"
      ? JSON.stringify({ topic: request.topic, instructions: request.instructions || null })
      : request.operation === "ask"
        ? JSON.stringify({ question: request.question, history: request.history })
        : undefined,
    signal,
  });

  if (!response.ok) throw await responseError(response);
  if (!response.body) throw new Error("浏览器未提供流式响应内容");

  for await (const event of readSseEvents(response.body)) {
    onEvent(event);
    if (["done", "blocked", "error"].includes(event.event)) return event;
  }
  throw new Error("AI 响应提前结束，请重试");
}

export function asKnowledgeAiDone(event: KnowledgeAiEvent): KnowledgeAiDone {
  return event.data as KnowledgeAiDone;
}
```

### 8.2 `services/ai-practice.service.ts`（全文）

```ts
import { ApiError, apiFetch, authenticatedFetch } from "@/lib/api/client";
import { readSseEvents } from "@/lib/api/sse";
import { aiResponseErrorMessage } from "@/services/knowledge-ai.service";
import type { KnowledgeAiEvent } from "@/types/knowledge-ai";
import type { PracticeAnswer, PracticeList, PracticeRecord } from "@/types/ai-practice";
import type { ApiResponse } from "@/types/api";

async function streamPractice(
  path: string,
  body: object,
  signal: AbortSignal,
  onEvent: (event: KnowledgeAiEvent) => void,
): Promise<KnowledgeAiEvent> {
  const response = await authenticatedFetch(path, { method: "POST", body: JSON.stringify(body), signal });
  if (!response.ok) {
    let error: unknown = null;
    try { error = await response.json(); } catch { /* 状态码仍可提示。 */ }
    throw new ApiError(aiResponseErrorMessage(error, response.status), response.status);
  }
  if (!response.body) throw new Error("浏览器未提供流式响应内容");
  for await (const event of readSseEvents(response.body)) {
    onEvent(event);
    if (["done", "blocked", "error"].includes(event.event)) return event;
  }
  throw new Error("AI 响应提前结束，请重试");
}

export const generatePractice = (noteId: number, count: 5 | 10 | 15, signal: AbortSignal, onEvent: (event: KnowledgeAiEvent) => void) =>
  streamPractice("/ai/practices/generate", { note_id: noteId, question_count: count }, signal, onEvent);

export const submitPractice = (body: { practice_ticket: string; answers: PracticeAnswer[] } | { submission_ticket: string }, signal: AbortSignal, onEvent: (event: KnowledgeAiEvent) => void) =>
  streamPractice("/ai/practices/submit", body, signal, onEvent);

export async function listPractices(page = 1, noteId?: number): Promise<PracticeList> {
  const query = new URLSearchParams({ page: String(page), page_size: "10" });
  if (noteId) query.set("note_id", String(noteId));
  return (await apiFetch<ApiResponse<PracticeList>>(`/ai/practices?${query}`)).data;
}

export async function getPractice(id: number): Promise<PracticeRecord> {
  return (await apiFetch<ApiResponse<PracticeRecord>>(`/ai/practices/${id}`)).data;
}

export async function deletePractice(id: number): Promise<void> {
  await apiFetch(`/ai/practices/${id}`, { method: "DELETE" });
}
```

### 8.3 认证方式结论

- 两类流式接口都通过 `authenticatedFetch` 发起，因此会带 `Authorization: Bearer <access_token>`，并复用 401 自动刷新逻辑。
- 不使用 `EventSource`（无法自定义请求头），而是 `fetch` + `ReadableStream` + `readSseEvents`。
- SSE 建立后不再做二次鉴权；若服务端在流式过程中撤销会话，当前实现无法中断已建立的流（服务端也只在建流前校验一次）。
- 迁移到 Cookie 时，只需在 `sendRequest` 中加 `credentials: "include"`；SSE 解析层无需改动。

---

## 9. 直接 `fetch` / `localStorage` / Axios 清单

### 9.1 所有直接调用 `fetch` 的位置

| 文件 | 行 | 用途 |
|---|---|---|
| `lib/api/client.ts` | 60 | `POST /auth/refresh`（裸 fetch，避免递归刷新） |
| `lib/api/client.ts` | 119 | 所有 JSON/SSE 请求的底层发送 |
| `app/health-check/page.tsx` | 16 | 健康检查 `GET /health`，不经过统一封装、不带 Token |

除此之外，服务层全部通过 `apiFetch` / `authenticatedFetch` 发请求，没有散落的 `fetch`。

### 9.2 所有直接读写 `localStorage` 的位置

认证相关（必须改造）：

| 文件 | 用途 |
|---|---|
| `lib/auth/token.ts` | `access_token` / `refresh_token` 的读写删（6 处） |

非认证相关（仅 UI 偏好，可保留）：

| 文件 | 用途 |
|---|---|
| `components/reminders/ReminderSettingsProvider.tsx` | 提醒设置（按 userId 分键） |
| `components/reminders/ReminderNotice.tsx` | 今日提醒是否已展示 |
| `components/focus/FocusRoom.tsx` | 专注音效场景与音量 |
| `hooks/useDashboardData.ts` | 仅注释提到 Token 存在 localStorage，实际通过 `getAccessToken()` |

直接调用 `getAccessToken()` 的位置：

| 文件 | 用途 |
|---|---|
| `lib/api/client.ts` | 注入 Authorization、判断是否发生并发刷新 |
| `components/layout/WorkspaceShell.tsx` | 路由守卫 |
| `hooks/useDashboardData.ts` | 首页数据加载前的登录检查 |

### 9.3 Axios 使用情况

- `package.json` 依赖与开发依赖中**没有 `axios`**。
- 全部 `.ts/.tsx` 源码中**没有 `import axios` / `axios.` 调用**。
- 结论：当前零 Axios；所有 HTTP 能力由原生 `fetch` + 自研封装提供。

---

## 10. 接口调用统计

### 10.1 后端接口规模（由后端路由实测）

| 类别 | 数量 | 说明 |
|---|---:|---|
| 路由总数 | 67 | 18 个路由文件 |
| JSON 接口 | 61 | 含 auth、users、plans、steps、tasks 等 |
| SSE 流式接口 | 6 | `knowledge_ai.py` 4 个 + `ai_practice.py` 2 个（generate、submit） |
| 公开接口 | 7 | `/`、`/health`、login、refresh、logout、`POST /users`、`GET /users` |

### 10.2 前端调用点统计

| 类别 | 数量 | 分布 |
|---|---:|---|
| `apiFetch` 调用点 | 48 | `tasks 10`、`steps 7`、`plans 7`、`knowledge 7`、`focus 5`、`auth 5`、`ai-practice 3`、`schedules 2`、`progress 1`、`statistics 1` |
| `authenticatedFetch` 调用点（SSE） | 2 | `knowledge-ai.service.ts::streamKnowledgeAi`（覆盖 4 个 SSE 接口）、`ai-practice.service.ts::streamPractice`（覆盖 2 个 SSE 接口） |
| 裸 `fetch` | 3 | 见 9.1 |
| Axios 调用 | 0 | — |

> 说明：`apiFetch` 统计包含 `auth.service.ts` 中 5 处（注册、登录、`/users/me`、logout、logout-all），不包含 `client.ts` 内部的 3 处定义/自调用。

---

## 11. Axios 迁移影响范围

### 11.1 若把 JSON 请求迁移到 Axios

必须处理：

1. **统一入口替换**：`apiFetch` / `authenticatedFetch` 的 50 个调用点都通过统一函数，理论上只需重写 `client.ts`；但 `authenticatedFetch` 返回原始 `Response` 的契约需要改为 Axios `Response`，会影响 SSE 两处调用。
2. **401 单飞刷新**：Axios 拦截器需重新实现 `refreshPromise` 单飞、`ACCESS_EXPIRED` 判定、重放原请求；否则并发请求会触发多次刷新并互相撤销 Refresh Token（现有轮换 + 重放检测会让后到的刷新失败）。
3. **登录表单编码**：`application/x-www-form-urlencoded` 需要 Axios 的 `URLSearchParams` 支持；默认 JSON 会直接 422。
4. **错误结构**：`ApiError.validationIssues` 来自 422 的 `data` 数组，需要在新封装里保留。
5. **SSE 无法用 Axios 浏览器端实现**：Axios 不暴露 `ReadableStream`，6 个 AI 流式接口必须继续用 `fetch`；最终会形成 Axios + fetch 双栈，增加维护成本。
6. **Cookie 模式**：Axios 需设置 `withCredentials: true`，并处理 CSRF 头；跨源时还要后端 CORS 精确允许来源。

结论：**不建议为 Auth V2.0 引入 Axios**。现有 `fetch` 封装已经覆盖 JSON、SSE、自动刷新、错误映射，改造成本低且风险可控。

### 11.2 若迁移到 HttpOnly Cookie（与 Axios 无关）

影响面：

- `lib/auth/token.ts` 全部废弃；`setTokenPair` / `getRefreshToken` / `removeTokenPair` 的 6 个调用点需改写。
- 登录/注册/刷新响应不再需要把 token 暴露给 JS；`LoginResponse` 类型需调整。
- `sendRequest` 增加 `credentials: "include"`；SSE 同样。
- 刷新接口改为「无 body，凭 Cookie」；`authenticatedFetch` 的 401 分支仍需保留。
- 跨源场景需要 `SameSite=None; Secure`，因此**必须 HTTPS**；本地开发需单独配置。
- 必须新增 CSRF 防护（双提交 Cookie 或自定义头 + 服务端校验）。
- 路由守卫不能再依赖 `getAccessToken()`，改为调用 `/users/me` 或专用 `/auth/session`。
- 多标签页登出同步需要 `storage` 事件或 BroadcastChannel（Cookie 模式下无法直接读 token，需靠接口探针）。

---

## 12. 前端风险与改造建议

### 12.1 高优先级

1. **Token 存 `localStorage`，XSS 可窃取 7 天 Refresh Token**
   - 位置：`lib/auth/token.ts`
   - 建议：Auth V2.0 改为 HttpOnly Cookie；若暂不迁移，至少缩短 Refresh 有效期并增加轮换重放撤销（后端已有）。

2. **路由守卫只判断 token 是否存在**
   - 位置：`components/layout/WorkspaceShell.tsx`
   - 影响：过期 token 仍进入工作区，页面级 401 处理不一致。
   - 建议：统一 AuthProvider，初始化时调用 `/users/me`（或 session 探针），失败即跳转。

3. **没有全局 401 处理**
   - 位置：`lib/api/client.ts`
   - 影响：刷新失败后仅清理 token，不跳转；各页面需自行处理。
   - 建议：在 `client.ts` 增加「刷新失败 → 清理 → 跳转 /login」的统一回调（注意避免在登录页循环跳转）。

### 12.2 中优先级

4. **登录/注册接口契约将变化**
   - 当前登录是 form-urlencoded + `OAuth2PasswordRequestForm`；邮箱验证码登录若改为 JSON，需要同步改 `loginUser` 与后端 Schema。
   - 注册当前无邮箱、无验证码；前端表单需新增邮箱、验证码、倒计时、错误次数提示。

5. **个人资料页能力缺失**
   - 无修改密码、换绑邮箱、头像上传、会话列表。
   - `User` 类型缺少 `email`、`avatar_url`、`email_verified_at`，需扩展。
   - `UsersProfile` 目前用昵称首字当头像，接入 `avatar_url` 后需处理加载失败回退。

6. **重复的登录检查逻辑**
   - `WorkspaceShell` 与 `useDashboardData` 各写一份；改造时容易漏改。
   - 建议抽成 `useRequireAuth` 或 AuthProvider。

7. **SSE 建立后无法被服务端即时中断**
   - 影响：踢下线/改密后，正在生成的 AI 流仍会继续返回。
   - 建议：服务端在流式循环中周期性校验会话（成本较高），或接受「流结束后下一次请求失效」的语义并写入文档。

### 12.3 低优先级

8. **`types/auth.ts` 重复声明 `LoginResponse`**：清理冗余。
9. **`apiFetch` 对所有请求设置 `Content-Type: application/json`**：GET 也带该头，虽无害但不规范；改为仅在有 body 时设置。
10. **`apiFetch` 直接 `response.json()`**：若后端返回 204 或空 body 会抛解析错误；当前受影响接口均返回 JSON，但新增接口需注意。
11. **健康检查页绕过统一封装**：`app/health-check/page.tsx` 直接 `fetch(/health)`，不参与刷新与错误规范；属调试页面，可保留但应标注。
12. **无请求超时/取消策略（JSON）**：SSE 已有 `AbortSignal`，普通 JSON 请求没有超时；弱网下可能长时间 pending。
13. **`NEXT_PUBLIC_API_BASE_URL` 是构建期变量**：生产切换域名需重新构建；若改为同源代理可移除该变量。
14. **没有前端认证测试**：`tests/` 仅覆盖 AI 练习与知识库，无登录、刷新、登出、401 跳转测试。

---

## 附录：`.env.local` 变量名（仅名称）

```text
NEXT_PUBLIC_API_BASE_URL
```

> 未输出任何具体值。Auth V2.0 若改为同源代理，可移除该变量；若保留跨源，需要补充 HTTPS 域名与 Cookie 相关配置（Cookie 由后端下发，前端通常无需新增环境变量）。

---

*本报告基于 2026-11-24 的实际前端源码生成；生产域名、HTTPS、反向代理等仓库外信息在后端审计报告中标注为 UNKNOWN。*
