"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { isKnowledgeQaStale, recentSuccessfulQaHistory } from "@/lib/knowledge-qa";
import { streamKnowledgeAi } from "@/services/knowledge-ai.service";
import type { KnowledgeAiEvent, KnowledgeQaHistoryTurn, KnowledgeQaTurn } from "@/types/knowledge-ai";

export function useKnowledgeQa(noteId: number, onStale?: () => void) {
  const [turns, setTurns] = useState<KnowledgeQaTurn[]>([]);
  const controller = useRef<AbortController | null>(null);
  const requestId = useRef(0);
  const turnId = useRef(0);
  const contextId = useRef(0);
  const turnsRef = useRef(turns);
  turnsRef.current = turns;

  const cancel = useCallback(() => controller.current?.abort(), []);

  const clear = useCallback(() => {
    requestId.current += 1;
    controller.current?.abort();
    controller.current = null;
    contextId.current += 1;
    setTurns([]);
  }, []);

  const ask = useCallback(async (rawQuestion: string, retryHistory?: KnowledgeQaHistoryTurn[]) => {
    if (controller.current) return;
    const question = rawQuestion.trim();
    const history = retryHistory ?? recentSuccessfulQaHistory(turnsRef.current, contextId.current);
    const id = ++turnId.current;
    const activeRequest = ++requestId.current;
    const active = new AbortController();
    controller.current = active;
    setTurns((current) => [...current, {
      id, contextId: contextId.current, question, answer: "", status: "generating", historySnapshot: history,
    }]);

    const update = (change: (turn: KnowledgeQaTurn) => KnowledgeQaTurn) => {
      if (requestId.current !== activeRequest) return;
      setTurns((current) => current.map((turn) => turn.id === id ? change(turn) : turn));
    };

    try {
      const terminal = await streamKnowledgeAi({ operation: "ask", noteId, question, history }, (event: KnowledgeAiEvent) => {
        if (requestId.current !== activeRequest) return;
        if (event.event === "delta") update((turn) => ({ ...turn, answer: turn.answer + String(event.data.text ?? "") }));
        if (event.event === "reviewing") update((turn) => ({ ...turn, status: "reviewing" }));
      }, active.signal);

      if (terminal.event === "done") {
        update((turn) => ({ ...turn, status: "success", answer: String(terminal.data.markdown ?? "") }));
      } else {
        const stale = isKnowledgeQaStale(terminal);
        if (stale) {
          requestId.current += 1;
          controller.current = null;
          contextId.current += 1;
          setTurns([]);
          onStale?.();
          return;
        }
        update((turn) => ({
          ...turn,
          answer: "",
          status: terminal.event === "blocked" ? "blocked" : "error",
          message: String(terminal.data.message ?? "AI 回答未完成"),
        }));
      }
    } catch (error) {
      if (requestId.current !== activeRequest) return;
      if (active.signal.aborted) {
        update((turn) => ({ ...turn, status: "cancelled", message: "已取消 · 内容不完整" }));
      } else {
        update((turn) => ({
          ...turn, answer: "", status: "error",
          message: error instanceof Error ? error.message : "AI 问答失败，请重试",
        }));
      }
    } finally {
      if (requestId.current === activeRequest) controller.current = null;
    }
  }, [noteId, onStale]);

  const retry = useCallback((turn: KnowledgeQaTurn) => {
    void ask(turn.question, turn.historySnapshot);
  }, [ask]);

  useEffect(() => () => {
    requestId.current += 1;
    controller.current?.abort();
  }, []);

  const running = turns.some((turn) => turn.status === "generating" || turn.status === "reviewing");
  return { turns, running, ask, retry, cancel, clear };
}
