import Markdown from "react-markdown";
import { messages } from "@/messages";

export function KnowledgeMarkdownPreview({ content }: { content: string }) {
  return <div className="knowledge-markdown">
    {content ? <Markdown skipHtml components={{ a: ({ href, children }) => <a href={href} target="_blank" rel="noopener noreferrer">{children}</a> }}>{content}</Markdown> : <p>{messages.knowledge.previewEmpty}</p>}
  </div>;
}
