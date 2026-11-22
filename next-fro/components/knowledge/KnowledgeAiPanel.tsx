"use client";

import { useState } from "react";
import { Clipboard, LoaderCircle, Sparkles, Square, WandSparkles } from "lucide-react";
import { messages } from "@/messages";
import { useKnowledgeAi } from "@/hooks/useKnowledgeAi";
import type { KnowledgeAiDraft, KnowledgeAiOperation } from "@/types/knowledge-ai";
import { KnowledgeMarkdownPreview } from "./KnowledgeMarkdownPreview";
import "@/components/css/KnowledgeAI.css";

const m = messages.knowledge.ai;

type Props = {
  noteId?: number;
  dirty: boolean;
  onApply: (draft: KnowledgeAiDraft) => void;
};

export function KnowledgeAiPanel({ noteId, dirty, onApply }: Props) {
  const [operation, setOperation] = useState<KnowledgeAiOperation>("generate");
  const [topic, setTopic] = useState("");
  const [instructions, setInstructions] = useState("");
  const [localMessage, setLocalMessage] = useState("");
  const ai = useKnowledgeAi();
  const sourceUnavailable = operation !== "generate" && (!noteId || dirty);
  const preview = ai.result?.markdown ?? ai.streamedText;

  function choose(next: KnowledgeAiOperation) {
    if (ai.running) return;
    ai.reset(); setLocalMessage(""); setOperation(next);
  }

  function start() {
    setLocalMessage("");
    if (operation === "generate") {
      const cleanTopic = topic.trim();
      if (Array.from(cleanTopic).length < 2 || Array.from(cleanTopic).length > 100) return setLocalMessage(m.invalidTopic);
      if (Array.from(instructions).length > 500) return setLocalMessage(m.invalidInstructions);
      void ai.run({ operation, topic: cleanTopic, instructions: instructions.trim() || undefined });
      return;
    }
    if (!noteId || dirty) return setLocalMessage(noteId ? m.dirtySource : m.unavailableNew);
    void ai.run({ operation, noteId });
  }

  async function copySummary() {
    if (!ai.result?.summary) return;
    const text = `${m.overview}\n${ai.result.summary.overview}\n\n${m.keyPoints}\n${ai.result.summary.key_points}\n\n${m.outline}\n${ai.result.summary.outline}`;
    try { await navigator.clipboard.writeText(text); setLocalMessage(m.copied); }
    catch { setLocalMessage(m.copyFailed); }
  }

  function applyDraft() {
    if (!ai.result?.markdown || !ai.result.mode) return;
    onApply({
      title: ai.result.suggested_title?.trim() || topic.trim(),
      content_md: ai.result.markdown,
      source: ai.result.mode,
    });
  }

  return <aside className="knowledge-ai" aria-label={m.title}>
    <div className="knowledge-ai-intro">
      <span className="knowledge-ai-icon"><Sparkles size={18} aria-hidden="true" /></span>
      <div><h2>{m.title}</h2><p>{m.description}</p></div>
    </div>

    <div className="knowledge-ai-tabs" role="tablist" aria-label={m.title}>
      {(["generate", "organize", "summary"] as const).map((item) => <button
        key={item}
        type="button"
        role="tab"
        aria-selected={operation === item}
        disabled={ai.running || (item !== "generate" && !noteId)}
        onClick={() => choose(item)}
      >{item === "generate" ? m.generate : item === "organize" ? m.organize : m.summary}</button>)}
    </div>

    {operation === "generate" && <div className="knowledge-ai-inputs">
      <label>{m.topic}<input value={topic} maxLength={100} placeholder={m.topicPlaceholder} onChange={(event) => setTopic(event.target.value)} /></label>
      <label>{m.instructions}<textarea value={instructions} maxLength={500} placeholder={m.instructionsPlaceholder} onChange={(event) => setInstructions(event.target.value)} /></label>
    </div>}

    {sourceUnavailable && <p className="knowledge-ai-hint">{noteId ? m.dirtySource : m.unavailableNew}</p>}
    {(localMessage || ai.message) && <p role="alert" className={ai.phase === "done" ? "knowledge-ai-notice" : "knowledge-ai-error"}>{localMessage || ai.message}</p>}
    {ai.phase === "cancelled" && <p role="status" className="knowledge-ai-hint">{m.cancelled}</p>}

    <div className="knowledge-ai-controls">
      {ai.running ? <button type="button" className="knowledge-ai-stop" onClick={ai.cancel}><Square size={14} aria-hidden="true" />{m.cancel}</button>
        : <button type="button" className="knowledge-ai-run" disabled={sourceUnavailable} onClick={start}><WandSparkles size={16} aria-hidden="true" />{
          operation === "generate" ? m.startGenerate : operation === "organize" ? m.startOrganize : m.startSummary
        }</button>}
      {ai.phase !== "idle" && !ai.running && <button type="button" onClick={ai.reset}>{m.retry}</button>}
    </div>

    {ai.running && <p className="knowledge-ai-status" role="status"><LoaderCircle className="knowledge-ai-spinner" size={16} aria-hidden="true" />{ai.phase === "reviewing" ? m.reviewing : m.streaming}</p>}

    <section className="knowledge-ai-result" aria-live="polite">
      <div className="knowledge-ai-result-heading"><h3>{m.preview}</h3>
        {ai.phase === "done" && ai.result?.summary && <button type="button" onClick={() => void copySummary()}><Clipboard size={14} aria-hidden="true" />{m.copy}</button>}
      </div>
      {ai.result?.summary ? <div className="knowledge-ai-summary">
        <article><h4>{m.overview}</h4><p>{ai.result.summary.overview}</p></article>
        <article><h4>{m.keyPoints}</h4><p>{ai.result.summary.key_points}</p></article>
        <article><h4>{m.outline}</h4><p>{ai.result.summary.outline}</p></article>
      </div> : preview ? <KnowledgeMarkdownPreview content={preview} /> : <p className="knowledge-ai-empty">{m.noPreview}</p>}
    </section>

    {ai.phase === "done" && ai.result?.markdown && <button type="button" className="knowledge-ai-apply" onClick={applyDraft}>{m.apply}</button>}
  </aside>;
}
