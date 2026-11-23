import type { KnowledgeAiEvent, KnowledgeQaHistoryTurn, KnowledgeQaTurn } from "@/types/knowledge-ai";

export function unicodeLength(value: string): number {
  return Array.from(value).length;
}

export function isKnowledgeQaStale(event: KnowledgeAiEvent): boolean {
  return event.event === "error" && (event.data.code === "NOTE_CHANGED" || event.data.status === "STALE");
}

export function recentSuccessfulQaHistory(
  turns: KnowledgeQaTurn[],
  contextId: number,
): KnowledgeQaHistoryTurn[] {
  return turns
    .filter((turn) => turn.contextId === contextId && turn.status === "success")
    .slice(-3)
    .map(({ question, answer }) => ({ question, answer }));
}
