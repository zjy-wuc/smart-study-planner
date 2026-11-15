
export type PlanStatus = "DRAFT" | "ACTIVE" | "ENDED";

export type Plan = {
  id: number;
  user_id: number;
  name: string;
  description: string | null;
  start_date: string;
  end_date: string;
  status: PlanStatus;
  started_at: string | null;
  ended_at: string | null;
  deleted_at: string | null;
  created_at: string;
  updated_at: string;
};

export type PlanCreate = {
  name: string;
  description?: string | null;
  start_date: string;
  end_date: string;
};

export type PlanUpdate = {
  name?: string;
  description?: string | null;
  start_date?: string;
  end_date?: string;
};



export type EndPlanResult = {
  plan_id: number;
  status: "ENDED";

  end_mode: "EARLY" | "NORMAL_EXPIRED";

  ended_task_count: number;
  deleted_task_count: number;
};




