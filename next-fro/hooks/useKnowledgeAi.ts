"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { asKnowledgeAiDone, streamKnowledgeAi } from "@/services/knowledge-ai.service";
import type { KnowledgeAiDone, KnowledgeAiEvent, KnowledgeAiPhase, KnowledgeAiRequest } from "@/types/knowledge-ai";

export function useKnowledgeAi() {
  const [phase, setPhase] = useState<KnowledgeAiPhase>("idle");
  const [streamedText, setStreamedText] = useState("");
  const [result, setResult] = useState<KnowledgeAiDone | null>(null);
  const [message, setMessage] = useState("");
  const controller = useRef<AbortController | null>(null);

  const cancel = useCallback(() => controller.current?.abort(), []);
  const reset = useCallback(() => {
    controller.current?.abort();
    setPhase("idle"); setStreamedText(""); setResult(null); setMessage("");
  }, []);

  const run = useCallback(async (request: KnowledgeAiRequest) => {
    if (controller.current) return;
    const active = new AbortController();
    controller.current = active;
    setPhase("streaming"); setStreamedText(""); setResult(null); setMessage("");

    try {
      const terminal = await streamKnowledgeAi(request, (event: KnowledgeAiEvent) => {
        if (event.event === "delta") setStreamedText((text) => text + String(event.data.text ?? ""));
        if (event.event === "reviewing") setPhase("reviewing");
      }, active.signal);

      if (terminal.event === "done") {
        setResult(asKnowledgeAiDone(terminal));
        setPhase("done");
      } else {
        setStreamedText("");
        setMessage(String(terminal.data.message ?? "AI 请求未完成"));
        setPhase(terminal.event === "blocked" ? "blocked" : "error");
      }
    } catch (error) {
      setStreamedText("");
      if (active.signal.aborted) {
        setPhase("cancelled");
      } else {
        setMessage(error instanceof Error ? error.message : "AI 请求失败，请重试");
        setPhase("error");
      }
    } finally {
      if (controller.current === active) controller.current = null;
    }
  }, []);

  useEffect(() => () => controller.current?.abort(), []);
  return { phase, streamedText, result, message, running: phase === "streaming" || phase === "reviewing", run, cancel, reset };
}
