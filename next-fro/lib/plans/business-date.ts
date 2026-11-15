
/**
 * 获取后端约定的东八区业务日期。
 * 只用于前端提示和按钮展示。
 * 最终是否允许修改，以 FastAPI 为准。
 */
export function getBusinessToday(): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());

  const getPart = (type: string) =>
    parts.find((part) => part.type === type)?.value ?? "";

  return [
    getPart("year"),
    getPart("month"),
    getPart("day"),
  ].join("-");
}
