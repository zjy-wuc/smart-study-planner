import { ApiError, apiFetch, assertSseSession, authenticatedFetch } from "@/lib/api/client";
import { readSseEvents } from "@/lib/api/sse";
import { aiResponseErrorMessage } from "@/services/knowledge-ai.service";
import type { KnowledgeAiEvent } from "@/types/knowledge-ai";
import type { PracticeAnswer, PracticeList, PracticeRecord } from "@/types/ai-practice";
import type { ApiResponse } from "@/types/api";

async function streamPractice(
  path: string,
  body: object,
  signal: AbortSignal,
  onEvent: (event: KnowledgeAiEvent) => void,
): Promise<KnowledgeAiEvent> {
  const response = await authenticatedFetch(path, { method: "POST", body: JSON.stringify(body), signal });
  if (!response.ok) {
    let error: unknown = null;
    try { error = await response.json(); } catch { /* 状态码仍可提示。 */ }
    throw new ApiError(aiResponseErrorMessage(error, response.status), response.status);
  }
  if (!response.body) throw new Error("浏览器未提供流式响应内容");
  for await (const event of readSseEvents(response.body)) {
    assertSseSession(response);
    onEvent(event);
    if (["done", "blocked", "error"].includes(event.event)) return event;
  }
  throw new Error("AI 响应提前结束，请重试");
}

export const generatePractice = (noteId: number, count: 5 | 10 | 15, signal: AbortSignal, onEvent: (event: KnowledgeAiEvent) => void) =>
  streamPractice("/ai/practices/generate", { note_id: noteId, question_count: count }, signal, onEvent);

export const submitPractice = (body: { practice_ticket: string; answers: PracticeAnswer[] } | { submission_ticket: string }, signal: AbortSignal, onEvent: (event: KnowledgeAiEvent) => void) =>
  streamPractice("/ai/practices/submit", body, signal, onEvent);

export async function listPractices(page = 1, noteId?: number): Promise<PracticeList> {
  const query = new URLSearchParams({ page: String(page), page_size: "10" });
  if (noteId) query.set("note_id", String(noteId));
  return (await apiFetch<ApiResponse<PracticeList>>(`/ai/practices?${query}`)).data;
}

export async function getPractice(id: number): Promise<PracticeRecord> {
  return (await apiFetch<ApiResponse<PracticeRecord>>(`/ai/practices/${id}`)).data;
}

export async function deletePractice(id: number): Promise<void> {
  await apiFetch(`/ai/practices/${id}`, { method: "DELETE" });
}
