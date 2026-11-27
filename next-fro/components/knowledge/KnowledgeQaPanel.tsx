"use client";

import { useEffect, useRef, useState, useSyncExternalStore, type KeyboardEvent } from "react";
import { Bot, Clipboard, LoaderCircle, RotateCcw, Send, Square, Trash2, X } from "lucide-react";
import { messages } from "@/messages";
import { useKnowledgeQa } from "@/hooks/useKnowledgeQa";
import { unicodeLength } from "@/lib/knowledge-qa";
import type { KnowledgeQaTurn } from "@/types/knowledge-ai";
import { KnowledgeMarkdownPreview } from "./KnowledgeMarkdownPreview";
import "@/components/css/KnowledgeQA.css";

const m = messages.knowledge.qa;
const mobileQuery = "(max-width: 1050px)";
const subscribeMobile = (callback: () => void) => {
  const media = window.matchMedia(mobileQuery);
  media.addEventListener("change", callback);
  return () => media.removeEventListener("change", callback);
};
const isMobile = () => window.matchMedia(mobileQuery).matches;

type Props = {
  noteId: number;
  open: boolean;
  dirty: boolean;
  savedContentEmpty: boolean;
  staleNotice: string;
  onStale: () => void;
  onResume: () => void;
  onClose: () => void;
};

export function KnowledgeQaPanel({ noteId, open, dirty, savedContentEmpty, staleNotice, onStale, onResume, onClose }: Props) {
  const [question, setQuestion] = useState("");
  const [notice, setNotice] = useState("");
  const qa = useKnowledgeQa(noteId, onStale);
  const endRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLElement>(null);
  const questionRef = useRef<HTMLTextAreaElement>(null);
  const mobile = useSyncExternalStore(subscribeMobile, isMobile, () => false);
  const questionLength = unicodeLength(question);
  const unavailable = dirty ? m.saveFirst : savedContentEmpty ? m.emptyNote : questionLength > 1000 ? m.questionTooLong : "";

  useEffect(() => {
    if (open) endRef.current?.scrollIntoView({ block: "nearest" });
  }, [open, qa.turns]);

  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    questionRef.current?.focus();
    return () => previous?.focus();
  }, [open]);

  function close() {
    if (qa.running) qa.cancel();
    onClose();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      close();
    }
    if (event.key !== "Tab" || !mobile || !panelRef.current) return;
    const focusable = [...panelRef.current.querySelectorAll<HTMLElement>('button:not([disabled]), textarea:not([disabled]), a[href], input:not([disabled])')];
    if (!focusable.length) return;
    if (event.shiftKey && document.activeElement === focusable[0]) {
      event.preventDefault();
      focusable.at(-1)?.focus();
    } else if (!event.shiftKey && document.activeElement === focusable.at(-1)) {
      event.preventDefault();
      focusable[0].focus();
    }
  }

  function send() {
    setNotice("");
    const clean = question.trim();
    if (dirty) return setNotice(m.saveFirst);
    if (savedContentEmpty) return setNotice(m.emptyNote);
    if (!clean) return setNotice(m.emptyQuestion);
    if (unicodeLength(clean) > 1000) return setNotice(m.questionTooLong);
    if (qa.running) return setNotice(m.running);
    setQuestion("");
    onResume();
    void qa.ask(clean);
  }

  async function copy(turn: KnowledgeQaTurn) {
    try { await navigator.clipboard.writeText(turn.answer); setNotice(m.copied); }
    catch { setNotice(m.copyFailed); }
  }

  return <>
    <button type="button" className="knowledge-qa-scrim" aria-label={m.close} data-open={open} onClick={close} />
    <aside ref={panelRef} className="knowledge-qa-panel" data-open={open} aria-hidden={!open} aria-label={m.title} role={mobile ? "dialog" : "complementary"} aria-modal={mobile && open ? true : undefined} onKeyDown={handleKeyDown}>
      <header className="knowledge-qa-header">
        <div><span><Bot size={18} aria-hidden="true" /></span><div><h2>{m.title}</h2><p>{m.description}</p></div></div>
        <button type="button" aria-label={m.close} onClick={close}><X size={18} aria-hidden="true" /></button>
      </header>

      <div className="knowledge-qa-toolbar">
        <button type="button" disabled={!qa.turns.length && !staleNotice} onClick={() => { qa.clear(); setNotice(""); onResume(); }}><Trash2 size={14} aria-hidden="true" />{m.clear}</button>
      </div>

      <div className="knowledge-qa-thread" aria-live="polite">
        {staleNotice && <p role="alert" className="knowledge-qa-error">{staleNotice}</p>}
        {!qa.turns.length && !staleNotice && <div className="knowledge-qa-empty"><Bot size={22} aria-hidden="true" /><p>{m.empty}</p></div>}
        {qa.turns.map((turn) => <article className="knowledge-qa-turn" key={turn.id}>
          <div className="knowledge-qa-question"><span>{m.userLabel}</span><p>{turn.question}</p></div>
          <div className="knowledge-qa-answer" data-status={turn.status}>
            <div className="knowledge-qa-answer-head"><span>{m.assistantLabel}</span>
              {!!turn.answer && (turn.status === "success" || turn.status === "cancelled") && <button type="button" onClick={() => void copy(turn)}><Clipboard size={13} aria-hidden="true" />{m.copy}</button>}
            </div>
            {turn.answer && <KnowledgeMarkdownPreview content={turn.answer} />}
            {turn.status === "generating" && <p className="knowledge-qa-status"><LoaderCircle className="knowledge-ai-spinner" size={15} aria-hidden="true" />{m.generating}</p>}
            {turn.status === "reviewing" && <p className="knowledge-qa-status"><LoaderCircle className="knowledge-ai-spinner" size={15} aria-hidden="true" />{m.reviewing}</p>}
            {turn.status === "cancelled" && <p className="knowledge-qa-cancelled">{turn.message || m.cancelled}</p>}
            {turn.status === "blocked" && <p role="alert" className="knowledge-qa-error">{turn.message || m.blocked}</p>}
            {turn.status === "error" && <div className="knowledge-qa-error" role="alert"><p>{turn.message}</p><button type="button" disabled={qa.running} onClick={() => qa.retry(turn)}><RotateCcw size={13} aria-hidden="true" />{m.retry}</button></div>}
          </div>
        </article>)}
        <div ref={endRef} />
      </div>

      <footer className="knowledge-qa-composer">
        {(notice || unavailable) && <p role="alert">{notice || unavailable}</p>}
        <textarea
          ref={questionRef}
          aria-label={m.questionLabel}
          value={question}
          placeholder={m.placeholder}
          onChange={(event) => { setQuestion(event.target.value); setNotice(""); }}
          onKeyDown={(event) => { if (!event.nativeEvent.isComposing && (event.ctrlKey || event.metaKey) && event.key === "Enter") { event.preventDefault(); send(); } }}
        />
        <div><span>{m.count(questionLength)}</span>
          {qa.running
            ? <button type="button" className="knowledge-qa-stop" onClick={qa.cancel}><Square size={13} aria-hidden="true" />{m.stop}</button>
            : <button type="button" className="knowledge-qa-send" disabled={Boolean(unavailable)} onClick={send}><Send size={14} aria-hidden="true" />{m.send}</button>}
        </div>
      </footer>
    </aside>
  </>;
}
