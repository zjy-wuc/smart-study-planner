"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { deletePractice, listPractices } from "@/services/ai-practice.service";
import type { PracticeList } from "@/types/ai-practice";
import { messages } from "@/messages";
import { aiPractice as m } from "@/messages/zh-CN/ai-practice";
import { ConfirmDelete } from "@/components/ai/ConfirmDelete";
import "@/components/css/AiPractice.css";


function History({ noteId }: { noteId?: number }) {
  const [page, setPage] = useState(1);
  const [list, setList] = useState<PracticeList | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState<number | null>(null);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let live = true;
    Promise.resolve().then(() => {
      if (live) { setLoading(true); setError(""); }
      return listPractices(page, noteId);
    }).then((value) => { if (live) setList(value); })
      .catch((cause) => { if (live) setError(cause instanceof Error ? cause.message : m.failed); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [page, noteId, revision]);

  async function remove(id: number) {
    setDeleting(id); setError("");
    try {
      await deletePractice(id);
      if (list?.items.length === 1 && page > 1) setPage(page - 1);
      else setRevision((value) => value + 1);
    } catch (cause) { setError(cause instanceof Error ? cause.message : m.failed); }
    finally { setDeleting(null); }
  }

  return <main className="ai-practice-page"><header className="ai-practice-page-header"><div><h1>{m.history}</h1><p>{m.historyDesc}</p></div><Link href="/ai/practice">{m.generate} →</Link></header>
    {noteId && <p className="ai-practice-filter">{m.chooseNote} #{noteId} · <Link href="/ai/practice/history">{m.allNotes}</Link></p>}
    {error && <p role="alert" className="ai-practice-error">{error} <button type="button" onClick={() => setRevision((value) => value + 1)}>{messages.knowledge.retry}</button></p>}
    {loading ? <div className="ai-practice-skeleton-list" role="status" aria-label={m.loading}>{[0, 1, 2].map((item) => <div key={item} className="ai-practice-skeleton ai-practice-skeleton-row" />)}</div> : !list?.items.length ? <div className="ai-practice-panel"><p>{m.emptyHistory}</p><Link href="/ai/practice">{m.generate}</Link></div> : <>
      <p className="ai-practice-history-total">{list.total} {m.historyTotal}</p>
      <div className="ai-practice-history-list">{list.items.map((item) => <article key={item.id} className="ai-practice-history-item"><div className="ai-practice-history-copy"><h2>{item.note_title_snapshot}</h2><p><time dateTime={item.created_at}>{item.created_at.replace("T", " ")}</time><span>{item.question_count} {m.questionUnit}</span>{item.source_note_deleted && <span className="ai-practice-deleted">{m.noteDeleted}</span>}</p></div><div className="ai-practice-history-score"><strong>{item.score}<small> / 100</small></strong><span className="ai-practice-history-track" aria-hidden="true"><span style={{ width: `${Math.max(0, Math.min(100, item.score))}%` }} /></span></div><div className="ai-practice-history-actions"><Link href={`/ai/practice/history/${item.id}`}>{m.detail}</Link><ConfirmDelete disabled={deleting !== null} onConfirm={() => void remove(item.id)} /></div></article>)}</div>
      <nav className="ai-practice-pagination" aria-label={m.history}><button type="button" disabled={page <= 1} onClick={() => setPage(page - 1)}>{m.previous}</button><span>{page} / {Math.max(1, Math.ceil(list.total / 10))}</span><button type="button" disabled={page * 10 >= list.total} onClick={() => setPage(page + 1)}>{m.next}</button></nav>
    </>}
  </main>;
}

export default function PracticeHistoryPage() {
  return <Suspense fallback={<p role="status">{m.loading}</p>}><HistoryRoute /></Suspense>;
}

function HistoryRoute() {
  const query = useSearchParams();
  const raw = Number(query.get("note_id"));
  const noteId = Number.isSafeInteger(raw) && raw > 0 ? raw : undefined;
  return <History key={noteId ?? "all"} noteId={noteId} />;
}
