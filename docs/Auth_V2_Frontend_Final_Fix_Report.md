# Auth V2.0 前端最终小范围整改报告

日期：2026-11-27。只修改前端认证链路、旧页面的宽泛 401 分支、相关测试和学习文档；未修改后端、数据库或接口协议。工作区原有未提交改动均保留。

## 修复与检查

| 项目 | 复现/检查 | 处理 |
| --- | --- | --- |
| 退出全部设备嵌套 Web Lock | 独占锁 Mock 中，过期 Access 触发内层刷新，修复前等待超时 | `withCurrentSessionLock()` 先在锁外请求 `/users/me`，允许必要的刷新；获锁后核对原 Epoch 与内存代际；锁内退出请求禁用隐式刷新 |
| 排队时换账号 | 修复前，账号 A 排队的退出会在账号 B 登录后继续执行 | 当前设备退出、全部设备退出均在入队前记录代际，获锁后重新检查；过时操作不发退出请求 |
| 错误密码 | 测试确认错误响应不清理会话 | 原有后端错误提示保留；只有退出成功才清本地状态 |
| 登录结果迟到 | 登录/注册返回结果原先没有可供页面核对的 Epoch | `rememberLogin()` 返回本次 Epoch；页面交给 `AuthContext` 前再次核对，过时结果停止导航 |
| 旧页面任意 401 跳登录 | 源码检索发现 12 个页面/Hook 文件中的宽泛判断 | 移除这些分支和无用导入；业务错误、网络错误继续由各页面原有提示显示；已确认失效由公共客户端与工作区守卫处理 |
| SSE 错误解析期间换账号 | 增加解析前后代际测试 | 解析 401 响应体之后、发起 Refresh 前再次核对 Epoch 和内存代际 |
| 残留 Authorization | 测试复现无当前 Token 时仍发送调用者传入的旧头 | Axios 与 SSE `fetch` 无当前 Token 时删除旧 `Authorization`；重试时仍设置当前有效 Token |
| 密码重置同步 | 后端仅清理被重置账号 Cookie；原页面依据邮箱清理内存 | 页面额外核对请求发起时的 Epoch，避免等待期间切换账号后清掉新账号；重置自己账号时仍清本地状态并广播退出 |
| 同代际迟到刷新广播 | 复核已有共享刷新版本与本地已清状态检查 | 现有测试覆盖晚到广播不能覆盖较新 Token；本轮无需修改 |

登录、注册、密码重置依赖明确目标身份；本轮新增的排队代际检查只用于依赖**当前账号**的两种退出操作。锁内若仍发生 Access 过期，退出请求返回错误，不再尝试递归刷新；用户可重试。

## 变更位置

- `next-fro/services/auth.service.ts`：`rememberLogin()`、`logoutUser()`、`logoutAllSessions()`、`withCurrentSessionLock()`。
- `next-fro/lib/api/client.ts`：Axios 请求拦截器、`authenticatedFetch()`。
- `next-fro/components/auth/LoginForm.tsx`、`next-fro/components/RegisterForm.tsx`：登录结果代际核对。
- `next-fro/app/(auth)/forgot-password/page.tsx`：重置密码后的本地会话核对。
- `next-fro/messages/zh-CN/auth.ts`：代际变化提示文案。
- 旧 401 分支清理：`components/tasks/TaskActionCard.tsx`、`PlanTasksPanel.tsx`、`components/plans/ActiveStepManager.tsx`、`PlanLifecyclePanel.tsx`、`PlanReadOnlyOverview.tsx`、`components/dashboard/TodayTaskList.tsx`、`CheckinHistory.tsx`、`hooks/useKnowledge.ts`、`useTodayTasks.ts`、`app/(workspace)/plans/[planId]/page.tsx`、其 `steps/page.tsx`、`app/(workspace)/history/page.tsx`。
- `next-fro/tests/auth-service.test.mjs`、`auth-client.test.mjs`：独占锁、账号切换、错误密码、请求头与 SSE 解析竞态回归。
- `docs/Auth_V2_Frontend_Core_Learning.md`：锁顺序、代际判断、错误处理说明和源码附录。

## 验证

| 验收项 | 实际结果 |
| --- | --- |
| `npx tsc --noEmit` | PASS |
| `npx eslint app components contexts hooks lib messages services --no-warn-ignored` | PASS，0 errors、0 warnings |
| `node --test tests/*.test.mjs` | PASS，56 项、0 失败；本轮较原 51 项新增 5 项 |
| `npm run build` | PASS，Next.js 16.4.2 生产构建完成 |
| 本轮修改范围的 `git diff --check` | PASS |
| 真实浏览器双标签页与后端 Cookie 轮换 | BLOCKED：检查时本机 3000/8000 端口无服务监听；Mock 不等同于真实环境验收 |

## 剩余边界

- 无后端与浏览器双标签页服务时，只能用 Mock 验证锁的顺序和错误分支，不能视作真实 Cookie 轮换验收。
- 锁外预检查后、锁内退出前仍可能再次自然过期；此时返回错误而不会嵌套刷新。
- 重置密码页面只在已知当前用户邮箱且 Epoch 不变时立即清本地状态；若 `AuthContext` 尚未恢复出当前用户，后续已撤销会话由公共 API 错误处理。该边界需真实浏览器联调。

完成本轮后停止新增认证功能，下一步进入 A5 前后端联合验收。
