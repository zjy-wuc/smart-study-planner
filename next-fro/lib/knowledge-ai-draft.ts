import type { KnowledgeAiDraft } from "@/types/knowledge-ai";

const marker = "knowledge_ai_draft_pending";
let pendingDraft: KnowledgeAiDraft | null = null;

export function storeKnowledgeAiDraft(draft: KnowledgeAiDraft) {
  pendingDraft = draft;
  sessionStorage.setItem(marker, "1");
}

export function consumeKnowledgeAiDraft(): { draft: KnowledgeAiDraft | null; expired: boolean } {
  const expired = sessionStorage.getItem(marker) === "1" && pendingDraft === null;
  const draft = pendingDraft;
  pendingDraft = null;
  sessionStorage.removeItem(marker);
  return { draft, expired };
}
