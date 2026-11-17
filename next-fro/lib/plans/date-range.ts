import { messages } from "@/messages";

const DAY_MS = 24 * 60 * 60 * 1000;


// 将 YYYY-MM-DD 转为 UTC 日期
function parseDate(value: string): Date {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);

  if (!match) {
    throw new Error(messages.validation.dateFormat);
  }

  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);

  const date = new Date(Date.UTC(
    year,
    month - 1,
    day,
  ));

  if (
    date.getUTCFullYear() !== year ||
    date.getUTCMonth() + 1 !== month ||
    date.getUTCDate() !== day
  ) {
    throw new Error(messages.validation.invalidPlanDate);
  }

  return date;
}


// 首尾日期都包含在内
export function listPlanDates(
  startDate: string,
  endDate: string,
): string[] {
  const start = parseDate(startDate);
  const end = parseDate(endDate);

  if (start.getTime() > end.getTime()) {
    throw new Error(messages.validation.planDateOrder);
  }

  const dates: string[] = [];

  for (
    let timestamp = start.getTime();
    timestamp <= end.getTime();
    timestamp += DAY_MS
  ) {
    dates.push(
      new Date(timestamp).toISOString().slice(0, 10),
    );
  }

  return dates;
}
