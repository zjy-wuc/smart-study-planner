# Auth V2.0 前端认证竞态专项审查与整改报告

## 2026-11-28 复核补充

下文 2026-11-27 的结果是当时的历史快照，测试数量和“12 处旧页面任意 401 跳转”不代表当前状态；旧页面的问题已在后续 `Auth_V2_Frontend_Final_Fix_Report.md` 整改。本次按当前工作区重新检查认证源码与回归测试，保留所有已有未提交改动。

| 检查项 | 当前结论与证据 |
| --- | --- |
| P0 Token 与 Epoch、请求发送前校验 | 已有修复；`token.ts` 绑定内存 Token 与 Epoch，`client.ts` 在 Axios 发送前和 SSE 发送前复核。`auth-v2.test.mjs` 与 `auth-client.test.mjs` 覆盖旧 Token、旧请求及跨账号重试。 |
| P1 广播乱序、刷新失败、锁晚于消息 | 已有修复；`coordinator.ts` 校验消息 Epoch 和刷新版本，刷新 Promise 只清理自身；现有测试覆盖迟到/重复广播、旧刷新失败、锁先于广播。 |
| P1 SSE 和异常边界 | 已有修复；旧流读取和事件交付复核代际，开始读流后不重放；测试覆盖旧事件、错误解析期间切换账号、残留 Authorization Header、超时后不确定的 Cookie 轮换。 |
| 登录恢复与 Cookie 写操作 | `AuthContext` 识别 `ACCOUNT_DISABLED`；登录、注册、刷新、重置密码及退出使用同名 Web Lock。退出操作在锁外预刷新、获锁后复核代际；现有测试覆盖嵌套锁和排队时换账号。 |
| 旧页面宽泛 401 | 2026-11-27 报告列出的旧页面已由后续专项整改处理；本次检索未再找到这些直接跳转分支。 |
| 新发现：管理页宽泛 401 | `AdminShell` 的 `/users/me` 失败分支把任何 401 直接当成退出。新增测试先复现失败，再移除该分支；非确认失效错误留在页面供重试，已确认失效仍由公共 `AuthContext` 导航。 |

本次实际改动：`next-fro/components/admin/AdminShell.tsx` 的身份校验错误分支；`next-fro/tests/admin.test.mjs` 新增 401 回归测试；本报告及 `Auth_V2_Frontend_Core_Learning.md` 同步说明。认证核心、后端、数据库和接口协议未修改。原先 P0/P1 的复现测试和修复已存在，本次没有重写或重复新增这些测试；新缺陷按“先失败、后修复”执行。

| 验收 | 本次实际结果 |
| --- | --- |
| `npx tsc --noEmit` | PASS |
| `npx eslint app components contexts hooks lib messages services types`、`npx eslint tests/admin.test.mjs` | PASS |
| `node --test tests/*.test.mjs` | PASS，60 项、0 失败；新增测试修复前失败、修复后通过 |
| `npm run build` | PASS，Next.js 16.4.2 |
| `npm run lint` | BLOCKED：ESLint 遍历现有 `.pytest_cache` 时遇到 `EPERM`；上述源码范围 ESLint 已通过 |
| `git diff --check`（整个仓库） | FAIL：已有未提交的 `back/app/config.py` 尾随空格及文件末空行；本次范围检查通过 |
| 真实浏览器双标签页与后端 Cookie 轮换 | BLOCKED：本次会话的浏览器访问受已保存权限限制，未执行；Mock 测试不等于浏览器联调 |

剩余风险：真实跨标签事件顺序、存储运行中失效和后端已轮换 Cookie 但前端未收到响应，仍需在获准的真实浏览器与后端环境验收。当前代码对此采用代际校验及不确定刷新拒绝自动重试；不能把这些 Mock 结果写成真实环境结论。

检查日期：2026-11-27。范围：`next-fro` 前端；未修改后端、数据库或认证接口。工作区原有未提交改动均保留。测试使用占位 Token 和模拟浏览器对象，不包含真实凭据。

## 结果概览

