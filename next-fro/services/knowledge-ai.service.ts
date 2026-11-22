import { ApiError, authenticatedFetch } from "@/lib/api/client";
import { readSseEvents } from "@/lib/api/sse";
import type { KnowledgeAiDone, KnowledgeAiEvent, KnowledgeAiRequest } from "@/types/knowledge-ai";

async function responseError(response: Response): Promise<ApiError> {
  let body: { message?: string; detail?: string | { message?: string } } = {};
  try { body = await response.json(); } catch { /* 非 JSON 错误使用状态文案。 */ }
  const message = typeof body.detail === "string"
    ? body.detail
    : body.detail?.message ?? body.message ?? `AI 请求失败（${response.status}）`;
  return new ApiError(message, response.status);
}

export async function streamKnowledgeAi(
  request: KnowledgeAiRequest,
  onEvent: (event: KnowledgeAiEvent) => void,
  signal: AbortSignal,
): Promise<KnowledgeAiEvent> {
  const path = request.operation === "generate"
    ? "/notes/ai/generate"
    : `/notes/${request.noteId}/ai/${request.operation}`;
  const response = await authenticatedFetch(path, {
    method: "POST",
    body: request.operation === "generate"
      ? JSON.stringify({ topic: request.topic, instructions: request.instructions || null })
      : undefined,
    signal,
  });

  if (!response.ok) throw await responseError(response);
  if (!response.body) throw new Error("浏览器未提供流式响应内容");

  for await (const event of readSseEvents(response.body)) {
    onEvent(event);
    if (["done", "blocked", "error"].includes(event.event)) return event;
  }
  throw new Error("AI 响应提前结束，请重试");
}

export function asKnowledgeAiDone(event: KnowledgeAiEvent): KnowledgeAiDone {
  return event.data as KnowledgeAiDone;
}
