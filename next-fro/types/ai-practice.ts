export type PracticeQuestion = {
  id: string;
  type: "SINGLE_CHOICE" | "SHORT_ANSWER";
  stem: string;
  options?: Record<string, string>;
};

export type PracticeAnswer = { id: string; answer: string | null };

export type PracticeResultQuestion = PracticeQuestion & {
  correct_answer?: string;
  reference_answer?: string;
  explanation?: string;
  submitted_answer: string | null;
  score_percent: number;
  earned_points: number;
  status: "CORRECT" | "INCORRECT" | "PARTIAL" | "SKIPPED";
  feedback?: { mastered_points?: string[]; missing_points?: string[]; suggestion?: string } | null;
};

export type PracticeSummary = {
  id: number;
  note_id: number | null;
  note_title_snapshot: string;
  question_count: number;
  score: number;
  created_at: string;
  source_note_deleted: boolean;
};

export type PracticeRecord = PracticeSummary & { questions: PracticeResultQuestion[] };
export type PracticeList = { items: PracticeSummary[]; total: number; page: number; page_size: number };

export type GeneratedPractice = {
  status: "success";
  note_id: number;
  note_title: string;
  question_count: number;
  questions: PracticeQuestion[];
  practice_ticket: string;
  expires_in_seconds: number;
};
