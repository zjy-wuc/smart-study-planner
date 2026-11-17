import type { MessageValue } from "../types";

export const schedule = {
  safeRangeExceeded: "超出前端安全整数范围",
  dateTargetInvalid: (date: MessageValue): string =>
    `${date} 的目标必须是非负整数`,
  dateTargetTooLarge: (date: MessageValue): string =>
    `${date} 的目标超出前端安全整数范围`,
  notManual: "当前叶子不是手动安排模式",
  clearConfirm: "当前没有有效安排，保存会清空该叶子原有的草稿安排。确定继续吗？",
  saved: "草稿每日安排已保存",
  title: "每日手动安排",
  description: "自动重复和数量自动分配不需要填写这里。 手动安排可分多次保存；正式开始时再检查完整性。",
  loadingSteps: "正在读取学习步骤...",
  noManualLeaves: "当前没有需要手动安排的叶子节点。 若所有叶子都使用自动模式，可以直接开始计划。",
  selectLeaf: "选择学习项目",
  loading: "正在读取该叶子的每日安排...",
  emptyDay: "当天尚未安排任务。",
  contentPlaceholder: "填写当天任务内容",
  addDailyTask: "+ 当天再添加一条",
  quantityPlaceholder: "当天数量",
  numericHint: "每天必须恰好有一条数量安排， 全部日期的数量之和必须等于总目标， 才可以正式开始。",
  save: "保存当前叶子的全部安排",
  quantitySummary: (sum: MessageValue, target: MessageValue): string =>
    `当前填写总量：${sum} / 叶子总目标：${target}`,
};
