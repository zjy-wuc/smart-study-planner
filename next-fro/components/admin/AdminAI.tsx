"use client";

import { useEffect, useState } from "react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
} from "recharts";
import { RefreshCw, Settings2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  getAdminAIConfig,
  getAdminAIStatistics,
  updateAdminAIConfig,
} from "@/services/admin.service";
import { useAdminPoll } from "@/hooks/useAdminPoll";
import type { AIConfig } from "@/types/admin";
import { messages } from "@/messages";

const m = messages.admin;

export function AdminAI() {
  const {
    data: stats,
    error: statsError,
    updatedAt,
    refresh,
  } = useAdminPoll(getAdminAIStatistics, 15000);
  const [config, setConfig] = useState<AIConfig | null>(null);
  const [configError, setConfigError] = useState("");
  const [notice, setNotice] = useState("");
  const [editing, setEditing] = useState(false);
  const [enabled, setEnabled] = useState(false);
  const [userLimit, setUserLimit] = useState("");
  const [globalLimit, setGlobalLimit] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  async function refreshConfig() {
    try {
      setConfig(await getAdminAIConfig());
      setConfigError("");
    } catch (err) {
      setConfigError(err instanceof Error ? err.message : String(err));
    }
  }
  useEffect(() => {
    let live = true;
    void getAdminAIConfig()
      .then((value) => {
        if (live) setConfig(value);
      })
      .catch((err: unknown) => {
        if (live)
          setConfigError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      live = false;
    };
  }, []);

  function openEditor() {
    if (!config) return;
    setEnabled(config.enabled);
    setUserLimit(String(config.user_daily_limit));
    setGlobalLimit(String(config.global_daily_limit));
    setReason("");
    setConfigError("");
    setEditing(true);
  }
  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!config || busy) return;
    const user = Number(userLimit),
      global = Number(globalLimit),
      why = reason.trim();
    if (
      !Number.isSafeInteger(user) ||
      !Number.isSafeInteger(global) ||
      user < 1 ||
      global < 1 ||
      user > global ||
      user > config.hard_user_daily_limit ||
      global > config.hard_global_daily_limit
    ) {
      setConfigError(m.invalidLimit);
      return;
    }
    if (!why || why.length > 200) {
      setConfigError(m.reasonHint);
      return;
    }
    const changes: {
      enabled?: boolean;
      user_daily_limit?: number;
      global_daily_limit?: number;
      reason: string;
    } = { reason: why };
    if (enabled !== config.enabled) changes.enabled = enabled;
    if (user !== config.user_daily_limit) changes.user_daily_limit = user;
    if (global !== config.global_daily_limit)
      changes.global_daily_limit = global;
    if (Object.keys(changes).length === 1) {
      setConfigError(m.noChange);
      return;
    }
    setBusy(true);
    setConfigError("");
    try {
      const updated = await updateAdminAIConfig(changes);
      setConfig(updated);
      setNotice(updated.changed ? m.configSaved : m.configUnchanged);
      setEditing(false);
      setReason("");
      void refresh();
    } catch (err) {
      setConfigError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  const used = stats?.overview.today_used ?? 0;
  const limit =
    stats?.config.global_daily_limit ??
    config?.effective_global_daily_limit ??
    0;
  const percent = limit > 0 ? (used / limit) * 100 : 0;
  const state = stats
    ? !stats.config.configured_enabled
      ? m.aiOff
      : stats.config.model_configured
        ? m.aiReady
        : m.aiNoModel
    : m.loading;
  const statusRows = stats ? Object.entries(stats.status_distribution) : [];
  const operationRows = stats
    ? Object.entries(stats.operation_distribution)
    : [];
  return (
    <div className="admin-page">
      <div className="admin-page-head">
        <div>
          <h1>{m.ai}</h1>
          <p>{m.notHealth}</p>
        </div>
        <button
          onClick={() => {
            void refresh();
            void refreshConfig();
          }}
        >
          <RefreshCw size={16} />
          {m.refresh}
        </button>
      </div>
      {notice && (
        <p className="admin-success" role="status">
          {notice}
        </p>
      )}
      {statsError && (
        <div className="admin-alert" role="alert">
          {stats ? m.refreshFailed : statsError}
          <button onClick={() => void refresh()}>{m.retry}</button>
        </div>
      )}
      {configError && !editing && (
        <div className="admin-alert" role="alert">
          {configError}
          <button onClick={() => void refreshConfig()}>{m.retry}</button>
        </div>
      )}
      {!stats ? (
        <p className="admin-skeleton" role="status">
          {m.loading}
        </p>
      ) : (
        <>
          <section className="admin-panel admin-ai-state">
            <div>
              <h2>{m.aiState}</h2>
              <strong className={stats.config.enabled ? "ok" : "warn"}>
                {state}
              </strong>
              <p>{m.notHealth}</p>
            </div>
            <div className="admin-metric-list">
              <div>
                <span>{m.configuredSwitch}</span>
                <strong>
                  {stats.config.configured_enabled ? m.yes : m.no}
                </strong>
              </div>
              <div>
                <span>{m.modelConfigured}</span>
                <strong>{stats.config.model_configured ? m.yes : m.no}</strong>
              </div>
              <div>
                <span>{m.effectiveState}</span>
                <strong>{stats.config.enabled ? m.yes : m.no}</strong>
              </div>
            </div>
          </section>
          <div className="admin-stat-grid">
            {(
              [
                [m.todayUsed, used],
                [m.todayRemaining, stats.overview.today_remaining],
                [m.todaySuccess, stats.overview.today_success],
                [m.todayFailed, stats.overview.today_failed],
                [m.todayCancelled, stats.overview.today_cancelled],
                [m.activeConcurrent, stats.overview.current_active],
              ] as [string, number][]
            ).map(([label, value]) => (
              <div className="admin-stat" key={label}>
                <span>{label}</span>
                <strong>{value.toLocaleString()}</strong>
              </div>
            ))}
          </div>
          <section className="admin-panel">
            <h2>{m.quota}</h2>
            <div className="admin-quota-line">
              <strong>
                {used.toLocaleString()} / {limit.toLocaleString()}
              </strong>
              <span>{percent.toFixed(1)}%</span>
            </div>
            <div className="admin-progress">
              <span
                style={{
                  width: `${Math.min(100, percent)}%`,
                  background:
                    percent >= 100
                      ? "#d34848"
                      : percent >= 80
                        ? "#e8992d"
                        : "#2867ce",
                }}
              />
            </div>
            {percent >= 100 && <p className="admin-alert">{m.quotaWarning}</p>}
          </section>
          <div className="admin-two-col">
            <section className="admin-panel">
              <h2>{m.requestTrend}</h2>
              {stats.daily_trend.some((day) => day.request_count > 0) ? (
                <div className="admin-chart">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={stats.daily_trend}>
                      <CartesianGrid stroke="#e8eef6" vertical={false} />
                      <XAxis
                        dataKey="date"
                        tickFormatter={(v: string) => v.slice(5)}
                      />
                      <YAxis allowDecimals={false} />
                      <Tooltip />
                      <Line
                        dataKey="request_count"
                        name={m.aiToday}
                        stroke="#2867ce"
                        strokeWidth={3}
                        dot
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <p className="admin-empty">{m.noTrend}</p>
              )}
            </section>
            <section className="admin-panel">
              <h2>{m.requestStatus}</h2>
              <div className="admin-breakdown">
                {statusRows
                  .filter(([, value]) => value > 0)
                  .map(([key, value]) => (
                    <div key={key}>
                      <span>{m.statusLabels[key] ?? key}</span>
                      <strong>{value}</strong>
                    </div>
                  ))}
              </div>
              {!statusRows.some(([, value]) => value > 0) && (
                <p className="admin-empty">{m.empty}</p>
              )}
            </section>
          </div>
          <div className="admin-two-col">
            <section className="admin-panel">
              <h2>{m.operationDistribution}</h2>
              <div className="admin-breakdown">
                {operationRows
                  .filter(([, value]) => value > 0)
                  .map(([key, value]) => (
                    <div key={key}>
                      <span>{m.operationLabels[key] ?? key}</span>
                      <strong>{value}</strong>
                    </div>
                  ))}
              </div>
              {!operationRows.some(([, value]) => value > 0) && (
                <p className="admin-empty">{m.empty}</p>
              )}
            </section>
            <section className="admin-panel">
              <div className="admin-section-head">
                <h2>{m.config}</h2>
                <button onClick={openEditor} disabled={!config}>
                  <Settings2 size={16} />
                  {m.editConfig}
                </button>
              </div>
              {config && (
                <div className="admin-breakdown">
                  <div>
                    <span>{m.configuredSwitch}</span>
                    <strong>{config.enabled ? m.yes : m.no}</strong>
                  </div>
                  <div>
                    <span>{m.userLimit}</span>
                    <strong>{config.user_daily_limit}</strong>
                  </div>
                  <div>
                    <span>{m.globalLimit}</span>
                    <strong>{config.global_daily_limit}</strong>
                  </div>
                </div>
              )}
            </section>
          </div>
          {config && (
            <section className="admin-panel">
              <h2>{m.safety}</h2>
              <div className="admin-metric-list">
                {(
                  [
                    [m.hardUserLimit, config.hard_user_daily_limit],
                    [m.hardGlobalLimit, config.hard_global_daily_limit],
                    [
                      m.userRate,
                      `${config.user_rate_limit} / ${config.rate_window_seconds}s`,
                    ],
                    [m.userConcurrency, config.user_concurrency],
                    [m.globalConcurrency, config.global_concurrency],
                  ] as [string, string | number][]
                ).map(([label, value]) => (
                  <div key={label}>
                    <span>{label}</span>
                    <strong>{value}</strong>
                  </div>
                ))}
              </div>
            </section>
          )}
          {updatedAt && (
            <p className="admin-updated">
              {m.refreshedAt(
                updatedAt.toLocaleTimeString("zh-CN", {
                  timeZone: "Asia/Shanghai",
                }),
              )}
            </p>
          )}
        </>
      )}
      <Dialog
        open={editing}
        onOpenChange={(open) => {
          if (!open && !busy) {
            setEditing(false);
            setReason("");
            setConfigError("");
          }
        }}
      >
        <DialogContent className="admin-confirm">
          <DialogHeader>
            <DialogTitle>{m.editConfig}</DialogTitle>
            <DialogDescription>{m.config}</DialogDescription>
          </DialogHeader>
          <form onSubmit={(event) => void save(event)}>
            <label className="admin-switch">
              <input
                type="checkbox"
                checked={enabled}
                onChange={(event) => setEnabled(event.target.checked)}
              />
              {m.configuredSwitch}
            </label>
            <label>
              {m.userLimit}
              <input
                type="number"
                min={1}
                max={config?.hard_user_daily_limit}
                value={userLimit}
                onChange={(event) => setUserLimit(event.target.value)}
                required
              />
            </label>
            <label>
              {m.globalLimit}
              <input
                type="number"
                min={1}
                max={config?.hard_global_daily_limit}
                value={globalLimit}
                onChange={(event) => setGlobalLimit(event.target.value)}
                required
              />
            </label>
            {config?.enabled && !enabled && (
              <p className="admin-alert">{m.disableImpact}</p>
            )}
            <label>
              {m.reason}
              <textarea
                value={reason}
                maxLength={200}
                onChange={(event) => setReason(event.target.value)}
                required
              />
            </label>
            {configError && (
              <p role="alert" className="admin-alert">
                {configError}
              </p>
            )}
            <div className="admin-dialog-actions">
              <button
                type="button"
                disabled={busy}
                onClick={() => setEditing(false)}
              >
                {m.cancel}
              </button>
              <button
                type="submit"
                className="primary"
                disabled={busy || !reason.trim()}
              >
                {busy ? m.saving : m.confirm}
              </button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
