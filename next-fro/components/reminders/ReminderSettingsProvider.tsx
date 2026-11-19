
"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import { getCurrentUser } from "@/services/auth.service";

export type ReminderSettings = {
  enabled: boolean;
  time: string;
};

type ReminderSettingsContextValue = {
  userId: string | null;
  settings: ReminderSettings | null;
  loadFailed: boolean;
  updateSettings: (
    changes: Partial<ReminderSettings>,
  ) => void;
};

const DEFAULT_SETTINGS: ReminderSettings = {
  enabled: true,
  time: "22:00",
};

const ReminderSettingsContext =
  createContext<ReminderSettingsContextValue | null>(null);

function storageKey(userId: string): string {
  return `smart-study-planner:reminders:${userId}`;
}

function readSettings(userId: string): ReminderSettings {
  try {
    const raw = localStorage.getItem(storageKey(userId));

    if (!raw) {
      return { ...DEFAULT_SETTINGS };
    }

    const parsed: unknown = JSON.parse(raw);

    if (typeof parsed !== "object" || parsed === null) {
      return { ...DEFAULT_SETTINGS };
    }

    const value = parsed as Partial<ReminderSettings>;

    return {
      enabled:
        typeof value.enabled === "boolean"
          ? value.enabled
          : DEFAULT_SETTINGS.enabled,

      time:
        typeof value.time === "string" &&
        /^([01]\d|2[0-3]):[0-5]\d$/.test(value.time)
          ? value.time
          : DEFAULT_SETTINGS.time,
    };
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
}

export function ReminderSettingsProvider({
  children,
}: {
  children: ReactNode;
}) {
  const [userId, setUserId] = useState<string | null>(null);

  const [settings, setSettings] =
    useState<ReminderSettings | null>(null);

  const [loadFailed, setLoadFailed] = useState(false);

  // 首次挂载时，确定当前用户并读取他的提醒设置。
  useEffect(() => {
    let active = true;

    async function load() {
      try {
        const response = await getCurrentUser();

        if (!active) return;

        const id = String(response.data.id);

        setUserId(id);
        setSettings(readSettings(id));
      } catch {
        if (active) {
          setLoadFailed(true);
        }
      }
    }

    void load();

    return () => {
      active = false;
    };
  }, []);

  // 设置变化后自动保存。
  useEffect(() => {
    if (userId === null || settings === null) {
      return;
    }

    try {
      localStorage.setItem(
        storageKey(userId),
        JSON.stringify(settings),
      );
    } catch {
      // 浏览器禁止本地存储时，不影响页面继续使用。
    }
  }, [userId, settings]);

  const updateSettings = useCallback(
    (changes: Partial<ReminderSettings>) => {
      setSettings((current) =>
        current ? { ...current, ...changes } : current,
      );
    },
    [],
  );

  return (
    <ReminderSettingsContext.Provider
      value={{
  userId,
  settings,
  loadFailed,
  updateSettings,
}}
    >
      {children}
    </ReminderSettingsContext.Provider>
  );
}

export function useReminderSettings() {
  const context = useContext(ReminderSettingsContext);

  if (!context) {
    throw new Error(
      "useReminderSettings 必须在 ReminderSettingsProvider 内使用",
    );
  }

  return context;
}
