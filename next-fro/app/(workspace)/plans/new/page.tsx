
"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { PlanForm } from "@/components/plans/PlanForm";
import { createPlan } from "@/services/plans.service";

import type { PlanCreate } from "@/types/plan";


export default function CreatePlanPage() {
  const router = useRouter();

  async function handleCreate(data: PlanCreate) {
    const created = await createPlan(data);

    // 创建成功后，进入刚创建的计划详情
    router.push(`/plans/${created.id}`);
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <Link
          href="/plans"
          className="text-sm text-blue-700"
        >
          返回我的计划
        </Link>

        <h1 className="mt-3 text-2xl font-bold">
          创建学习计划
        </h1>

        <p className="mt-2 text-slate-500">
          先创建草稿，再配置具体学习步骤。
        </p>
      </div>

      <PlanForm
        onSubmit={handleCreate}
        submitLabel="创建计划"
      />
    </div>
  );
}