| 风险 | 严重程度 | 修复前复现 | 修复后 |
| --- | --- | --- | --- |
| 旧 Access Token 与新共享 Epoch 组合 | P0 | 是；切换 Epoch 后旧 Token 仍可被读取 | Token 绑定 Epoch，请求发送前双重核对；旧账号请求无法借新账号 Token 重试 |
| 旧 login/logout、重复消息改变新会话 | P1 | 是；旧 logout 和重复 login 都触发回调 | 所有消息核对 Epoch，同一 Epoch 只通知一次 |
| 迟到的旧刷新 Token 覆盖较新 Token | P1 | 是；两次刷新后晚到的第一次广播覆盖新值 | 广播附共享刷新版本，接收端只接受当前版本；清空会话后不能靠广播复活 |
| 旧刷新失败清除新账号状态 | P1 | 是；原错误路径无条件清 Token | 清除前同时核对原请求 Epoch 和所用 Token；旧 Promise 的 `finally` 仅清除自己 |
| SSE 在切换账号后继续写入页面 | P1 | 是；旧流下一块仍可读取 | 流读取前后核对代际，解码后交给组件前再核对；不重放已开始的流 |
| Web Lock 先于广播到达 | P1 | 是；第二标签页再次请求刷新 | 获锁后比较共享刷新版本，版本变化时拒绝第二次轮换 |
| 刷新超时后自动再试 | P1 | 是；可能向已轮换 Cookie 发送第二次刷新 | 不确定结果标记在当前 Epoch，后续自动刷新提示重新登录 |
| 恢复阶段收到 `ACCOUNT_DISABLED` | P1 | 源码检查：原逻辑只把 401 作为已确认失效 | 403 且错误码为 `ACCOUNT_DISABLED` 时进入未登录状态 |
| 没有 Web Locks | 环境限制 | 已有测试：拒绝刷新 | 保持拒绝所有通过 `withAuthLock` 的 Cookie 写操作 |
| 没有 BroadcastChannel | 环境限制 | 源码检查：缺少登录/退出通知兜底 | `storage` 事件同步 Epoch；不通过存储传递 Access Token |
| `localStorage` 访问异常 | 环境限制 | 源码检查：无法保证认证入口提前阻止写 Cookie | `withAuthLock` 先检查共享存储；请求读取失败即中止；恢复页显示临时错误 |

前四项和“旧流仍可读”“Web Lock 晚广播”“刷新超时”均先运行了失败的复现测试，再做修复。缓冲事件的二次校验和跨账号重试测试是在修复后补充的边界回归，不把它们声称为修复前的实测失败。

## 实际修改

| 文件 | 函数/位置 | 改动 |
| --- | --- | --- |
| `next-fro/lib/auth/token.ts` | `readAuthEpoch`、`getAccessToken`、`setAccessToken`、`acceptBroadcastToken`、`clearAccessToken` | Access 只在内存；增加所属 Epoch，拒绝旧 Epoch Token；清除后不接受迟到广播恢复 |
| `next-fro/lib/auth/coordinator.ts` | `refreshAccessToken`、`onAuthMessage`、`announceAuthChange`、`withAuthLock` | 消息核对与去重、storage 兜底、共享刷新版本、超时未知结果阻止自动重试、获锁后复核 |
| `next-fro/lib/api/client.ts` | Axios 请求/响应拦截器、`apiFetch`、`authenticatedFetch`、`guardSseResponse`、`assertSseSession` | 发送前冻结并核对 Epoch；旧错误不得清新状态；重试保留原 Epoch；SSE 读流及事件回调前核对 |
| `next-fro/services/auth.service.ts` | `rememberLogin` | 登录响应先公布新 Epoch，再将新 Access 绑定该 Epoch |
| `next-fro/contexts/AuthContext.tsx` | 恢复和订阅 Effects | 识别 `ACCOUNT_DISABLED`；共享存储失败时进入临时错误，避免未处理异常 |
| `next-fro/services/knowledge-ai.service.ts`、`next-fro/services/ai-practice.service.ts` | 两处 SSE 事件循环 | 每次交付事件前复核流所属会话 |
| `next-fro/tests/auth-v2.test.mjs`、`auth-client.test.mjs`、`auth-service.test.mjs`、`knowledge-ai.test.mjs`、`ai-practice.test.mjs` | 回归测试和必要的 Mock 接口 | 覆盖代际、消息乱序、锁顺序、刷新超时、Axios 跨账号重试、流式数据隔离；原有测试仍保留 |
| `docs/Auth_V2_Frontend_Core_Learning.md` | Token、刷新、跨标签时序和源码附录 | 与最终实现同步；解释新增边界和降级行为 |

