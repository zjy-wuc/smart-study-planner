import type { MessageValue } from "../types";

export const statistics = {
  subtitle: "查看打卡记录、学习连续性和计划执行情况。",
  checkinTab: "打卡统计",
  consistencyTab: "计划坚持",
  focusTab: "专注统计",
  categoriesLabel: "统计分类",
  focusOverview: "专注数据概览",
  focusDuration: "有效专注时长",
  focusSessions: "专注参与次数",
  completedPomodoros: "完整番茄钟",
  focusTrend: "每日专注时长",
  focusTrendSubtitle: (days: MessageValue): string => `最近 ${days} 天，按专注开始日期统计`,
  focusMinutes: (minutes: MessageValue): string => `${minutes} 分钟`,
  focusHoursMinutes: (hours: MessageValue, minutes: MessageValue): string => `${hours} 小时 ${minutes} 分`,
  loadingFocus: "正在加载专注统计...",
  consistencyTitle: "计划执行情况",
  consistencySubtitle: "计划完成度和执行覆盖率会分别展示。",
  consistencyUnavailable: "计划级执行统计接口尚未提供。当前只展示真实的计划数量，执行天数、覆盖率和日期格将在后端聚合接口可用后接入。",
  activePlansMetric: "当前进行中计划",
  endedPlansMetric: "已结束计划",
  loading: "正在加载学习统计...",
  staleError: (error: MessageValue): string => `更新失败，当前显示上次的数据：${error}`,
  calendarStaleError: (error: MessageValue): string =>
    `日历更新失败，当前显示上次的数据：${error}`,
  calendarError: (error: MessageValue): string =>
    `日历加载失败：${error}`,
  loadingCalendar: "正在加载学习日历...",
  trendTitle: "每日打卡趋势",
  emptyTrend: "当前时间范围内暂无打卡记录。",
  trendAccessible: (days: MessageValue, total: MessageValue): string =>
    `最近 ${days} 天每日打卡趋势，共 ${total} 次；每日数据可在下方展开查看`,
  times: (count: MessageValue): string =>
    `${count} 次`,
  toggleRangeLabel: (days: MessageValue, nextDays: MessageValue): string =>
    `当前最近 ${days} 天，点击切换到最近 ${nextDays} 天`,
  dailyDetails: "查看每日详细数据",
  checkinCount: "打卡次数",
  totalCheckins: "累计打卡",
  last7Checkins: "最近 7 天打卡",
  last30Checkins: "最近 30 天打卡",
  activePlans: "执行中的计划",
  endedPlans: "已结束计划",
  summaryTitle: "学习数据概览",
  endedPlansHint: "含正常到期和提前结束的计划",
  streakTitle: "连续打卡",
  checkedInToday: "今天已打卡，连续记录已更新。",
  notCheckedInToday: "今天尚未打卡，可以在今天结束前继续打卡。",
  businessDayHint: "按北京时间自然日统计，每天成功打卡至少一次即可。",
  calendarTitle: " 我的学习日历",
  calendarMottoFirstLine: "把每一天的努力，",
  calendarMottoSecondLine: "留在日历里。",
  calendarSubtitle: "时间会记住你的每一次坚持。",
  currentStreak: "当前连续打卡",
  dayUnitSpaced: " 天",
  todayEncouragement: "今天也在向目标靠近",
  todayReminder: "今天也为自己留一点学习时间",
  calendarProgressMotto: "每一次打卡，都是前进的一步",
  calendarLabel: (year: MessageValue, month: MessageValue): string =>
    `${year}年${month}月学习日历`,
  calendarDayLabel: (month: MessageValue, day: MessageValue, todaySuffix: MessageValue, status: MessageValue): string =>
    `${month}月${day}日${todaySuffix}，${status}`,
  todaySuffix: "，今天",
  futureDate: "未来日期",
  noData: "暂无数据",
  checkins: (count: MessageValue): string =>
    `打卡 ${count} 次`,
  notCheckedIn: "未打卡",
  checkedIn: "已打卡",
  noDataLegend: "— 暂无数据",
  fetchFailed: "获取学习统计失败",
  trendSummary: (days: MessageValue, total: MessageValue): string =>
    `最近 ${days} 天，共 ${total} 次`,
  switchingRange: (days: MessageValue, previousDays: MessageValue): string =>
    `正在切换到最近 ${days} 天，暂时显示最近 ${previousDays} 天的数据。`,
  asOf: (date: MessageValue): string =>
    `统计截至北京时间 ${date}。 打卡数据以成功保存的学习记录为准。`,
  monthHeading: (year: MessageValue, month: MessageValue): string =>
    `${year} 年 ${month} 月`,
  todayDate: (month: MessageValue, day: MessageValue): string =>
    `今天 ${month}/${day}`,
  calendarRange: (firstAvailable: string | undefined): string =>
    `日历显示最近 30 天的打卡情况；${firstAvailable ? firstAvailable + " 之前" : "当前"}暂无日期明细。`,
};
