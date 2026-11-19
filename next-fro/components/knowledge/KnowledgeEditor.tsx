"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useDeferredValue, useEffect, useRef, useState } from "react";
import { messages } from "@/messages";
import { useKnowledgeAction, useKnowledgeQuery } from "@/hooks/useKnowledge";
import { addReview, createNote, deleteNote, getNote, getReviews, updateNote } from "@/services/knowledge.service";
import { listPlans } from "@/services/plans.service";
import { getPlanSteps } from "@/services/steps.service";
import { knowledgeChanges, knowledgeLeaves, parseKnowledgeTags } from "@/lib/knowledge";
import type { KnowledgeNote, KnowledgeNoteCreate } from "@/types/knowledge";
import { KnowledgeMarkdownPreview } from "./KnowledgeMarkdownPreview";
import "@/components/css/Knowledge.css";

const m = messages.knowledge;
const empty: KnowledgeNoteCreate = { title: "", content_md: "", tags: [], plan_id: null, step_id: null };

export function KnowledgeEditorPage({ noteId }: { noteId: number }) {
  const load = useCallback(() => {
    if (!Number.isSafeInteger(noteId) || noteId <= 0) return Promise.reject(new Error(m.invalidId));
    return getNote(noteId);
  }, [noteId]);
  const note = useKnowledgeQuery(load);
  if (note.loading) return <p role="status">{m.loading}</p>;
  if (note.error) return <div className="knowledge-page"><p role="alert">{note.error}</p><button onClick={note.refresh}>{m.retry}</button> <Link href="/knowledge">{m.back}</Link></div>;
  return note.data ? <KnowledgeEditor key={note.data.id} initial={note.data} /> : null;
}

function ReviewHistory({ noteId }: { noteId: number }) {
  const load = useCallback(() => getReviews(noteId), [noteId]);
  const history = useKnowledgeQuery(load);
  const action = useKnowledgeAction();
  return <section className="knowledge-review">
    <div className="knowledge-heading"><h2>{m.reviewHistory}</h2><button className="knowledge-primary" disabled={action.busy} onClick={() => void action.run(async () => { await addReview(noteId); history.refresh(); }, m.reviewSaved)}>{action.busy ? m.saving : m.review}</button></div>
    {action.error && <p role="alert" className="knowledge-error">{action.error}</p>}
    {action.notice && <p role="status" className="knowledge-success">{action.notice}</p>}
    {history.loading ? <p role="status">{m.loading}</p> : history.error ? <p role="alert" className="knowledge-error">{history.error} {action.notice && m.reviewRefreshFailed} <button onClick={history.refresh}>{m.retry}</button></p> : <>
      <p>{m.reviewCount(history.data?.length ?? 0)}</p>
      {!!history.data?.length && <p>{m.latestReview}：{history.data[0].reviewed_at.replace("T", " ")}</p>}
      <p className="knowledge-meta">{m.timeHint}</p>
      {history.data?.length === 0 ? <p>{m.noReviews}</p> : <ol>{history.data?.map((record) => <li key={record.id}><time>{record.reviewed_at.replace("T", " ")}</time></li>)}</ol>}
    </>}
  </section>;
}