## 认证路径复核

- `registerUser`、密码/邮箱登录、`resetPassword`、`logoutUser`、`logoutAllSessions` 及 `/auth/refresh` 均通过同名 Web Lock；`rememberLogin` 在锁内变更 Epoch 与内存 Access。无 Web Locks 时拒绝上述 Cookie 写操作。
- `changePassword`、`changeEmail`、撤销指定/其他设备走普通授权 API；当前后端路由未见这些响应设置 Refresh Cookie。若后端以后改为轮换 Cookie，需把相应入口纳入同一锁。
- SSE 仅在收到明确的预读 `401 + ACCESS_EXPIRED` 时刷新并重新发送；开始读流后不会重放。退出或换账号时旧流不能继续把事件交给页面；底层网络在等待下一块数据时可能仍存活片刻。
- 检索到仍按任意 401 导航登录页的旧调用点：`components/tasks/TaskActionCard.tsx`、`PlanTasksPanel.tsx`、`components/plans/ActiveStepManager.tsx`、`PlanLifecyclePanel.tsx`、`PlanReadOnlyOverview.tsx`、`components/dashboard/TodayTaskList.tsx`、`CheckinHistory.tsx`、`hooks/useKnowledge.ts`、`useTodayTasks.ts`、`app/(workspace)/plans/[planId]/page.tsx`、其 `steps/page.tsx`、`app/(workspace)/history/page.tsx`。本次未改这些页面；它们仍可能把业务性 401 当成会话失效。工作区公共守卫由 `AuthContext` 负责已确认的失效状态。
- 统一 `ApiError` 只提取后端 `detail`、422 字段错误与 HTTP 状态，未把真实 Token 写入日志。若后端将堆栈作为公开 `detail.message` 返回，前端会照常展示；需要后端保证公开错误内容安全。

## 验证结果

| 命令/场景 | 实际结果 |
| --- | --- |
| `npx tsc --noEmit` | PASS |
| `npx eslint app components contexts hooks lib messages services --no-warn-ignored` | PASS |
| `node --test tests/*.test.mjs` | PASS，51 项，0 失败（原基线 39 项） |
| `npm run build` | PASS，Next.js 16.4.2 生产构建完成 |
| `git diff --check`（整个工作区） | FAIL：原有未提交后端文件及 `docs/开发日志/新功能实现逻辑.md` 有尾随空格/文件末空行；本轮未触碰这些内容 |
| 真正浏览器双标签页 + 后端 Cookie 轮换 | BLOCKED：检查时本机 3000/8000 端口没有服务监听；Mock 结果不等同真实浏览器验收 |

## 未验证事项与剩余风险

1. 真实浏览器中 Web Locks、BroadcastChannel、Cookie 的事件顺序，以及登录/退出同时发生的跨标签体验，仍需双标签页联调。
2. `localStorage` 若恰好在后端已经设置 Cookie **之后**才写入失败，前端无法回滚浏览器 Cookie；本次在请求前做了可用性检查，仍无法消除运行中存储故障。
3. 广播不可用时只通过 `storage` 同步登录/退出，不能传 Access；旧标签页需要恢复认证。长期没有消息且旧 Token 仍在时，前端可能给用户显示可重试错误。没有 Web Locks 的浏览器会被安全策略挡在认证操作外。
4. 刷新网络超时/取消时，前端无法证明后端是否轮换；当前代际禁止自动再试，用户需重新登录。普通业务 POST 超时也不自动重放，但 UI 应避免暗示“必定未执行”。
5. 旧页面对任意 401 的直接跳转尚未统一；应另开小范围任务，以后端明确错误码替代宽泛判断。
6. `git diff --check` 的全仓错误位于本轮范围外；保持用户原有未提交代码原样。

**结论：** 已在源码和 Mock 回归层面封住可复现的跨账号 Token/请求/SSE 竞态；正式验收还需要真实浏览器双标签页与后端 Cookie 轮换测试。
