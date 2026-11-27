# Auth V2.0 前端实现报告

记录时间：2026-11-26。源码基准为 `D:\project` 工作区 Git HEAD `2d1e29c` 加本次未提交的前端改动。本次只处理前端；仓库在执行前已有其他未提交的前端、后端和文档改动，均未清理或覆盖。

## 实现范围

| 模块 | 实际实现 |
| --- | --- |
| 请求基础设施 | `lib/api/client.ts` 通过 Axios 统一普通 JSON 请求；独立刷新客户端避免拦截器递归；保留 `apiFetch<T>` 业务签名与 `authenticatedFetch` SSE 入口。解析后端字符串、对象错误和 FastAPI 422 数组。 |
| Token 与 Cookie | Access Token 只放当前标签页模块内存；清除旧版 localStorage 两个 Token 键；Refresh Token 只由浏览器 HttpOnly Cookie 管理。 |
| 刷新并发 | 同页 Promise 单飞，多页 Web Locks 排队，拿锁后复核 Token/认证代际；明确 `ACCESS_EXPIRED` 时单次重试。账号或代际变化拒收旧响应。 |
| 全局状态 | 根 Layout 注入 `AuthProvider`；页面刷新时 `/auth/refresh` 后查询 `/users/me`；区分恢复中、已登录、未登录、暂时失败。工作区只在已登录时渲染。 |
| 账号页面 | 登录支持用户名密码、邮箱密码和邮箱验证码；注册验证码成功后直接使用注册响应自动登录；增加忘记密码；个人中心支持昵称、头像、密码、邮箱和设备会话管理。 |
| 旧业务 | 保持计划等 Service 的 `apiFetch` 调用入口；AI SSE 使用共用刷新协调器，在流开始前处理明确过期响应。 |
| 文案与样式 | 新增样式保存在 `components/css/`；新增文案在 `messages/zh-CN/`。登录与注册延续原有视觉风格。 |

## 文件清单

**新增：** `next-fro/lib/auth/coordinator.ts`、`next-fro/contexts/AuthContext.tsx`、`next-fro/app/(auth)/forgot-password/page.tsx`、`next-fro/components/css/AuthFields.css`、`next-fro/components/css/ProfileAuth.css`、`next-fro/tests/auth-v2.test.mjs`、`next-fro/tests/auth-client.test.mjs`、`next-fro/tests/auth-service.test.mjs`，以及本次三份 `docs/Auth_V2_Frontend_*.md`。

**修改：** `next-fro/lib/auth/token.ts`、`lib/api/client.ts`、`types/auth.ts`、`services/auth.service.ts`、`contexts` 使用方 `app/layout.tsx`、`components/layout/WorkspaceShell.tsx`、`hooks/useDashboardData.ts`；登录、注册和个人中心组件；`messages/zh-CN/auth.ts`、`profile.ts`；`tests/knowledge-ai.test.mjs`；`package.json` 与 `package-lock.json`。本地 `next-fro/.env.local` 仅把公开的 API 地址从 `127.0.0.1:8000` 改为 `localhost:8000`，与当前 `localhost:3000` 页面同主机，以便 Cookie 联调；该文件被 Git 忽略，未读取或输出其他配置值。

**删除：** 无。`git diff --stat` 中还有执行前已存在的其他前端改动，不能全部归因于本次认证开发。

## API 契约与关键决定

- `POST /auth/login` 用表单编码，用户名字段也接受邮箱；`POST /auth/login/email`、`POST /users` 等用 JSON。注册与登录返回 `data.access_token` 和 `data.user`，浏览器接收 Refresh Cookie。
- `POST /auth/refresh` 使用独立 Axios 实例、`withCredentials` 和 `X-CSRF-Protection: 1`；只由协调器调用。
- 普通认证失败只在后端明确返回 `SESSION_REVOKED`、`SESSION_EXPIRED`、`INVALID_TOKEN`、`REFRESH_INVALID` 或 `ACCOUNT_DISABLED` 等码时清理本地认证。`ACCOUNT_DISABLED` 的实际 HTTP 状态是 403，已单独处理。
- 登录、注册、刷新、重置密码、退出等 Cookie 写操作使用同一个 Web Lock。无 Web Locks 时拒绝执行并给出明确错误；暂未设计跨浏览器兼容方案。
- 跨标签页只同步临时 Access Token 和不含凭据的 epoch；不会持久化 Access/Refresh。`BroadcastChannel` 的实际多页行为仍需浏览器联调。
- 当前设备退出必须收到服务端 `session_revoked: true` 才清本地状态；若服务端只清 Cookie 而未确认撤销，页面显示异常信息，避免误称退出成功。
- 头像使用后端提供的 URL；登录设备列表按后端分页查询。新增样式沿用现有蓝白主题。
- 只新增 Axios 这一项运行时依赖，未增加状态管理库，未改动后端 SQL、数据库和学习业务规则。

## 与原计划的差异及未完成验收

原交接材料列出的技术结构以现有源码为准调整：项目的普通业务 Service 已统一调用 `apiFetch`，因此迁移重点是替换内部实现，业务层没有整体重写；路由守卫复用 `WorkspaceShell`，未另建空壳 `AuthGuard.tsx`。SSE 保留原有流解析器。旧页面仍有少量针对 401 的单独跳转判断，尚未完全统一为 Context 驱动；这属于后续审查重点。

本地没有运行的前后端服务，`localhost:3000` 与 `localhost:8000` 检查超时；后端 `.venv` 的 Python 进程在本环境无法创建。故本次无法声称已完成真实注册、邮件验证码、MySQL、Refresh Cookie 轮换、双浏览器标签页或头像上传联调。未调用真实邮件或 AI 服务，未改数据库数据。实际执行的自动化结果见测试报告。

**结论：** 前端代码、类型检查、静态检查、单元回归与生产构建可交付审查；正式联合验收尚需在可启动的隔离后端和真实浏览器中完成，特别是 Cookie 的 `Secure`/Origin/CORS 策略、Web Locks 多标签页轮换与账号管理全流程。
