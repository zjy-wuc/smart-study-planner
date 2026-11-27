# Auth V2.0 前端测试报告

记录时间：2026-11-26。环境：Windows PowerShell，`D:\project\next-fro`，Next.js 16.4.2，Node 内建 test runner；当前工作区有未提交改动。本报告只标记实际运行的结果。

## 已执行

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| TypeScript | `npx tsc --noEmit` | PASS，退出码 0 |
| ESLint | `npx eslint app components contexts hooks lib messages services --no-warn-ignored` | PASS，退出码 0 |
| 前端测试 | `node --test tests/*.test.mjs` | PASS，39 tests，39 passed，0 failed，0 skipped |
| 生产构建 | `npm run build` | PASS，26 个路由生成；包含 `/forgot-password` |
| 补丁空白检查 | `git diff --check -- next-fro` | PASS，退出码 0；有现有 CRLF 转换提示 |

**新增测试实际覆盖：** 内存 Access 与旧键清理；五请求同页单飞；模拟双标签页串行刷新及临时 Access 传递；账号切换时新请求不继承旧刷新 Promise；旧登录代际拒收；无 Web Locks 明确失败；Axios Bearer/CSRF/活动头；422、密码错误、网络故障；`ACCESS_EXPIRED` 只刷新和重试一次；无递归刷新；`ACCOUNT_DISABLED` 403 清理；注册自动登录不额外登录；两种登录请求编码；退出当前设备仅在后端确认撤销后清状态。旧 AI/SSE、知识、今日任务展示测试也在 39 项中运行。

## 联调状态

| 场景 | 状态 | 证据或限制 |
| --- | --- | --- |
| 单标签页刷新与 Axios 请求 | PASS（自动化 Mock） | 请求、刷新、重试顺序由 adapter 测试验证；非真实 Cookie 轮换 |
| 双标签页并发刷新 | PASS（模拟） | 两个独立模块实例、模拟锁和 BroadcastChannel；非真实浏览器 |
| 登录、注册、验证码和设备接口 | PASS（接口封装单元测试，部分场景） | 验证调用路径、编码和状态条件；没有真实后端/邮件 |
| 浏览器刷新恢复、Cookie `Secure`/Origin/CORS | BLOCKED | 3000、8000 端口未监听；HTTP 探测超时 |
| 真实双标签页退出/切换账号/迟到 Set-Cookie | BLOCKED | 无可用后端和浏览器联调会话 |
| 真实账号管理：邮箱、密码、头像、设备分页及撤销 | BLOCKED | 未连接隔离数据库和邮件环境，不修改正式数据 |
| 学习计划、任务、知识、专注、AI SSE 实际 API 回归 | BLOCKED | 服务未运行；现有前端 Mock 测试通过，不能代替前后端联调 |
| 后端应用导入 | BLOCKED | `back/.venv/Scripts/python.exe` 在本环境无法创建进程 |

## 剩余风险与联合验收步骤

1. 在隔离环境启动 MySQL、FastAPI 与 Next.js，确认页面和 API 使用兼容的主机名。核对 `REFRESH_COOKIE_SECURE=True` 在所用 HTTPS/localhost 浏览器条件下的实际 Set-Cookie/回传行为；检查 Origin 与 CORS。不要用正式用户数据测试。
2. 使用隔离测试邮箱按注册 → 自动进入首页 → 刷新页面恢复 → 密码/验证码登录 → 修改密码/邮箱 → 设备撤销 → 当前/全部退出走一遍，记录 Network 状态码及 `detail.code`，不要保存 Token 或验证码。
3. 两个真实标签页同时制造 Access 过期，核对仅一次有效 Refresh 轮换；在另一标签页退出和切换账号，观察所有页面及迟到请求。无 Web Locks 浏览器会明确拒绝认证 Cookie 写操作，需产品决定兼容要求。
4. 从工作区抽测计划、任务、知识、专注和 AI SSE；重点核查旧页面中按任意 401 跳登录页的路径，不应把暂时网络故障误当退出。

**联合验收结论：** 静态与自动化回归通过；真实浏览器及后端数据链路尚未验证，暂不标记正式联合验收完成。
