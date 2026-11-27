"use client";

import Link from "next/link";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts";
import {
  Users,
  BookOpen,
  ClipboardCheck,
  Sparkles,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { useAdminPoll } from "@/hooks/useAdminPoll";
import { getAdminDashboard } from "@/services/admin.service";
import { messages } from "@/messages";

const m = messages.admin;
const colors = ["#2867ce", "#2baea7", "#9674e8"];

export function AdminDashboard() {
  const { data, error, updatedAt, refresh } = useAdminPoll(
    getAdminDashboard,
    30000,
  );
  const overview = data?.overview;
  const stats = overview
    ? [
        { label: m.totalUsers, value: overview.total_users, icon: Users },
        {
          label: m.activeLearners,
          value: overview.learning_active_users_today,
          icon: BookOpen,
        },
        {
          label: m.todayCheckins,
          value: overview.today_checkins,
          icon: ClipboardCheck,
        },
        { label: m.aiToday, value: overview.today_ai_requests, icon: Sparkles },
      ]
    : [];
  const rest = overview
    ? ([
        [m.enabledUsers, overview.enabled_users],
        [m.disabledUsers, overview.disabled_users],
        [m.newUsers, overview.new_users_today],
        [m.totalCheckins, overview.total_checkins],
        [m.totalPlans, overview.total_plans],
        [m.activePlans, overview.active_plans],
        [m.totalNotes, overview.total_notes],
      ] as const)
    : [];
  const pie = data
    ? (["DRAFT", "ACTIVE", "ENDED"] as const).map((status) => ({
        name: { DRAFT: m.draft, ACTIVE: m.running, ENDED: m.ended }[status],
        value: data.plan_status_distribution[status],
      }))
    : [];
  return (
    <div className="admin-page">
      <div className="admin-page-head">
        <div>
          <h1>{m.overview}</h1>
          <p>{m.activeLearnersHint}</p>
        </div>
        <button onClick={() => void refresh()}>
          <RefreshCw size={16} />
          {m.refresh}
        </button>
      </div>
      {error && (
        <div className="admin-alert" role="alert">
          {data ? m.refreshFailed : error}
          <button onClick={() => void refresh()}>{m.retry}</button>
        </div>
      )}
      {!data ? (
        <div className="admin-skeleton" role="status">
          {m.loading}
        </div>
      ) : (
        <>
          <div className="admin-stat-grid">
            {stats.map(({ label, value, icon: Icon }) => (
              <div className="admin-stat" key={label}>
                <Icon size={19} />
                <span>{label}</span>
                <strong>{value.toLocaleString()}</strong>
              </div>
            ))}
          </div>
          <section className="admin-panel">
            <h2>{m.overview}</h2>
            <div className="admin-metric-list">
              {rest.map(([label, value]) => (
                <div key={label}>
                  <span>{label}</span>
                  <strong>{value.toLocaleString()}</strong>
                </div>
              ))}
            </div>
          </section>
          <div className="admin-two-col">
            <section className="admin-panel">
              <h2>{m.trend}</h2>
              {data.daily_trend.some(
                (day) =>
                  day.new_user_count > 0 ||
                  day.active_user_count > 0 ||
                  day.checkin_count > 0,
              ) ? (
                <div className="admin-chart">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={data.daily_trend}>
                      <CartesianGrid stroke="#e8eef6" vertical={false} />
                      <XAxis
                        dataKey="date"
                        tickFormatter={(v: string) => v.slice(5)}
                      />
                      <YAxis allowDecimals={false} />
                      <Tooltip />
                      <Legend />
                      <Line
                        name={m.newUsersTrend}
                        dataKey="new_user_count"
                        stroke={colors[0]}
                        strokeWidth={2.5}
                        dot
                      />
                      <Line
                        name={m.activeTrend}
                        dataKey="active_user_count"
                        stroke={colors[1]}
                        strokeWidth={2.5}
                        dot
                      />
                      <Line
                        name={m.checkinTrend}
                        dataKey="checkin_count"
                        stroke={colors[2]}
                        strokeWidth={2.5}
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
              <h2>{m.planDistribution}</h2>
              {pie.some((item) => item.value > 0) ? (
                <div className="admin-chart">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={pie}
                        dataKey="value"
                        nameKey="name"
                        innerRadius={68}
                        outerRadius={98}
                        paddingAngle={3}
                      >
                        {pie.map((item, index) => (
                          <Cell key={item.name} fill={colors[index]} />
                        ))}
                      </Pie>
                      <Tooltip />
                      <Legend />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <p className="admin-empty">{m.empty}</p>
              )}
            </section>
          </div>
          <section className="admin-panel">
            <h2>{m.quick}</h2>
            <div className="admin-quick">
              <Link href="/admin/users">
                <Users size={18} />
                {m.users}
              </Link>
              <Link href="/admin/ai">
                <Sparkles size={18} />
                {m.ai}
              </Link>
              <Link href="/admin/audit">
                <ShieldCheck size={18} />
                {m.audit}
              </Link>
            </div>
          </section>
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
    </div>
  );
}
