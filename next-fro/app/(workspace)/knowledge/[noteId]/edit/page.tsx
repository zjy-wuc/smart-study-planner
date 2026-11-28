"use client";

import { useParams } from "next/navigation";
import { KnowledgeEditorPage } from "@/components/knowledge/KnowledgeEditor";

export default function EditKnowledgePage() {
  const { noteId } = useParams<{ noteId: string }>();
  return <KnowledgeEditorPage key={noteId} noteId={Number(noteId)} />;
}
