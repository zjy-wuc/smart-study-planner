# 前端文案维护说明

页面负责布局与交互，`messages` 目录负责固定文字。当前仍显示中文，尚未添加语言切换按钮或英文翻译。

## 目录与职责

```text
messages/
├── index.ts          # 页面统一入口：messages、locale 和 Messages 类型
├── types.ts          # 动态文案参数类型
└── zh-CN/
    ├── index.ts      # 汇总中文文案
    ├── common.ts     # 公共操作、系统名称、单位、星期
    ├── navigation.ts # 侧边栏、导航、搜索
    ├── auth.ts       # 登录、注册
    ├── profile.ts    # 个人中心
    ├── dashboard.ts  # 首页工作台
    ├── plans.ts      # 计划创建、修改、启动、结束、删除
    ├── steps.ts      # 步骤树、执行规则、运行中步骤
    ├── schedule.ts   # 草稿每日安排
    ├── tasks.ts      # 今日任务、打卡、顺延、未来任务修改
    ├── history.ts    # 打卡历史
    ├── progress.ts   # 完成进度展示
    ├── statistics.ts # 统计、趋势图、日历
    ├── validation.ts # 前端校验和接口格式错误提示
    └── health.ts     # 后端连接检查页面
```

本次整理后共保留 **448 项文案，分为 14 类**。标题、按钮、占位符、确认框、错误兜底、无障碍标签及页面元信息均使用统一入口。

## 修改一句话

例如，将打卡成功后的鼓励文字换成另一句话，只需修改 `zh-CN/tasks.ts`：

```ts
encouragement: "坚持就是胜利",
```

首页、今日任务等引用它的位置会一起更新：

```tsx
import { messages } from "@/messages";

<span>{messages.tasks.encouragement}</span>
<button>{messages.tasks.checkin}</button>
```

不要在页面中重新写同一段中文，也不要根据翻译后的显示文字决定业务状态。业务判断继续使用接口枚举，例如 `task.status === "COMPLETED"`。

登录页原有的成功提示比较已替换为同一个文案引用，原交互保持不变。将来实现运行时切换语言时，应再将这种提示状态改为稳定标识，以免语言变化影响已有提示的判断。

## 带数字、日期、名称的句子

整句话放在文案函数中，不要在页面里拼接几个翻译片段：

```tsx
<p>{messages.tasks.quantitySummary(task.actual_quantity, target)}</p>
<p>{messages.statistics.trendSummary(days, total)}</p>
```

对应中文定义：

```ts
quantitySummary: (actual: MessageValue, target: MessageValue): string =>
  `累计完成 ${actual} / 目标 ${target}`,
```

英文可以重新安排语序，并在文案函数中处理单复数，页面不必随之改动。参数以普通文本渲染，未使用 HTML 注入。

带独立字体样式的数值与单位仍分别渲染，例如统计卡片的大号数字和小号“次”；单位也已放入文案文件。

## 以后增加英文

1. 参照 `zh-CN/` 新建 `en-US/`，保持相同的业务分组、键名和函数参数。
2. 英文汇总对象用 `satisfies Messages` 检查，遗漏键或函数签名不兼容时会产生类型错误。
3. 在统一入口选择英文文案，同时将展示语言 `locale` 改为 `en-US`。页面中的 `messages.tasks.checkin` 等引用不用调整。
4. 如果需要用户实时切换语言，再统一接入语言上下文、持久化偏好和服务端初始语言；仅修改当前常量不会自动实现实时切换。

英文汇总文件的结构示例：

```ts
import type { Messages } from "../index";
// 分别导入英文 common、navigation、auth 等全部业务对象。

export const enUS = {
  common,
  navigation,
  auth,
  // 其余业务对象必须完整提供。
} satisfies Messages;
```

这是结构示意，不能省略其余分组直接运行。类型导入不会产生运行时循环依赖。

HTML 的 `lang` 与统计数字的 `toLocaleString` 已使用统一 `locale`。**北京时间业务日规则保持原样**，展示语言不应改变打卡归属日期。正式接入英文时还需检查日期格式、长文案布局和单复数。

## 哪些文字不会自动翻译

- 用户填写的计划名称、步骤名称、任务内容、昵称：属于用户数据，原样展示。
- 后端直接返回的错误详情：保留服务端原文，本次只集中前端兜底提示。完整英文体验需要后续约定稳定错误码或后端多语言机制。
- API 路径、字段名、状态枚举、存储键、时区规则：属于程序契约，不是翻译文案。
- 代码注释：留在实现文件中，帮助阅读代码。

## 本次验证

- `npx tsc --noEmit --incremental false`：通过。
- `npm run build`：通过，14 个静态生成条目完成，全部现有路由正常完成构建。
- 自动对照 407 项原始文案及 6 组动态句子、确认框示例：通过。
- 对 39 个修改文件进行语法树扫描：没有剩余中文固定文字，注释不计入。
- 新文案目录 ESLint：无错误、无警告。
- 修改前后 ESLint 对比：均为 5 个错误、3 个警告；各文件诊断规则与内容一致，没有新增问题。

原有 lint 错误为 `WorkspaceShell`、`ActiveStepManager`、`DraftScheduleEditor`、`PlanTasksPanel`、`TaskActionCard` 中的 Effect 同步更新状态；警告为 `DraftScheduleEditor` 的 Effect 依赖和任务服务的两个未使用类型导入。本次没有调整这些交互逻辑。

未修改后端、CSS、API 请求参数或任务业务规则。验证范围是文案对照、静态检查及生产构建，没有重新执行登录、打卡、顺延等浏览器业务回归。

