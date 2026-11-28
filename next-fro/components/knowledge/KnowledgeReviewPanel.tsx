"use client";

import { useCallback } from "react";
import { messages } from "@/messages";
import { useKnowledgeAction, useKnowledgeQuery } from "@/hooks/useKnowledge";
import { addReview, getReviews } from "@/services/knowledge.service";

const m = messages.knowledge;

export function KnowledgeReviewPanel({ noteId }: { noteId: number }) {
  const load = useCallback(() => getReviews(noteId), [noteId]);
  const history = useKnowledgeQuery(load);
  const action = useKnowledgeAction();

  return <section className="knowledge-review">
    <h2>{m.reviewHistory}</h2>
    {action.error && <p role="alert" className="knowledge-error">{action.error}</p>}
    {action.notice && <p role="status" className="knowledge-success">{action.notice}</p>}
    {history.loading ? <p role="status">{m.loading}</p> : history.error ? <p role="alert" className="knowledge-error">{history.error} {action.notice && m.reviewRefreshFailed} <button onClick={history.refresh}>{m.retry}</button></p> : <>
      <p>{m.reviewCount(history.data?.length ?? 0)}</p>
      {!!history.data?.length && <p>{m.latestReview}：<time>{history.data[0].reviewed_at.replace("T", " ")}</time></p>}
      <p className="knowledge-meta">{m.timeHint}</p>
      {history.data?.length === 0 ? <p>{m.noReviews}</p> : <ol>{history.data?.map((record) => <li key={record.id}><time>{record.reviewed_at.replace("T", " ")}</time></li>)}</ol>}
    </>}
    <button className="knowledge-primary knowledge-review-action" disabled={action.busy || history.loading || !!history.error} onClick={() => void action.run(async () => { await addReview(noteId); history.refresh(); }, m.reviewSaved)}>{action.busy ? m.saving : m.review}</button>
  </section>;
}
