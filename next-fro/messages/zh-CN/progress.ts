import type { MessageValue } from "../types";

export const progress = {
  loading: "正在加载完成率...",
  unavailable: "进度暂时无法获取",
  notComputable: "暂无可计算进度",
  current: "当前可统计进度",
  planLabel: (name: MessageValue): string =>
    `${name}的可统计进度`,
  leafCount: (computable: MessageValue, total: MessageValue): string =>
    `${computable}/${total} 个叶子参与计算`,
};
