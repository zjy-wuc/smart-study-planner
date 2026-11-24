import Link from "next/link";
import { aiPractice as m } from "@/messages/zh-CN/ai-practice";
import "@/components/css/AiPractice.css";

const entries = [
  { href: "/ai/practice", title: m.practice, description: m.practiceDesc, number: "01", featured: true },
  { href: "/ai/practice/history", title: m.history, description: m.historyDesc, number: "02" },
  { href: "/knowledge/new", title: m.organize, description: m.organizeDesc, number: "03" },
  { href: "/knowledge", title: m.qa, description: m.qaDesc, number: "04" },
];

export default function AiHome() {
  return <main className="ai-practice-page ai-practice-home"><header className="ai-practice-page-header"><div><h1>{m.title}</h1><p>{m.subtitle}</p></div></header><div className="ai-practice-home-list">{entries.map((entry) => <Link key={entry.href} href={entry.href} className={entry.featured ? "ai-practice-home-featured" : undefined}><span>{entry.number}</span><div><h2>{entry.title}</h2><p>{entry.description}</p></div><strong>{entry.featured ? m.start : m.go} →</strong></Link>)}</div></main>;
}
