import { zhCN } from "./zh-CN";

// 页面、组件与工具函数统一从此处读取文案；未来新增语言时保留同一结构。
export type Messages = typeof zhCN;
export const messages: Messages = zhCN;
export const locale = "zh-CN";
