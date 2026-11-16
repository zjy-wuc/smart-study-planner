
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
      >
        连续打卡
      </h2>

      <p className="mt-4 text-4xl font-semibold text-slate-900">
        {streakDays}

        <span className="ml-2 text-base font-normal text-slate-500">
          天
        </span>
      </p>

      <p className="mt-3 text-sm text-slate-600">
        {checkedInToday
          ? "今天已打卡，连续记录已更新。"
          : "今天尚未打卡，可以在今天结束前继续打卡。"}
      </p>

      <p className="mt-2 text-xs text-slate-500">
        按北京时间自然日统计，每天成功打卡至少一次即可。
      </p>
    </section>
  );
}
