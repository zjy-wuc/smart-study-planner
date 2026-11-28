import type { MessageValue } from "../types";

export const dashboard = {
  greeting: "今天，也向目标靠近一点。",
  welcomeDescription: "从一件小事开始，把学习慢慢变成习惯。",
  title: "首页工作台",
  subtitle: "学习计划与每日执行情况",
  todaySubtitle: "从今天的安排开始",
  tasksError: (error: MessageValue): string =>
    `今日任务加载失败：${error}`,
  plansSubtitle: "查看计划与完成进度",
  loadingPlans: "正在获取计划...",
  plansError: (error: MessageValue): string =>
    `计划加载失败：${error}`,
  noPlans: "还没有学习计划",
  stepsTitle: "学习步骤预览",
  stepsSubtitle: "按计划查看步骤层级",
  loadingSteps: "正在准备步骤预览...",
  stepsUnavailable: "当前无法加载计划步骤",
  pendingCount: (count: MessageValue): string => `${count} 项待完成`,
  activeCount: (count: MessageValue): string => `${count} 个进行中`,
};