export function KnowledgeEditor({ initial }: { initial?: KnowledgeNote }) {
  const router = useRouter();
  const [form, setForm] = useState<KnowledgeNoteCreate>(initial ?? empty);
  const [baseline, setBaseline] = useState<KnowledgeNoteCreate>(initial ?? empty);
  const [tags, setTags] = useState((initial?.tags ?? []).join(", "));
  const [tab, setTab] = useState("edit");
  const action = useKnowledgeAction();
  const plans = useKnowledgeQuery(listPlans);
  const loadSteps = useCallback(async () => ({
    planId: form.plan_id,
    leaves: form.plan_id === null ? [] : knowledgeLeaves(await getPlanSteps(form.plan_id)),
  }), [form.plan_id]);
  const steps = useKnowledgeQuery(loadSteps);
  const preview = useDeferredValue(form.content_md);
  const skipGuard = useRef(false);
  const dirty = JSON.stringify(form) !== JSON.stringify(baseline) || tags !== baseline.tags.join(", ");
  const leaves = steps.data?.planId === form.plan_id ? steps.data.leaves : [];

  // 站内链接、刷新/关闭窗口均保护未保存输入。成功保存或明确删除后允许跳转。
  useEffect(() => {
    if (!dirty) return;
    function beforeUnload(event: BeforeUnloadEvent) {
      if (skipGuard.current) return;
      event.preventDefault();
      event.returnValue = "";
    }
    function click(event: MouseEvent) {
      if (skipGuard.current || event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      const anchor = (event.target as Element).closest?.("a[href]");
      if (!(anchor instanceof HTMLAnchorElement) || anchor.target === "_blank" || anchor.hasAttribute("download")) return;
      const destination = new URL(anchor.href);
      if (destination.pathname === location.pathname && destination.search === location.search) return;
      if (!window.confirm(m.leaveConfirm)) { event.preventDefault(); event.stopPropagation(); }
    }
    // Navigation API 支持的浏览器同时保护前进/后退；不改写 Next.js history 状态。
    const navigation = (window as Window & { navigation?: EventTarget }).navigation;
    function navigate(event: Event) {
      const nav = event as Event & { navigationType?: string };
      if (nav.navigationType === "traverse" && event.cancelable && !skipGuard.current && !window.confirm(m.leaveConfirm)) event.preventDefault();
    }
    window.addEventListener("beforeunload", beforeUnload);
    document.addEventListener("click", click, true);
    navigation?.addEventListener("navigate", navigate);
    return () => {
      window.removeEventListener("beforeunload", beforeUnload);
      document.removeEventListener("click", click, true);
      navigation?.removeEventListener("navigate", navigate);
    };
  }, [dirty]);

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await action.run(async () => {
      const title = form.title.trim();
      if (!title || Array.from(title).length > 200) throw new Error(m.invalidTitle);
      const payload = { ...form, title, tags: parseKnowledgeTags(tags) };
      // 编辑时只提交改变的字段，避免用旧关联覆盖后台已解除的关联。
      const result = initial ? await updateNote(initial.id, knowledgeChanges(baseline, payload)) : await createNote(payload);
      skipGuard.current = true;
      setForm(result);
      setBaseline(result);
      setTags(result.tags.join(", "));
      if (!initial) router.replace(`/knowledge/${result.id}`);
    }, m.saved);
  }

  return <div className="knowledge-page">
    <header className="knowledge-heading"><h1>{initial ? m.edit : m.create}</h1><Link href="/knowledge">{m.back}</Link></header>
    {action.error && <p role="alert" className="knowledge-error">{action.error}</p>}
    {action.notice && <p role="status" className="knowledge-success">{action.notice}</p>}
    <form onSubmit={(event) => void save(event)} onChange={() => { skipGuard.current = false; }}>
      <fieldset disabled={action.busy} className="knowledge-fields">
        <label>{m.name}<input value={form.title} maxLength={200} required onChange={(event) => setForm({ ...form, title: event.target.value })} /></label>
        <div className="knowledge-attachments">
          <label>{m.tags}<input value={tags} onChange={(event) => setTags(event.target.value)} aria-describedby="knowledge-tags-hint" /><small id="knowledge-tags-hint">{m.tagHint}</small></label>
          <label>{m.plan}<select value={form.plan_id ?? ""} disabled={plans.loading || !!plans.error} onChange={(event) => setForm({ ...form, plan_id: event.target.value ? Number(event.target.value) : null, step_id: null })}>
            <option value="">{m.unattached}</option>
            {form.plan_id !== null && !plans.data?.some((plan) => plan.id === form.plan_id) && <option value={form.plan_id}>{m.unavailable}</option>}
            {plans.data?.map((plan) => <option key={plan.id} value={plan.id}>{plan.name}</option>)}
          </select></label>
          <label>{m.step}<select value={form.step_id ?? ""} disabled={form.plan_id === null || steps.loading || !!steps.error || steps.data?.planId !== form.plan_id} onChange={(event) => setForm({ ...form, step_id: event.target.value ? Number(event.target.value) : null })}>
            <option value="">{form.plan_id === null ? m.unattached : m.planOnly}</option>
            {form.step_id !== null && !leaves.some((leaf) => leaf.id === form.step_id) && <option value={form.step_id}>{m.unavailable}</option>}
            {leaves.map((leaf) => <option key={leaf.id} value={leaf.id}>{leaf.name}</option>)}
          </select></label>
        </div>
        {(plans.error || steps.error) && <p role="alert" className="knowledge-error">{m.associationError} <button type="button" onClick={() => { plans.refresh(); steps.refresh(); }}>{m.retry}</button></p>}
        <div className="knowledge-tabs" role="group" aria-label={m.content}>
          <button type="button" aria-pressed={tab === "edit"} onClick={() => setTab("edit")}>{m.write}</button>
          <button type="button" aria-pressed={tab === "preview"} onClick={() => setTab("preview")}>{m.preview}</button>
        </div>
        <div className="knowledge-editor-grid" data-tab={tab}>
          <label className="knowledge-write">{m.content}<textarea value={form.content_md} onChange={(event) => setForm({ ...form, content_md: event.target.value })} spellCheck={false} /></label>
          <section className="knowledge-preview" aria-label={m.preview}><h2>{m.preview}</h2><KnowledgeMarkdownPreview content={preview} /></section>
        </div>
        <div className="knowledge-actions knowledge-save">
          <button className="knowledge-primary" type="submit">{action.busy ? m.saving : m.save}</button>
          <Link href="/knowledge">{m.cancel}</Link>
          {dirty && <span className="knowledge-meta">{m.unsaved}</span>}
          {initial && <button type="button" onClick={() => {
            if (!window.confirm(m.deleteConfirm)) return;
            void action.run(async () => { await deleteNote(initial.id); skipGuard.current = true; router.replace("/knowledge/trash"); }, m.deleted);
          }}>{m.delete}</button>}
        </div>
      </fieldset>
    </form>
    {initial && <ReviewHistory noteId={initial.id} />}
  </div>;
}
