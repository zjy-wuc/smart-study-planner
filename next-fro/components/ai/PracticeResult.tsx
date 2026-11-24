import { KnowledgeMarkdownPreview } from "@/components/knowledge/KnowledgeMarkdownPreview";
import { aiPractice as m } from "@/messages/zh-CN/ai-practice";
import type { PracticeRecord } from "@/types/ai-practice";


export function PracticeResult({ record }: { record: PracticeRecord }) {
  return <div className="ai-practice-result">
    <header className="ai-practice-result-heading">
      <div><h1>{m.result}</h1><p>{record.note_title_snapshot} · {record.question_count} {m.questionUnit}</p></div>
      <div className="ai-practice-score"><strong>{record.score}</strong><span>/ 100 · {m.score}</span></div>
      <div className="ai-practice-score-track" role="meter" aria-label={m.score} aria-valuemin={0} aria-valuemax={100} aria-valuenow={record.score}><span style={{ width: `${Math.max(0, Math.min(100, record.score))}%` }} /></div>
    </header>
    <div className="ai-practice-question-list">
      {record.questions.map((question, index) => <article key={question.id} className="ai-practice-question ai-practice-reviewed" data-status={question.status}>
        <div className="ai-practice-question-top"><span>{index + 1} · {question.type === "SINGLE_CHOICE" ? m.single : m.short}</span><strong>{m.statuses[question.status]}</strong></div>
        <KnowledgeMarkdownPreview content={question.stem} />
        {question.options && <div className="ai-practice-options-read">{Object.entries(question.options).map(([key, value]) => <p key={key}><b>{key}</b> {value}</p>)}</div>}
        <dl className="ai-practice-review-details">
          <div><dt>{m.yourAnswer}</dt><dd>{question.submitted_answer || m.emptyAnswer}</dd></div>
          <div><dt>{question.type === "SINGLE_CHOICE" ? m.correctAnswer : m.referenceAnswer}</dt><dd>{question.correct_answer ?? question.reference_answer ?? "—"}</dd></div>
          <div className="ai-practice-review-points"><dt>{m.points}</dt><dd>{question.earned_points} · {question.score_percent}%</dd></div>
        </dl>
        {(question.explanation || question.feedback) && <div className="ai-practice-review-feedback">
          {question.explanation && <div className="ai-practice-explanation"><h3>{m.explanation}</h3><KnowledgeMarkdownPreview content={question.explanation} /></div>}
          {!!question.feedback?.mastered_points?.length && <p><strong>{m.mastered}：</strong>{question.feedback.mastered_points.join("、")}</p>}
          {!!question.feedback?.missing_points?.length && <p><strong>{m.missing}：</strong>{question.feedback.missing_points.join("、")}</p>}
          {question.feedback?.suggestion && <p><strong>{m.suggestion}：</strong>{question.feedback.suggestion}</p>}
        </div>}
      </article>)}
    </div>
  </div>;
}
