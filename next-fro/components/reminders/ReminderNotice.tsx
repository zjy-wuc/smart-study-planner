
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, BellRing, X } from "lucide-react";

import { messages } from "@/messages";
import { getTodayUncheckedCount } from "@/services/tasks.service";
import { useReminderSettings } from "./ReminderSettingsProvider";

import "@/components/css/ReminderNotice.css";

type Notice = {
  date: string;
  count: number;
};

// 使用北京时间，不依赖电脑的本地时区。
const beijingFormatter = new Intl.DateTimeFormat("en-US", {
  timeZone: "Asia/Shanghai",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

function getBeijingNow() {
  const parts = beijingFormatter.formatToParts(new Date());

  function getPart(type: string): string {
    return parts.find((part) => part.type === type)?.value ?? "";
  }

  const date = [
    getPart("year"),
    getPart("month"),
    getPart("day"),
  ].join("-");

  const minutes =
    Number(getPart("hour")) * 60 +
    Number(getPart("minute"));

  return { date, minutes };
}

// 每个用户只保存最后一次提醒的北京时间日期。
function shownKey(userId: string): string {
  return `smart-study-planner:reminder:last-shown:${userId}`;
}

function hasShownToday(
  userId: string,
  date: string,
): boolean {
  try {
    return localStorage.getItem(shownKey(userId)) === date;
  } catch {
    return false;
  }
}

// 成功占用当天的提醒机会，防止重复展示。
// Web Locks 用于协调同一浏览器的多个标签页。
async function claimReminder(
  userId: string,
  date: string,
): Promise<boolean> {
  function claim(): boolean {
    try {
      if (document.visibilityState !== "visible") {
        return false;
      }

      const key = shownKey(userId);

      if (localStorage.getItem(key) === date) {
        return false;
      }

      localStorage.setItem(key, date);

      return true;
    } catch {
      return false;
    }
  }

  if (navigator.locks) {
    return navigator.locks.request(
      `smart-study-planner:reminder:${userId}`,
      claim,
    );
  }

  return claim();
}

// 真正运行定时检查的组件。
function ReminderRunner({
  userId,
  time,
}: {
  userId: string;
  time: string;
}) {
  const [notice, setNotice] = useState<Notice | null>(null);

  useEffect(() => {
    let cancelled = false;
    let checking = false;
    let lastRequestAt = 0;

    const [hour, minute] = time.split(":").map(Number);

    const reminderMinutes = hour * 60 + minute;

    async function checkReminder() {
      if (cancelled || checking) {
        return;
      }

      const now = getBeijingNow();

      // 跨天时，清除昨天仍然显示的通知。
      setNotice((current) =>
        current?.date === now.date ? current : null,
      );

      // 标签页不可见时，不提前消耗提醒机会。
      if (document.visibilityState !== "visible") {
        return;
      }

      if (now.minutes < reminderMinutes) {
        return;
      }

      if (hasShownToday(userId, now.date)) {
        return;
      }

      // 避免返回 0 或接口失败时频繁请求。
      const currentTime = Date.now();

      if (currentTime - lastRequestAt < 5 * 60 * 1000) {
        return;
      }

      lastRequestAt = currentTime;
      checking = true;

      try {
        const result = await getTodayUncheckedCount();

        if (cancelled) {
          return;
        }

        const current = getBeijingNow();

        // 请求期间可能跨过午夜或切换标签页。
        if (
          document.visibilityState !== "visible" ||
          result.date !== current.date ||
          current.minutes < reminderMinutes ||
          result.unchecked_count <= 0
        ) {
          return;
        }

        const claimed = await claimReminder(
          userId,
          current.date,
        );

        if (cancelled || !claimed) {
          return;
        }

        setNotice({
          date: current.date,
          count: result.unchecked_count,
        });
      } catch {
        // 请求失败时不标记已提醒，之后允许重试。
      } finally {
        checking = false;
      }
    }

    function handleVisibility() {
      if (document.visibilityState === "visible") {
        void checkReminder();
      }
    }

    function handleFocus() {
      void checkReminder();
    }

    // 首次进入工作区立即判断。
    void checkReminder();

    // 每 30 秒检查时间，不代表每 30 秒请求 API。
    const timer = window.setInterval(
      () => void checkReminder(),
      30_000,
    );

    document.addEventListener(
      "visibilitychange",
      handleVisibility,
    );

    window.addEventListener("focus", handleFocus);

    return () => {
      cancelled = true;

      window.clearInterval(timer);

      document.removeEventListener(
        "visibilitychange",
        handleVisibility,
      );

      window.removeEventListener("focus", handleFocus);
    };
  }, [userId, time]);

  if (!notice) {
    return null;
  }

  function dismiss() {
    // 今日已提醒的日期已经保存在 localStorage。
    setNotice(null);
  }

  return (
    <aside
      className="reminder-notice"
      role="status"
      aria-live="polite"
      aria-label={messages.reminders.notificationTitle}
    >
      <div className="reminder-notice-header">
        <span className="reminder-notice-icon">
          <BellRing size={19} />
        </span>

        <strong>
          {messages.reminders.notificationTitle}
        </strong>

        <button
          type="button"
          className="reminder-notice-close"
          onClick={dismiss}
          aria-label={messages.reminders.notificationClose}
        >
          <X size={18} />
        </button>
      </div>

      <p className="reminder-notice-message">
        {messages.reminders.uncheckedTasks(notice.count)}
      </p>

      <div className="reminder-notice-actions">
        <button
          type="button"
          className="reminder-notice-later"
          onClick={dismiss}
        >
          {messages.reminders.notificationLater}
        </button>

        <Link
          href="/task/today"
          className="reminder-notice-link"
          onClick={dismiss}
        >
          {messages.reminders.viewTodayTasks}
          <ArrowRight size={15} />
        </Link>
      </div>
    </aside>
  );
}

// 外层组件负责读取 F2 设置。
// 关闭提醒时，Runner 会卸载并停止定时器。
export function ReminderNotice() {
  const { userId, settings } = useReminderSettings();

  if (!userId || !settings?.enabled) {
    return null;
  }

  return (
    <ReminderRunner
      key={`${userId}:${settings.time}`}
      userId={userId}
      time={settings.time}
    />
  );
}
