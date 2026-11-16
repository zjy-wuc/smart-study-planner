
import type {
  CheckinStatistics,
  PlanStatistics,
} from "@/types/statistics";

type Props = {
  checkins: CheckinStatistics;
  plans: PlanStatistics;
};

export function StatisticsSummary({
  checkins,
  plans,
}: Props) {
  const items = [
    {
      label: "累计打卡",
      value: checkins.total_count,
      unit: "次",
    },
    {
      label: "最近 7 天打卡",
      value: checkins.last_7_days_count,
      unit: "次",
    },
    {
      label: "最近 30 天打卡",
      value: checkins.last_30_days_count,
      unit: "次",
    },
    {
      label: "执行中的计划",
      value: plans.active_count,
      unit: "个",
    },
    {
      label: "已结束计划",
      value: plans.ended_count,
      unit: "个",
    },
  ];

  return (
    <section
      aria-labelledby="statistics-summary-title"
      className="space-y-3"
    >
      <h2
        id="statistics-summary-title"
        className="text-lg font-semibold"
      >
        学习数据概览
      </h2>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {items.map((item) => (
          <article
            key={item.label}
            className="rounded-xl border border-slate-200 bg-white p-5"
          >
            <h3 className="text-sm text-slate-600">
              {item.label}
            </h3>

            <p className="mt-3 text-3xl font-semibold text-slate-900">
              {item.value.toLocaleString("zh-CN")}

              <span className="ml-2 text-sm font-normal text-slate-500">
                {item.unit}
              </span>
            </p>

            {item.label === "已结束计划" && (
              <p className="mt-2 text-xs text-slate-500">
                含正常到期和提前结束的计划
              </p>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}
