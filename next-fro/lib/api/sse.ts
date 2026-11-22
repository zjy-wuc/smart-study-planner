import type { KnowledgeAiEvent } from "@/types/knowledge-ai";

function parseBlock(block: string): KnowledgeAiEvent | null {
  let event = "message";
  const data: string[] = [];

  for (const line of block.split("\n")) {
    if (!line || line.startsWith(":")) continue;
    const separator = line.indexOf(":");
    const field = separator === -1 ? line : line.slice(0, separator);
    let value = separator === -1 ? "" : line.slice(separator + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") event = value;
    if (field === "data") data.push(value);
  }

  if (!data.length || !["start", "delta", "reviewing", "done", "blocked", "error"].includes(event)) return null;
  return { event: event as KnowledgeAiEvent["event"], data: JSON.parse(data.join("\n")) as Record<string, unknown> };
}

export async function* readSseEvents(
  stream: ReadableStream<Uint8Array>,
): AsyncGenerator<KnowledgeAiEvent, void, void> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let exhausted = false;

  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      const trailingCarriageReturn = !done && buffer.endsWith("\r");
      const tail = trailingCarriageReturn ? "\r" : "";
      const normalizable = trailingCarriageReturn ? buffer.slice(0, -1) : buffer;
      buffer = normalizable.replace(/\r\n|\r/g, "\n") + tail;

      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const parsed = parseBlock(buffer.slice(0, boundary));
        buffer = buffer.slice(boundary + 2);
        if (parsed) yield parsed;
        boundary = buffer.indexOf("\n\n");
      }

      if (done) {
        exhausted = true;
        const parsed = parseBlock(buffer.replace(/\r\n|\r/g, "\n"));
        if (parsed) yield parsed;
        return;
      }
    }
  } finally {
    if (!exhausted) {
      try { await reader.cancel(); } catch { /* 请求取消时读取器可能已经关闭。 */ }
    }
    reader.releaseLock();
  }
}
