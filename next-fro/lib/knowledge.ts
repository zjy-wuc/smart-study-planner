import { messages } from "@/messages";
import type { KnowledgeNoteCreate, KnowledgeNoteUpdate } from "@/types/knowledge";
import type { StepNode } from "@/types/step";

export function parseKnowledgeTags(text: string): string[] {
  const tags = text.split(/[,，]/).map((tag) => tag.trim()).filter(Boolean);
  if (tags.length > 20 || tags.some((tag) => Array.from(tag).length > 50)) {
    throw new Error(messages.knowledge.invalidTags);
  }
  return tags.filter((tag, index) => tags.findIndex((other) => other.toLowerCase() === tag.toLowerCase()) === index);
}

export function knowledgeLeaves(nodes: StepNode[], parents: string[] = []): { id: number; name: string }[] {
  return nodes.flatMap((node) => {
    const path = [...parents, node.name];
    return node.node_type === "LEAF" ? [{ id: node.id, name: path.join(" / ") }] : knowledgeLeaves(node.children, path);
  });
}

export function knowledgeChanges(before: KnowledgeNoteCreate, after: KnowledgeNoteCreate): KnowledgeNoteUpdate {
  const changes: KnowledgeNoteUpdate = {};
  if (before.title !== after.title) changes.title = after.title;
  if (before.content_md !== after.content_md) changes.content_md = after.content_md;
  if (JSON.stringify(before.tags) !== JSON.stringify(after.tags)) changes.tags = after.tags;
  if (before.plan_id !== after.plan_id) {
    changes.plan_id = after.plan_id;
    changes.step_id = after.step_id;
  } else if (before.step_id !== after.step_id) changes.step_id = after.step_id;
  return changes;
}
