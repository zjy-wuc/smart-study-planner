"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { MessageCircle } from "lucide-react";
import { messages } from "@/messages";
import { aiPractice } from "@/messages/zh-CN/ai-practice";
import { useKnowledgeQuery } from "@/hooks/useKnowledge";
import { getNote } from "@/services/knowledge.service";
import { KnowledgeMarkdownPreview } from "./KnowledgeMarkdownPreview";
import { KnowledgeQaPanel } from "./KnowledgeQaPanel";
import { KnowledgeReviewPanel } from "./KnowledgeReviewPanel";
import "@/components/css/Knowledge.css";

const m = messages.knowledge;

export function KnowledgeNotePreview({ noteId }: { noteId: number }) {
  const [qaOpen, setQaOpen] = useState(false);
  const [qaStaleNotice, setQaStaleNotice] = useState("");
  const load = useCallback(() => {
    if (!Number.isSafeInteger(noteId) || noteId <= 0) return Promise.reject(new Error(m.invalidId));
    return getNote(noteId);
  }, [noteId]);
  const note = useKnowledgeQuery(load);
  const refreshNote = note.refresh;
  const handleQaStale = useCallback(() => {
    setQaStaleNotice(m.qa.stale);
    refreshNote();
  }, [refreshNote]);

  if (note.loading) return <p role="status">{m.loading}</p>;
  if (note.error) return <div className="knowledge-page"><p role="alert" className="knowledge-error">{note.error}</p><button onClick={note.refresh}>{m.retry}</button> <Link href="/knowledge">{m.back}</Link></div>;
  if (!note.data) return null;
  const current = note.data;

  return <div className="knowledge-page knowledge-detail-page">
    <div className="knowledge-qa-layout" data-open={qaOpen}>
      <div className="knowledge-workspace">
        <header className="knowledge-detail-heading">
          <div>
            <Link className="knowledge-detail-back" href="/knowledge">{m.back}</Link>
            <h1>{current.title}</h1>
            <p className="knowledge-meta">{m.updated}：<time>{current.updated_at.replace("T", " ")}</time></p>
            {!!current.tags.length && <div className="knowledge-tags">{current.tags.map((tag) => <span key={tag}>{tag}</span>)}</div>}
          </div>
          <div className="knowledge-actions knowledge-detail-actions">
            <button type="button" className="knowledge-qa-open" onClick={() => setQaOpen(true)}><MessageCircle size={16} aria-hidden="true" />{m.qa.open}</button>
            <Link href={`/ai/practice?note_id=${current.id}`}>{aiPractice.practice}</Link>
            <Link href={`/knowledge/${current.id}/edit`}>{m.edit}</Link>
          </div>
        </header>
        <div className="knowledge-detail-layout">
          <article className="knowledge-detail-content" aria-label={m.content}>
            {current.content_md.trim() ? <KnowledgeMarkdownPreview content={current.content_md} /> : <p className="knowledge-meta">{m.noContent}</p>}
          </article>
          <KnowledgeReviewPanel noteId={current.id} />
        </div>
      </div>
      <KnowledgeQaPanel key={current.updated_at} noteId={current.id} open={qaOpen} dirty={false} savedContentEmpty={!current.content_md.trim()} staleNotice={qaStaleNotice} onStale={handleQaStale} onResume={() => setQaStaleNotice("")} onClose={() => setQaOpen(false)} />
    </div>
  </div>;
}
