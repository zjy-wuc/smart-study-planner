
export type { ApiResponse } from "@/types/auth";
//数据验证错误类型
export type ValidationIssue = {
  type: string;
  loc: (string | number)[];
  msg: string;
  input?: unknown;
  ctx?: Record<string, unknown>;
};
