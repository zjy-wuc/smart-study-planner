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
  mode?: "generate" | "organize";
  suggested_title?: string;
  markdown?: string;
  summary?: KnowledgeAiSummary;
};

export type KnowledgeAiRequest =
  | { operation: "generate"; topic: string; instructions?: string }
  | { operation: "organize" | "summary"; noteId: number };

export type KnowledgeAiDraft = {
  title: string;
  content_md: string;
  source: "generate" | "organize";
};
