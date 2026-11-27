
"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";

import {
  ArrowRight,
  Bell,
  ClipboardList,
  Clock3,
  RefreshCw,
  Settings2,
} from "lucide-react";

import { messages } from "@/messages";
import { getTodayUncheckedCount } from "@/services/tasks.service";
import { useReminderSettings } from "@/components/reminders/ReminderSettingsProvider";
import type { TodayUncheckedCount } from "@/types/reminder";

import "@/components/css/Reminders.css";

export default function RemindersPage() {
  const [summary, setSummary] =
    useState<TodayUncheckedCount | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const {
    settings,
    loadFailed,
    updateSettings,
  } = useReminderSettings();

  const loadSummary = useCallback(() => {
    void getTodayUncheckedCount()
      .then(setSummary)
      .catch((error) => {
        setSummary(null);
        setError(error instanceof Error ? error.message : messages.reminders.loadFailed);
      })
      .finally(() => setLoading(false));
  }, []);

  const refreshSummary = () => {
    setLoading(true);
    setError("");
    void loadSummary();
  };

  useEffect(() => {
    loadSummary();
  }, [loadSummary]);

  return (
    <div className="reminders-page">
      <header className="reminders-header">
        <div>
          <h1>{messages.reminders.title}</h1>
          <p>{messages.reminders.subtitle}</p>
        </div>

        <button
          type="button"
          className="reminders-refresh"
          onClick={refreshSummary}
          disabled={loading}
          aria-label={messages.reminders.refresh}
          title={messages.reminders.refresh}
        >
          <RefreshCw size={18} />
        </button>
      </header>

      <div className="reminders-layout">
        <section
          className="reminders-card reminders-overview"
          aria-labelledby="reminders-today-heading"
        >
          <div className="reminders-card-heading">
            <span className="reminders-icon">
              <ClipboardList size={20} />
            </span>

            <h2 id="reminders-today-heading">
              {messages.reminders.todayStatus}
            </h2>
          </div>

          <div className="reminders-summary" aria-live="polite">
            {loading ? (
              <p className="reminders-state" role="status">
                {messages.reminders.loading}
              </p>
            ) : error ? (
              <div className="reminders-message">
                <p role="alert">{error}</p>

                <button
                  type="button"
                  onClick={refreshSummary}
                  className="reminders-retry"
                >
                  {messages.reminders.retry}
                </button>
              </div>
            ) : summary ? (
              <>
                {summary.unchecked_count > 0 ? (
                  <>
                    <div className="reminders-count">
                      {summary.unchecked_count}
                    </div>

                    <h3>
                      {messages.reminders.uncheckedTasks(
                        summary.unchecked_count,
                      )}
                    </h3>

                    <p>
                      {messages.reminders.uncheckedDescription}
                    </p>
                  </>
                ) : (
                  <>
                    <div className="reminders-empty-icon">
                      <ClipboardList size={36} />
                    </div>

                    <h3>{messages.reminders.noUnchecked}</h3>

                    <p>
                      {messages.reminders.noUncheckedDescription}
                    </p>
                  </>
                )}

                <span className="reminders-date">
                  {messages.reminders.dateLabel}
                  {summary.date}
                </span>
              </>
            ) : null}
          </div>

          <Link
            href="/task/today"
            className="reminders-task-link"
          >
            {messages.reminders.viewTodayTasks}
            <ArrowRight size={18} />
          </Link>
        </section>

        <section
          className="reminders-card reminders-settings"
          aria-labelledby="reminders-settings-heading"
        >
          <div className="reminders-card-heading">
            <span className="reminders-icon">
              <Settings2 size={20} />
            </span>

            <h2 id="reminders-settings-heading">
              {messages.reminders.settingsTitle}
            </h2>
          </div>

          {settings ? (
            <>
              <div className="reminders-setting-row">
                <label htmlFor="reminders-enabled">
                  {messages.reminders.enabledLabel}
                </label>

                <input
                  id="reminders-enabled"
                  type="checkbox"
                  role="switch"
                  className="reminders-toggle"
                  checked={settings.enabled}
                  onChange={(event) =>
                    updateSettings({
                      enabled: event.target.checked,
                    })
                  }
                />
              </div>

              <div className="reminders-setting-divider" />

              <div className="reminders-time-block">
                <div className="reminders-time-heading">
                  <Clock3 size={18} />
                  <label htmlFor="reminders-time">
                    {messages.reminders.timeLabel}
                  </label>
                </div>

                <input
                  id="reminders-time"
                  type="time"
                  className="reminders-time-input"
                  value={settings.time}
                  step={60}
                  disabled={!settings.enabled}
                  onChange={(event) => {
                    if (event.target.value) {
                      updateSettings({
                        time: event.target.value,
                      });
                    }
                  }}
                />

                <p>{messages.reminders.timezone}</p>
              </div>

              <div className="reminders-settings-note">
                <Bell size={17} />

                <p>{messages.reminders.settingsPending}</p>
              </div>
            </>
          ) : (
            <p
              className="reminders-settings-status"
              role={loadFailed ? "alert" : "status"}
            >
              {loadFailed
                ? messages.reminders.settingsLoadFailed
                : messages.reminders.settingsLoading}
            </p>
          )}

          <p className="reminders-browser-note">
            {messages.reminders.browserOnly}
          </p>
        </section>
      </div>
    </div>
  );
}