## 已接入文案入口的现有文件

- [命名空间接入：next-fro/app/(workspace)/history/page.tsx](D:/project/next-fro/app/(workspace)/history/page.tsx)
- [命名空间接入：next-fro/app/(workspace)/layout.tsx](D:/project/next-fro/app/(workspace)/layout.tsx)
- [命名空间接入：next-fro/app/(workspace)/plans/[planId]/page.tsx](D:/project/next-fro/app/(workspace)/plans/[planId]/page.tsx)
- [命名空间接入：next-fro/app/(workspace)/plans/new/page.tsx](D:/project/next-fro/app/(workspace)/plans/new/page.tsx)
- [命名空间接入：next-fro/app/(workspace)/plans/page.tsx](D:/project/next-fro/app/(workspace)/plans/page.tsx)
- [命名空间接入：next-fro/app/(workspace)/statistics/page.tsx](D:/project/next-fro/app/(workspace)/statistics/page.tsx)
- [命名空间接入：next-fro/app/(workspace)/task/today/page.tsx](D:/project/next-fro/app/(workspace)/task/today/page.tsx)
- [命名空间接入：next-fro/app/health-check/page.tsx](D:/project/next-fro/app/health-check/page.tsx)
- [命名空间接入：next-fro/app/layout.tsx](D:/project/next-fro/app/layout.tsx)
- [命名空间接入：next-fro/components/RegisterForm.tsx](D:/project/next-fro/components/RegisterForm.tsx)
- [命名空间接入：next-fro/components/auth/LoginForm.tsx](D:/project/next-fro/components/auth/LoginForm.tsx)
- [命名空间接入：next-fro/components/auth/UsersProfile.tsx](D:/project/next-fro/components/auth/UsersProfile.tsx)
- [命名空间接入：next-fro/components/dashboard/CheckinHistory.tsx](D:/project/next-fro/components/dashboard/CheckinHistory.tsx)
- [命名空间接入：next-fro/components/dashboard/Dashboard.tsx](D:/project/next-fro/components/dashboard/Dashboard.tsx)
- [命名空间接入：next-fro/components/dashboard/PlanCard.tsx](D:/project/next-fro/components/dashboard/PlanCard.tsx)
- [命名空间接入：next-fro/components/dashboard/StepPreview.tsx](D:/project/next-fro/components/dashboard/StepPreview.tsx)
- [命名空间接入：next-fro/components/dashboard/TodayTaskList.tsx](D:/project/next-fro/components/dashboard/TodayTaskList.tsx)
- [命名空间接入：next-fro/components/layout/WorkspaceShell.tsx](D:/project/next-fro/components/layout/WorkspaceShell.tsx)
- [命名空间接入：next-fro/components/plans/ActiveStepManager.tsx](D:/project/next-fro/components/plans/ActiveStepManager.tsx)
- [命名空间接入：next-fro/components/plans/DraftScheduleEditor.tsx](D:/project/next-fro/components/plans/DraftScheduleEditor.tsx)
- [命名空间接入：next-fro/components/plans/PlanForm.tsx](D:/project/next-fro/components/plans/PlanForm.tsx)
- [命名空间接入：next-fro/components/plans/PlanLifecyclePanel.tsx](D:/project/next-fro/components/plans/PlanLifecyclePanel.tsx)
- [命名空间接入：next-fro/components/plans/StepRuleFields.tsx](D:/project/next-fro/components/plans/StepRuleFields.tsx)
- [命名空间接入：next-fro/components/plans/StepTreeEditor.tsx](D:/project/next-fro/components/plans/StepTreeEditor.tsx)
- [命名空间接入：next-fro/components/statistics/CheckinTrend.tsx](D:/project/next-fro/components/statistics/CheckinTrend.tsx)
- [命名空间接入：next-fro/components/statistics/StatisticsSummary.tsx](D:/project/next-fro/components/statistics/StatisticsSummary.tsx)
- [命名空间接入：next-fro/components/statistics/StreakCard.tsx](D:/project/next-fro/components/statistics/StreakCard.tsx)
- [命名空间接入：next-fro/components/statistics/StudyCalendar.tsx](D:/project/next-fro/components/statistics/StudyCalendar.tsx)
- [命名空间接入：next-fro/components/tasks/PlanTasksPanel.tsx](D:/project/next-fro/components/tasks/PlanTasksPanel.tsx)
- [命名空间接入：next-fro/components/tasks/TaskActionCard.tsx](D:/project/next-fro/components/tasks/TaskActionCard.tsx)
- [命名空间接入：next-fro/hooks/useDashboardData.ts](D:/project/next-fro/hooks/useDashboardData.ts)
- [命名空间接入：next-fro/hooks/useStatistics.ts](D:/project/next-fro/hooks/useStatistics.ts)
- [命名空间接入：next-fro/hooks/useTodayTasks.ts](D:/project/next-fro/hooks/useTodayTasks.ts)
- [命名空间接入：next-fro/lib/api/client.ts](D:/project/next-fro/lib/api/client.ts)
- [命名空间接入：next-fro/lib/plans/date-range.ts](D:/project/next-fro/lib/plans/date-range.ts)
- [命名空间接入：next-fro/lib/plans/step-rule.ts](D:/project/next-fro/lib/plans/step-rule.ts)
- [命名空间接入：next-fro/services/schedules.service.ts](D:/project/next-fro/services/schedules.service.ts)
- [命名空间接入：next-fro/services/statistics.service.ts](D:/project/next-fro/services/statistics.service.ts)
- [命名空间接入：next-fro/services/tasks.service.ts](D:/project/next-fro/services/tasks.service.ts)
