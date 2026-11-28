"use client";

import { useParams } from "next/navigation";
import { KnowledgeNotePreview } from "@/components/knowledge/KnowledgeNotePreview";

export default function KnowledgeNotePage() {
  const { noteId } = useParams<{ noteId: string }>();
  return <KnowledgeNotePreview key={noteId} noteId={Number(noteId)} />;
}
