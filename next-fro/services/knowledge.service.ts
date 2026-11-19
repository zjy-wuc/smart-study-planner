import { apiFetch } from "@/lib/api/client";
import type { ApiResponse } from "@/types/api";
import type { KnowledgeFilters, KnowledgeNote, KnowledgeNoteCreate, KnowledgeNoteUpdate, KnowledgeNoteList, KnowledgeReview } from "@/types/knowledge";

export async function listNotes(filters: KnowledgeFilters, trash = false): Promise<KnowledgeNoteList> {
  const query = new URLSearchParams({ page: String(filters.page), page_size: String(filters.page_size) });
  if (!trash) {
    if (filters.keyword) query.set("keyword", filters.keyword);
    if (filters.tag) query.set("tag", filters.tag);
    if (filters.plan_id) query.set("plan_id", String(filters.plan_id));
  }
  return (await apiFetch<ApiResponse<KnowledgeNoteList>>(`/notes${trash ? "/trash" : ""}?${query}`)).data;
}

export async function getNote(id: number): Promise<KnowledgeNote> {
  return (await apiFetch<ApiResponse<KnowledgeNote>>(`/notes/${id}`)).data;
}

export async function createNote(data: KnowledgeNoteCreate): Promise<KnowledgeNote> {
  return (await apiFetch<ApiResponse<KnowledgeNote>>("/notes", { method: "POST", body: JSON.stringify(data) })).data;
}

export async function updateNote(id: number, data: KnowledgeNoteUpdate): Promise<KnowledgeNote> {
  return (await apiFetch<ApiResponse<KnowledgeNote>>(`/notes/${id}`, { method: "PATCH", body: JSON.stringify(data) })).data;
}

export async function deleteNote(id: number): Promise<void> {
  await apiFetch(`/notes/${id}`, { method: "DELETE" });
}

export async function restoreNote(id: number): Promise<KnowledgeNote> {
  return (await apiFetch<ApiResponse<KnowledgeNote>>(`/notes/${id}/restore`, { method: "POST" })).data;
}

export async function addReview(id: number): Promise<KnowledgeReview> {
  return (await apiFetch<ApiResponse<KnowledgeReview>>(`/notes/${id}/reviews`, { method: "POST" })).data;
}

export async function getReviews(id: number): Promise<KnowledgeReview[]> {
  return (await apiFetch<ApiResponse<KnowledgeReview[]>>(`/notes/${id}/reviews`)).data;
}
