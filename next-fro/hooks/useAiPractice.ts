"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { generatePractice, submitPractice } from "@/services/ai-practice.service";
import type { GeneratedPractice, PracticeAnswer, PracticeQuestion, PracticeRecord } from "@/types/ai-practice";
import type { KnowledgeAiEvent } from "@/types/knowledge-ai";
import { aiPractice as m } from "@/messages/zh-CN/ai-practice";

type Phase = "configuring" | "generating" | "preview" | "answering" | "grading" | "grading_failed" | "completed";

function eventError(event: KnowledgeAiEvent): string {
  return typeof event.data.message === "string" ? event.data.message : event.event === "blocked" ? m.blocked : m.failed;
}

export function useAiPractice() {
  const [phase, setPhase] = useState<Phase>("configuring");
  const [stage, setStage] = useState("");
  const [error, setError] = useState("");
  const [paper, setPaper] = useState<GeneratedPractice | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [result, setResult] = useState<PracticeRecord | null>(null);
  const controller = useRef<AbortController | null>(null);
  const requestId = useRef(0);
  const expiresAt = useRef(0);
  const submissionTicket = useRef<string | null>(null);
  const originalSubmission = useRef<{ practice_ticket: string; answers: PracticeAnswer[] } | null>(null);
  const busy = useRef(false);

  useEffect(() => () => { controller.current?.abort(); requestId.current += 1; }, []);

  const generate = useCallback(async (noteId: number, count: 5 | 10 | 15) => {
    if (busy.current) return;
    busy.current = true;
    const id = ++requestId.current;
    const abort = new AbortController();
    controller.current = abort;
    setError(""); setPaper(null); setResult(null); setStage(m.generating); setPhase("generating");
    try {
      const terminal = await generatePractice(noteId, count, abort.signal, (event) => {
        if (id === requestId.current && event.event === "reviewing") setStage(m.reviewing);
      });
      if (id !== requestId.current) return;
      if (terminal.event !== "done" || terminal.data.status !== "success") throw new Error(eventError(terminal));
      const generated = terminal.data as GeneratedPractice;
      if (!Array.isArray(generated.questions) || !generated.practice_ticket) throw new Error(m.failed);
      expiresAt.current = Date.now() + generated.expires_in_seconds * 1000;
      submissionTicket.current = null;
      originalSubmission.current = null;
      setPaper(generated); setPhase("preview");
    } catch (cause) {
      if (id !== requestId.current) return;
      setError(cause instanceof Error ? cause.message : m.failed); setPhase("configuring");
    } finally { if (id === requestId.current) busy.current = false; }
  }, []);

  const cancelGeneration = useCallback(() => {
    if (phase !== "generating") return;
    requestId.current += 1; controller.current?.abort(); busy.current = false;
    setPaper(null); setError(""); setPhase("configuring");
  }, [phase]);

  const discard = useCallback(() => {
    setPaper(null); setAnswers({}); setError(""); setPhase("configuring");
    expiresAt.current = 0;
  }, []);

  const begin = useCallback(() => { setAnswers({}); setError(""); setPhase("answering"); }, []);
  const answer = useCallback((question: PracticeQuestion, value: string) => {
    if (phase !== "answering") return;
    setAnswers((current) => ({ ...current, [question.id]: value }));
  }, [phase]);

  const grade = useCallback(async () => {
    if (busy.current || !paper || (phase !== "answering" && phase !== "grading_failed")) return;
    if (Date.now() >= expiresAt.current) { setError(m.expired); return; }
    if (Object.values(answers).some((value) => Array.from(value.trim()).length > 2000)) { setError(m.answerTooLong); return; }
    if (phase === "answering") {
      originalSubmission.current = {
        practice_ticket: paper.practice_ticket,
        answers: paper.questions.map((question) => ({ id: question.id, answer: answers[question.id]?.trim() || null })),
      };
    }
    const body = submissionTicket.current
      ? { submission_ticket: submissionTicket.current }
      : originalSubmission.current;
    if (!body) return;
    busy.current = true;
    const id = ++requestId.current;
    const abort = new AbortController();
    controller.current = abort;
    setError(""); setStage(m.grading); setPhase("grading");
    try {
      const terminal = await submitPractice(body, abort.signal, (event) => {
        if (id !== requestId.current) return;
        if (event.event === "start" && typeof event.data.submission_ticket === "string") submissionTicket.current = event.data.submission_ticket;
        if (event.event === "reviewing") setStage(m.grading);
      });
      if (id !== requestId.current) return;
      if (terminal.event !== "done" || terminal.data.status !== "success") throw new Error(eventError(terminal));
      const saved = terminal.data.record as PracticeRecord | undefined;
      if (!saved || !Array.isArray(saved.questions)) throw new Error(m.failed);
      setResult(saved); setPhase("completed");
      originalSubmission.current = null; submissionTicket.current = null;
    } catch (cause) {
      if (id !== requestId.current) return;
      setError(cause instanceof Error ? cause.message : m.gradeFailed); setPhase("grading_failed");
    } finally { busy.current = false; }
  }, [answers, paper, phase]);

  return { phase, stage, error, paper, answers, result, generate, cancelGeneration, discard, begin, answer, grade };
}
