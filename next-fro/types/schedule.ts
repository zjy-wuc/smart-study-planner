
export type ScheduleEntryInput = {
  task_date: string;
  content?: string | null;
  target_quantity?: number | null;
};

export type ScheduleEntry = {
  id: number;
  step_id: number;
  task_date: string;
  content: string | null;
  target_quantity: number | null;
  sort_order: number;
};

export type ScheduleReplace = {
  entries: ScheduleEntryInput[];
};
