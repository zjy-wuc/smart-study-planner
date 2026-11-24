import { Suspense } from "react";
import { PracticeFlow } from "@/components/ai/PracticeFlow";
import { aiPractice } from "@/messages/zh-CN/ai-practice";

export default function AiPracticePage() {
  return <Suspense fallback={<p role="status">{aiPractice.loading}</p>}><PracticeFlow /></Suspense>;
}
