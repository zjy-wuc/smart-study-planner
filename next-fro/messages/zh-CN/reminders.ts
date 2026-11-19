export const reminders = {
  title: "消息提醒",
  subtitle: "了解今日打卡情况，管理每日学习提醒",

  todayStatus: "今日学习状态",
  uncheckedTasks: (count: number) =>
    `您还有 ${count} 项任务未打卡`,

  noUnchecked: "今天没有待打卡的任务",
  noUncheckedDescription:
    "今天没有需要继续打卡的有效任务。",

  uncheckedDescription:
    "今天还有学习任务等待记录。",

  viewTodayTasks: "查看今日任务",
  dateLabel: "业务日期：",

  loading: "正在获取今日任务...",
  loadFailed: "获取今日任务失败",
  retry: "重新加载",
  refresh: "刷新今日任务",

  settingsTitle: "提醒设置",
  enabledLabel: "每日学习提醒",
  enabledDefault: "默认开启",
  timeLabel: "每日提醒时间",
  defaultTime: "22:00",
  timezone: "北京时间（UTC+8）",
settingsPending:
  "设置会自动保存。右上角自动提醒将在下一阶段接入。",

  browserOnly:
    "提醒仅在网页打开时生效，不保存通知历史。",
    settingsLoading: "正在读取提醒设置...",
settingsLoadFailed:
  "无法获取当前用户信息，请刷新页面重试。",
  notificationTitle: "今日学习提醒",
notificationClose: "关闭提醒",
notificationLater: "稍后处理",
};