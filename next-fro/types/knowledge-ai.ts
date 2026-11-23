export type KnowledgeAiOperation = "generate" | "organize" | "summary";
export type KnowledgeAiPhase = "idle" | "streaming" | "reviewing" | "done" | "blocked" | "error" | "cancelled";

export type KnowledgeAiSummary = {
  overview: string;
  key_points: string;
  outline: string;
};

export type KnowledgeAiEvent = {
  event: "start" | "delta" | "reviewing" | "done" | "blocked" | "error";
  data: Record<string, unknown>;
};

export type KnowledgeAiDone = {
  status: "success";
  mode?: "generate" | "organize" | "ask";
  suggested_title?: string;
  markdown?: string;
  summary?: KnowledgeAiSummary;
};

export type KnowledgeAiRequest =
  | { operation: "generate"; topic: string; instructions?: string }
  | { operation: "organize" | "summary"; noteId: number }
  | { operation: "ask"; noteId: number; question: string; history: KnowledgeQaHistoryTurn[] };

export type KnowledgeAiDraft = {
  title: string;
  content_md: string;
  source: "generate" | "organize";
};

export type KnowledgeQaHistoryTurn = { question: string; answer: string };
export type KnowledgeQaStatus = "generating" | "reviewing" | "success" | "cancelled" | "error" | "blocked" | "stale";
export type KnowledgeQaTurn = {
  id: number;
  contextId: number;
  question: string;
  answer: string;
  status: KnowledgeQaStatus;
  message?: string;
  historySnapshot: KnowledgeQaHistoryTurn[];
};
