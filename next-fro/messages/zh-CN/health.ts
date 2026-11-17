import type { MessageValue } from "../types";

export const health = {
  connecting: "正在连接后端...",
  httpError: (status: MessageValue): string =>
    `HTTP 错误：${status}`,
  connectionFailed: "连接失败",
  title: "智能学习计划管理系统",
  frontend: "前端：Next.js",
  backend: "后端：Python + FastAPI",
  testTitle: "后端连接测试",
  statusText: (status: MessageValue): string =>
    `连接状态：${status}`,
  errorText: (error: MessageValue): string =>
    `错误信息：${error}`,
};
