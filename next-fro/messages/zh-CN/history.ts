import type { MessageValue } from "../types";

export function historyRangeSummary(days: number, records: number): string {
  return `${days} 天有打卡 · 共 ${records} 次`;
}

export const history = {
  dateHeading: (month: MessageValue, day: MessageValue, weekday: MessageValue, todaySuffix: MessageValue): string =>
    `${month}月${day}日 · 周${weekday}${todaySuffix}`,
  todaySuffix: " · 今天",
  incompleteData: "数据未完整加载",
  dayCounts: (total: MessageValue, streak: MessageValue): string =>
    `累计 ${total} 天 · 连续 ${streak} 天`,
  subtitle: "记录每一次认真学习的日子",
  refresh: "刷新记录",
  loading: "正在整理打卡记录，任务较多时需要一些时间…",
  loadProgress: (done: MessageValue, total: MessageValue): string => `已读取 ${done} / ${total} 项`,
  partialFailure: "部分数据加载失败，记录可能不完整，受影响的计划不显示统计。",
  recordsTitle: "打卡记录",
  recordsSubtitle: "每一次努力，都值得被记录",
  rangeLabel: "打卡记录时间范围",
  partialRetry: "部分数据未加载，请重试",
  emptyRange: "这个时间范围还没有打卡记录",
  plansTitle: "计划坚持情况",
  plansSubtitle: "每个学习方向的点滴积累",
  streakExplanation: "同一天打卡多次只算一天；今天未打卡时，连续天数从昨天计算。",
  expandSteps: "展开查看学习步骤",
  totalDays: "累计天数",
  streakDays: "连续天数",
  emptyPlanSteps: "此计划暂无步骤",
  dataScope: "按北京时间的实际打卡日期统计；当前展示可查询的有效计划、步骤和任务记录。",
  loadFailed: "历史记录加载失败",
  collapse: "收起历史",
  view: "查看历史",
  loadingCompact: "正在加载历史…",
  emptyRecords: "暂无打卡记录",
  todayDescription: "查看今日任务的打卡记录",
  emptyToday: "今天暂无任务记录",
  fetching: "正在获取历史...",
  collapseFull: "收起打卡历史",
  viewFull: "查看打卡历史",
  loadingFull: "正在加载历史...",
  recordedAt: (time: MessageValue): string =>
    `记录时间：${time}`,
  checkinCount: (count: MessageValue): string => `${count} 次打卡`,
  collapseRetry: (error: MessageValue): string => `${error}，请收起后重试。`,
};
