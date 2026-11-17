import { messages } from "@/messages";

type Props = {
  streakDays: number;
  todayCheckinCount: number;
};

export function StreakCard({
  streakDays,
  todayCheckinCount,
}: Props) {
  const checkedInToday = todayCheckinCount > 0;

  return (
    <section
      aria-labelledby="streak-title"
      className="rounded-xl border border-slate-200 bg-white p-5"
    >
      <h2
        id="streak-title"
        className="text-lg font-semibold text-slate-900"
      >{messages.statistics.streakTitle}</h2>

      <p className="mt-4 text-4xl font-semibold text-slate-900">
        {streakDays}

        <span className="ml-2 text-base font-normal text-slate-500">{messages.common.daysUnit}</span>
      </p>

      <p className="mt-3 text-sm text-slate-600">
        {checkedInToday
          ? messages.statistics.checkedInToday
          : messages.statistics.notCheckedInToday}
      </p>

      <p className="mt-2 text-xs text-slate-500">{messages.statistics.businessDayHint}</p>
    </section>
  );
}
