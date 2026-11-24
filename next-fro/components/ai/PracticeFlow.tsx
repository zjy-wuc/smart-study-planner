"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import * as RadioGroup from "@radix-ui/react-radio-group";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { KnowledgeMarkdownPreview } from "@/components/knowledge/KnowledgeMarkdownPreview";
import { PracticeResult } from "./PracticeResult";
import { ConfirmDiscard } from "./ConfirmDiscard";
import { useAiPractice } from "@/hooks/useAiPractice";
import { getNote, listNotes } from "@/services/knowledge.service";
import type { KnowledgeNote } from "@/types/knowledge";
import type { PracticeQuestion } from "@/types/ai-practice";
import { messages } from "@/messages";
import { aiPractice as m } from "@/messages/zh-CN/ai-practice";
import "@/components/css/AiPractice.css";

const order = (questions: PracticeQuestion[]) => [...questions].sort((a, b) => Number(a.type === "SHORT_ANSWER") - Number(b.type === "SHORT_ANSWER"));

export function PracticeFlow() {
  const query = useSearchParams();
  const requestedId = Number(query.get("note_id"));
  const [notes, setNotes] = useState<KnowledgeNote[]>([]);
  const [notePage, setNotePage] = useState(1);
  const [noteRevision, setNoteRevision] = useState(0);
  const [noteTotal, setNoteTotal] = useState(0);
  const [noteId, setNoteId] = useState(Number.isSafeInteger(requestedId) && requestedId > 0 ? requestedId : 0);
  const [count, setCount] = useState<5 | 10 | 15>(5);
  const [noteError, setNoteError] = useState("");
  const [noteLoading, setNoteLoading] = useState(true);
  const flow = useAiPractice();
  const reducedMotion = useReducedMotion();
  const questions = useMemo(() => order(flow.paper?.questions ?? []), [flow.paper]);

  useEffect(() => {
    let live = true;
    listNotes({ page: notePage, page_size: 100 }).then((list) => {
      if (!live) return;
      setNotes((previous) => notePage === 1 ? list.items : [...previous, ...list.items]);
      setNoteTotal(list.total); setNoteLoading(false);
    }).catch((error) => { if (live) { setNoteError(error instanceof Error ? error.message : m.failed); setNoteLoading(false); } });
    return () => { live = false; };
  }, [notePage, noteRevision]);

  useEffect(() => {
    if (!noteId || notes.some((note) => note.id === noteId) || noteLoading) return;
    let live = true;
    getNote(noteId).then((note) => { if (live && !note.deleted_at) setNotes((current) => [note, ...current]); })
      .catch(() => { if (live) setNoteId(0); });
    return () => { live = false; };
  }, [noteId, notes, noteLoading]);

  useEffect(() => {
    if (flow.phase !== "answering") return;
    const beforeUnload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    const interceptLink = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      const target = event.target;
      if (!(target instanceof Element)) return;
      const link = target.closest("a[href]") as HTMLAnchorElement | null;
      if (!link || link.target === "_blank" || link.hasAttribute("download") || link.href === window.location.href) return;
      if (!window.confirm(m.leave)) { event.preventDefault(); event.stopPropagation(); }
    };
    const navigation = (window as Window & { navigation?: EventTarget }).navigation;
    const interceptTraverse = (event: Event) => {
      const nav = event as Event & { navigationType?: string };
      if (nav.navigationType === "traverse" && event.cancelable && !window.confirm(m.leave)) event.preventDefault();
    };
    window.addEventListener("beforeunload", beforeUnload);
    document.addEventListener("click", interceptLink, true);
    navigation?.addEventListener("navigate", interceptTraverse);
    return () => { window.removeEventListener("beforeunload", beforeUnload); document.removeEventListener("click", interceptLink, true); navigation?.removeEventListener("navigate", interceptTraverse); };
  }, [flow.phase]);

  const available = notes.filter((note) => !note.deleted_at);
  const selected = available.find((note) => note.id === noteId);
  const historyHref = noteId ? `/ai/practice/history?note_id=${noteId}` : "/ai/practice/history";

  return <main className="ai-practice-page">
    <header className="ai-practice-page-header"><div><h1>{m.practice}</h1><p>{m.practiceDesc}</p></div><Link href={historyHref}>{m.history} →</Link></header>
    <PracticeStages phase={flow.phase} />
    <AnimatePresence mode="wait" initial={false}>
    <motion.div key={flow.phase} initial={reducedMotion ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={reducedMotion ? undefined : { opacity: 0, y: -5 }} transition={{ duration: 0.18 }}>
    {flow.phase === "configuring" && <section className="ai-practice-panel ai-practice-config">
      <div><h2>{m.chooseNote}</h2><p>{m.generateHint}</p></div>
      {noteLoading ? <div className="ai-practice-skeleton ai-practice-skeleton-field" role="status" aria-label={m.loading} /> : noteError ? <p role="alert">{noteError} <button type="button" onClick={() => { setNoteError(""); setNoteLoading(true); setNotePage(1); setNoteRevision((value) => value + 1); }}>{messages.knowledge.retry}</button></p> : <>
        <label>{m.chooseNote}<select value={selected?.id ?? ""} onChange={(event) => setNoteId(Number(event.target.value))}><option value="">{m.choose}</option>{available.map((note) => <option key={note.id} value={note.id}>{note.title}</option>)}</select></label>
        {notePage * 100 < noteTotal && <button type="button" className="ai-practice-text-button" onClick={() => setNotePage((page) => page + 1)}>{m.moreNotes}</button>}
        {!available.length && <p>{m.emptyNotes} <Link href="/knowledge/new">{messages.knowledge.create}</Link></p>}
        {selected && <div className="ai-practice-selection"><span>{m.selectedNote}</span><strong>{selected.title}</strong><div><Link href={`/knowledge/${selected.id}`}>{m.noteLink}</Link><Link href={historyHref}>{m.historyLink}</Link></div></div>}
      </>}
      <div className="ai-practice-count-field"><span id="ai-practice-count-label">{m.count}</span><RadioGroup.Root className="ai-practice-count-options" aria-labelledby="ai-practice-count-label" value={String(count)} onValueChange={(value) => setCount(Number(value) as 5 | 10 | 15)}>{([5, 10, 15] as const).map((value) => <RadioGroup.Item key={value} value={String(value)} className="ai-practice-count">{value} {m.questionUnit}</RadioGroup.Item>)}</RadioGroup.Root><p>{m.countHint}</p></div>
      {flow.error && <p role="alert" className="ai-practice-error">{flow.error}</p>}
      <button className="ai-practice-primary" type="button" disabled={!selected} onClick={() => void flow.generate(noteId, count)}>{m.generate}</button>
    </section>}
    {flow.phase === "generating" && <section className="ai-practice-panel ai-practice-wait" role="status"><span className="ai-practice-pulse" /><h2>{flow.stage}</h2><button type="button" onClick={flow.cancelGeneration}>{m.cancel}</button></section>}
    {flow.phase === "preview" && flow.paper && <section className="ai-practice-panel"><div className="ai-practice-section-heading"><div><h2>{m.preview}</h2><p>{flow.paper.note_title} · {flow.paper.question_count} 题 · {m.previewHint}</p></div><div><button type="button" onClick={flow.discard}>{m.discard}</button><button className="ai-practice-primary" type="button" onClick={flow.begin}>{m.start}</button></div></div><QuestionList questions={questions} /></section>}
    {["answering", "grading", "grading_failed"].includes(flow.phase) && flow.paper && <section className="ai-practice-panel"><div className="ai-practice-section-heading"><div><h2>{flow.paper.note_title}</h2><p>{m.answered} {Object.values(flow.answers).filter((value) => value.trim()).length} / {flow.paper.question_count}</p></div>{flow.phase === "answering" && <ConfirmDiscard onConfirm={flow.discard} />}</div><QuestionList questions={questions} answers={flow.answers} onAnswer={flow.answer} locked={flow.phase !== "answering"} />
      {flow.phase === "answering" && <button className="ai-practice-primary" type="button" onClick={() => void flow.grade()}>{m.submit}</button>}
      {flow.phase === "answering" && flow.error && <p role="alert" className="ai-practice-error">{flow.error}</p>}
      {flow.phase === "grading" && <p role="status" className="ai-practice-progress">{flow.stage}</p>}
      {flow.phase === "grading_failed" && <div role="alert" className="ai-practice-error"><p>{flow.error || m.gradeFailed}</p><button type="button" onClick={() => void flow.grade()}>{m.retryGrade}</button></div>}
    </section>}
    {flow.phase === "completed" && flow.result && <><PracticeResult record={flow.result} /><div className="ai-practice-footer"><Link href="/ai/practice/history">{m.history}</Link><button type="button" onClick={flow.discard}>{m.generate}</button></div></>}
    </motion.div>
    </AnimatePresence>
  </main>;
}

