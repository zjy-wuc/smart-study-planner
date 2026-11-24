"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { PracticeResult } from "@/components/ai/PracticeResult";
import { ConfirmDelete } from "@/components/ai/ConfirmDelete";
import { deletePractice, getPractice } from "@/services/ai-practice.service";
import type { PracticeRecord } from "@/types/ai-practice";
import { aiPractice as m } from "@/messages/zh-CN/ai-practice";
import "@/components/css/AiPractice.css";


export default function PracticeHistoryDetail() {
  const params = useParams<{ recordId: string }>();
  const router = useRouter();
  const id = Number(params.recordId);
  const validId = Number.isSafeInteger(id) && id > 0;
  const [record, setRecord] = useState<PracticeRecord | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);
  useEffect(() => {
    if (!validId) return;
    let live = true;
    getPractice(id).then((value) => { if (live) setRecord(value); }).catch((cause) => { if (live) setError(cause instanceof Error ? cause.message : m.failed); }).finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [id, validId]);
  async function remove() {
    setDeleting(true); setError("");
    try { await deletePractice(id); router.replace("/ai/practice/history"); }
    catch (cause) { setError(cause instanceof Error ? cause.message : m.failed); setDeleting(false); }
  }
  return <main className="ai-practice-page"><div className="ai-practice-detail-actions"><Link href="/ai/practice/history">← {m.back}</Link>{record && <ConfirmDelete disabled={deleting} onConfirm={() => void remove()} />}</div>{!validId ? <p role="alert">{m.noResult}</p> : loading ? <div className="ai-practice-skeleton ai-practice-skeleton-detail" role="status" aria-label={m.loading} /> : error ? <p role="alert" className="ai-practice-error">{error}</p> : record ? <PracticeResult record={record} /> : <p>{m.noResult}</p>}</main>;
}
