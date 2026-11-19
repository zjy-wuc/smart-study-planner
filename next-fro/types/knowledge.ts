export type KnowledgeNote = {
  id: number;
  user_id: number;
  plan_id: number | null;
  step_id: number | null;
  title: string;
  content_md: string;
  tags: string[];
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
};

export type KnowledgeNoteCreate = Pick<KnowledgeNote, "title" | "content_md" | "tags" | "plan_id" | "step_id">;
export type KnowledgeNoteUpdate = Partial<KnowledgeNoteCreate>;
export type KnowledgeNoteList = { items: KnowledgeNote[]; total: number; page: number; page_size: number };
export type KnowledgeReview = { id: number; note_id: number; reviewed_at: string };
export type KnowledgeFilters = { keyword?: string; tag?: string; plan_id?: number; page: number; page_size: number };
