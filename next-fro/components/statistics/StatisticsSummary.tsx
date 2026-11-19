import { locale, messages } from "@/messages";

import type {
  CheckinStatistics,
} from "@/types/statistics";

type Props = {
  checkins: CheckinStatistics;
};

export function StatisticsSummary({
  checkins,
}: Props) {
  const items = [
    {
      label: messages.statistics.totalCheckins,
      value: checkins.total_count,
      unit: messages.common.timesUnit,
    },
    {
      label: messages.statistics.last7Checkins,
      value: checkins.last_7_days_count,
      unit: messages.common.timesUnit,
    },
    {
      label: messages.statistics.last30Checkins,
      value: checkins.last_30_days_count,
      unit: messages.common.timesUnit,
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
      >{messages.statistics.summaryTitle}</h2>

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
              {item.value.toLocaleString(locale)}

              <span className="ml-2 text-sm font-normal text-slate-500">
                {item.unit}
              </span>
            </p>

          </article>
        ))}
      </div>
    </section>
  );
}
