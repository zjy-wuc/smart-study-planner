# A5 管理员前端开发报告

日期：2026-11-28

## 实现范围

| 页面 | 实现内容 |
| --- | --- |
| `/admin` | 平台指标、近 7 天趋势、计划状态分布、快捷入口、30 秒可见时轮询 |
| `/admin/users` | 服务端搜索、状态筛选、分页、详情抽屉、封禁/解封/撤销会话确认弹窗 |
| `/admin/ai` | AI 指标、额度、趋势与分布、动态配置弹窗、只读安全策略、15 秒可见时轮询 |
| `/admin/audit` | 操作筛选、服务端分页、审计详情及字段差异 |

独立 `AdminShell` 仅在当前用户向服务端确认 `ADMIN` 身份后渲染页面。普通用户看到 403；`ADMIN_REQUIRED` 使管理页卸载并回到学习空间，不注销正常会话。普通学习空间只向管理员显示入口。沿用 Auth V2 的 `apiFetch`、Access Token 刷新、Cookie 与 CSRF 处理，没有建立第二套认证逻辑。

## 文件

- 路由：`app/admin/layout.tsx`、`app/admin/page.tsx`、`app/admin/users/page.tsx`、`app/admin/ai/page.tsx`、`app/admin/audit/page.tsx`
- 页面与布局：`components/admin/AdminShell.tsx`、`AdminDashboard.tsx`、`AdminUsers.tsx`、`AdminAI.tsx`、`AdminAudit.tsx`
- 样式：`components/css/Admin.css`、`components/css/WorkspaceRefresh.css`
- 数据与状态：`services/admin.service.ts`、`types/admin.ts`、`hooks/useAdminPoll.ts`、`lib/admin/audit.ts`
- 文案：`messages/zh-CN/admin.ts`、`messages/zh-CN/index.ts`
- 认证入口和根布局：`components/layout/WorkspaceShell.tsx`、`types/auth.ts`、`app/layout.tsx`
- 测试：`tests/admin.test.mjs`

已存在的其他未提交修改保持原状；未修改后端、数据库或 `.env`，未提交和推送 Git。

## 接口与关键设计

前端封装与后端实际路由核对了 10 个接口：`GET /admin/dashboard`、`GET /admin/users`、`GET /admin/users/{id}`、`POST /admin/users/{id}/ban`、`POST /admin/users/{id}/unban`、`POST /admin/users/{id}/revoke-sessions`、`GET /admin/ai/statistics`、`GET /admin/ai/config`、`PATCH /admin/ai/config`、`GET /admin/audit-logs`。

用户列表的邮箱搜索只驻留页面内存，不写入 URL。敏感操作原因必填；AI 配置仅提交实际变化的字段，硬上限读取接口返回值。统计轮询在页面隐藏时停止，忽略过时响应；AI 配置轮询与编辑表单分离。审计对比区分字段缺失、`null`、`false` 和 `0`。用户业务时间按后端的 `+08:00` 解释，审计 UTC 时间转换为北京时间。

## 实际验证

| 检查 | 结果 |
| --- | --- |
| `npx tsc --noEmit` | 通过 |
| `npx eslint app components contexts hooks lib messages services types` | 通过 |
| `node --test tests/*.test.mjs` | 59 passed，0 failed；其中新增 A5 测试 3 项 |
| `npm run build` | 通过，四个管理路由生成成功 |
| `git diff --check -- next-fro` | 通过 |
| 真实管理员 API/账号操作联调 | 未执行；未提供隔离管理员测试身份，不能对正式用户执行封禁等操作 |
| 浏览器截图与视觉验收 | 未执行；浏览器工具的已保存权限策略拒绝访问 `http://localhost:3000`，未绕过限制 |

直接执行 `npm run lint` 会因 `next-fro/.pytest_cache` 目录无读取权限而中断。显式扫描前端源码通过；若包含旧 `tests/`，现存 8 处 Lint 错误，涉及 7 个旧测试文件的 `@next/next/no-assign-module-variable` 和 `auth-v2.test.mjs` 的 `@typescript-eslint/no-this-alias`，本次没有改动这些文件。

第一次构建因 Google Fonts 网络下载失败；在允许访问字体资源后，首次重跑完成编译，但 Next.js 16.4.2 的安全提示令命令退出；再次运行完整构建成功。当前依赖仍有 Next.js 安全升级建议。本轮未改依赖，之前独立安全升级工作区不在本次 A5 修改范围。

## 未验证与风险

1. 管理员、普通用户、降权后的真实浏览器流程及四个页面的实际截图尚待浏览器权限开放后验收。
2. 封禁、解封、强制退出、AI 配置写入仅完成代码和无副作用的自动化检查；需在隔离环境使用测试账号联调。
3. A4 后端 AI 运行配置仍在验收，实时额度和服务状态需要后端稳定版本实测。前端没有展示 Redis 健康、模型可用性或未接入的指标。
4. `npm run lint` 的目录权限及旧测试规则错误需要单独处理。
5. Next.js 16.4.2 的安全告警需在独立升级工作区审查并合并，A5 本身未处理依赖。

结论：A5 前端代码闭环、类型、源码 Lint、自动化测试和生产构建已完成；真实管理员联调与视觉验收尚未完成，不能视为最终验收通过。
