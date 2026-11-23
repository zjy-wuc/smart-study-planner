import { ApiError, authenticatedFetch } from "@/lib/api/client";
import { readSseEvents } from "@/lib/api/sse";
import type { KnowledgeAiDone, KnowledgeAiEvent, KnowledgeAiRequest } from "@/types/knowledge-ai";

type ErrorBody = {
  message?: unknown;
  detail?: unknown;
};

export function aiResponseErrorMessage(body: unknown, status: number): string {
  if (!body || typeof body !== "object") return `AI 请求失败（${status}）`;
  const { detail, message } = body as ErrorBody;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((issue) => issue && typeof issue === "object" ? (issue as { msg?: unknown }).msg : null)
      .filter((value): value is string => typeof value === "string" && Boolean(value.trim()));
    if (messages.length) return messages.join("；");
  }
  if (detail && typeof detail === "object") {
    const detailMessage = (detail as { message?: unknown }).message;
    if (typeof detailMessage === "string" && detailMessage.trim()) return detailMessage;
  }
  if (typeof message === "string" && message.trim()) return message;
  return `AI 请求失败（${status}）`;
}

async function responseError(response: Response): Promise<ApiError> {
  let body: unknown = null;
  try { body = await response.json(); } catch { /* 非 JSON 错误使用状态文案。 */ }
  return new ApiError(aiResponseErrorMessage(body, response.status), response.status);
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
      : request.operation === "ask"
        ? JSON.stringify({ question: request.question, history: request.history })
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
