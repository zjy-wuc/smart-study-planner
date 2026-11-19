"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { messages } from "@/messages";
import { useKnowledgeAction, useKnowledgeQuery } from "@/hooks/useKnowledge";
import { deleteNote, listNotes, restoreNote } from "@/services/knowledge.service";
import { listPlans } from "@/services/plans.service";
import type { KnowledgeFilters } from "@/types/knowledge";
import "@/components/css/Knowledge.css";

const m = messages.knowledge;
export function KnowledgeNoteList({ trash = false }: { trash?: boolean }) {
  const [filters, setFilters] = useState<KnowledgeFilters>({ page: 1, page_size: 12 });
  const [keyword, setKeyword] = useState("");
  const [tag, setTag] = useState("");
  const [plan, setPlan] = useState("");
  const load = useCallback(() => listNotes(filters, trash), [filters, trash]);
  const notes = useKnowledgeQuery(load);
  const plans = useKnowledgeQuery(listPlans);
  const action = useKnowledgeAction();
  const pages = Math.max(1, Math.ceil((notes.data?.total ?? 0) / filters.page_size));

  async function mutate(id: number) {
    if (!trash && !window.confirm(m.deleteConfirm)) return;
    await action.run(async () => {
      if (trash) await restoreNote(id);
      else await deleteNote(id);
      if (notes.data?.items.length === 1 && filters.page > 1) {
        setFilters((current) => ({ ...current, page: current.page - 1 }));
      } else notes.refresh();
    }, trash ? m.restored : m.deleted);
  }

  return (
    <div className="knowledge-page">
      <header className="knowledge-heading">
        <div><h1>{trash ? m.trash : m.title}</h1><p>{m.description}</p></div>
        <div className="knowledge-actions">
          <button type="button" onClick={notes.refresh} disabled={notes.loading}>{m.refresh}</button>
          <Link href={trash ? "/knowledge" : "/knowledge/trash"}>{trash ? m.back : m.trash}</Link>
          {!trash && <Link className="knowledge-primary" href="/knowledge/new">{m.create}</Link>}
        </div>
      </header>
      {!trash && <form className="knowledge-filters" onSubmit={(event) => {
        event.preventDefault();
        setFilters({ page: 1, page_size: 12, keyword: keyword.trim(), tag: tag.trim(), plan_id: plan ? Number(plan) : undefined });
      }}>
        <label>{m.search}<input value={keyword} maxLength={100} onChange={(event) => setKeyword(event.target.value)} /></label>
        <label>{m.tagFilter}<input value={tag} maxLength={50} onChange={(event) => setTag(event.target.value)} /></label>
        <label>{m.planFilter}<select value={plan} onChange={(event) => setPlan(event.target.value)} disabled={plans.loading || !!plans.error}>
          <option value="">{m.allPlans}</option>{plans.data?.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select></label>
        <button className="knowledge-primary" type="submit">{m.apply}</button>
        <button type="button" onClick={() => { setKeyword(""); setTag(""); setPlan(""); setFilters({ page: 1, page_size: 12 }); }}>{m.reset}</button>
      </form>}
      {plans.error && !trash && <p className="knowledge-error" role="alert">{m.associationError} <button onClick={plans.refresh}>{m.retry}</button></p>}
      {action.error && <p className="knowledge-error" role="alert">{action.error}</p>}
      {action.notice && <p className="knowledge-success" role="status">{action.notice}</p>}
      {notes.loading ? <p role="status">{m.loading}</p> : notes.error ? <p className="knowledge-error" role="alert">{notes.error} <button onClick={notes.refresh}>{m.retry}</button></p> : <>
        {notes.data?.items.length === 0 ? <p className="knowledge-empty">{trash ? m.emptyTrash : filters.keyword || filters.tag || filters.plan_id ? m.noResults : m.empty}</p> : <div className="knowledge-cards">
          {notes.data?.items.map((note) => <article className="knowledge-card" key={note.id}>
            <h2>{trash ? note.title : <Link href={`/knowledge/${note.id}`}>{note.title}</Link>}</h2>
            {!trash && <p className="knowledge-excerpt">{note.content_md.slice(0, 180) || m.noContent}</p>}
            <div className="knowledge-tags">{note.tags.map((value) => <span key={value}>{value}</span>)}</div>
            {!trash && <p className="knowledge-meta">{m.plan}：{note.plan_id === null ? m.unattached : plans.data?.find((item) => item.id === note.plan_id)?.name ?? m.unavailable}</p>}
            <p className="knowledge-meta">{trash ? m.deletedAt : m.updated}：<time>{(trash ? note.deleted_at : note.updated_at)?.replace("T", " ")}</time></p>
            <div className="knowledge-actions">{!trash && <Link href={`/knowledge/${note.id}`}>{m.edit}</Link>}
              <button type="button" disabled={action.busy} onClick={() => void mutate(note.id)}>{action.busy ? m.saving : trash ? m.restore : m.delete}</button>
            </div>
          </article>)}
        </div>}
        <nav className="knowledge-pagination" aria-label={m.title}>
          <button disabled={filters.page <= 1 || action.busy} onClick={() => setFilters((current) => ({ ...current, page: current.page - 1 }))}>{m.previous}</button>
          <span>{m.page(filters.page, pages, notes.data?.total ?? 0)}</span>
          <button disabled={filters.page >= pages || action.busy} onClick={() => setFilters((current) => ({ ...current, page: current.page + 1 }))}>{m.next}</button>
        </nav>
      </>}
    </div>
  );
}