function PracticeStages({ phase }: { phase: ReturnType<typeof useAiPractice>["phase"] }) {
  const stages = [m.configure, m.ready, m.doing, m.finished];
  const active = phase === "configuring" || phase === "generating" ? 0 : phase === "preview" ? 1 : phase === "completed" ? 3 : 2;
  return <ol className="ai-practice-stages" aria-label={m.practice}>{stages.map((stage, index) => <li key={stage} aria-current={index === active ? "step" : undefined} className={index < active ? "is-past" : ""}><span>{index + 1}</span>{stage}</li>)}</ol>;
}

function QuestionList({ questions, answers, onAnswer, locked = false }: { questions: PracticeQuestion[]; answers?: Record<string, string>; onAnswer?: (question: PracticeQuestion, value: string) => void; locked?: boolean }) {
  return <div className="ai-practice-question-list">{questions.map((question, index) => <article key={question.id} className="ai-practice-question"><div className="ai-practice-question-top"><span>{index + 1} · {question.type === "SINGLE_CHOICE" ? m.single : m.short}</span>{answers && <span>{answers[question.id]?.trim() ? m.answered : m.skipped}</span>}</div><KnowledgeMarkdownPreview content={question.stem} />
    {question.type === "SINGLE_CHOICE" && (answers ? <RadioGroup.Root className="ai-practice-options" aria-label={`${m.single} ${index + 1}`} value={answers[question.id] ?? ""} disabled={locked} onValueChange={(value) => onAnswer?.(question, value)}>{Object.entries(question.options ?? {}).map(([key, value]) => <RadioGroup.Item key={key} value={key} className="ai-practice-option"><b>{key}</b><span>{value}</span></RadioGroup.Item>)}</RadioGroup.Root> : <div className="ai-practice-options-read">{Object.entries(question.options ?? {}).map(([key, value]) => <p key={key}><b>{key}</b> {value}</p>)}</div>)}
    {question.type === "SHORT_ANSWER" && answers && <textarea aria-label={`${m.short} ${index + 1}`} value={answers[question.id] ?? ""} disabled={locked} onChange={(event) => onAnswer?.(question, event.target.value)} rows={5} />}
  </article>)}</div>;
}
