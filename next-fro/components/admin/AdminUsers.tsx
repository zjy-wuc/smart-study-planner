"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Search, RefreshCw, MoreHorizontal, X } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  actOnAdminUser,
  getAdminUser,
  getAdminUsers,
} from "@/services/admin.service";
import type {
  AdminUser,
  AdminUserDetail,
  PageResult,
  UserAction,
} from "@/types/admin";
import { messages } from "@/messages";

const m = messages.admin;
const time = (value: string) =>
  new Date(value).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" });

export function AdminUsers() {
  const [query, setQuery] = useState({
    page: 1,
    page_size: 20,
    keyword: "",
    status: "" as "" | "ACTIVE" | "DISABLED",
  });
  const [search, setSearch] = useState("");
  const [result, setResult] = useState<PageResult<AdminUser> | null>(null);
  const [detail, setDetail] = useState<AdminUserDetail | null>(null);
  const [detailId, setDetailId] = useState<number | null>(null);
  const [detailError, setDetailError] = useState("");
  const [action, setAction] = useState<{
    user: AdminUser;
    kind: UserAction;
  } | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [revision, setRevision] = useState(0);
  const [urlReady, setUrlReady] = useState(false);
  const detailSequence = useRef(0);

  useEffect(() => {
    let live = true;
    const url = new URL(window.location.href);
    const page = Math.max(1, Number(url.searchParams.get("page")) || 1);
    const size = Number(url.searchParams.get("page_size"));
    const page_size = [20, 50, 100].includes(size) ? size : 20;
    const status = url.searchParams.get("status");
    const keyword = url.searchParams.get("keyword") ?? "";
    queueMicrotask(() => {
      if (!live) return;
      setQuery({
        page,
        page_size,
        status: status === "ACTIVE" || status === "DISABLED" ? status : "",
        keyword: keyword.includes("@") ? "" : keyword,
      });
      setSearch(keyword.includes("@") ? "" : keyword);
      setUrlReady(true);
    });
    return () => {
      live = false;
    };
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(
      () =>
        setQuery((current) =>
          current.keyword === search.trim()
            ? current
            : { ...current, page: 1, keyword: search.trim() },
        ),
      400,
    );
    return () => window.clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    if (!urlReady) return;
    const url = new URL(window.location.href);
    for (const key of ["page", "page_size", "status", "keyword"])
      url.searchParams.delete(key);
    if (query.page > 1) url.searchParams.set("page", String(query.page));
    if (query.page_size !== 20)
      url.searchParams.set("page_size", String(query.page_size));
    if (query.status) url.searchParams.set("status", query.status);
    if (query.keyword && !query.keyword.includes("@"))
      url.searchParams.set("keyword", query.keyword);
    window.history.replaceState(null, "", url.pathname + url.search);
  }, [query, urlReady]);

  useEffect(() => {
    if (!urlReady) return;
    let live = true;
    getAdminUsers({ ...query, status: query.status || undefined })
      .then((data) => {
        if (live) {
          setResult(data);
          setError("");
        }
      })
      .catch((err: unknown) => {
        if (live) setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      live = false;
    };
  }, [query, revision, urlReady]);

  const loadDetail = useCallback(async (id: number) => {
    const sequence = ++detailSequence.current;
    setDetailId(id);
    setDetail(null);
    setDetailError("");
    try {
      const data = await getAdminUser(id);
      if (detailSequence.current === sequence) setDetail(data);
    } catch (err) {
      if (detailSequence.current === sequence)
        setDetailError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  async function submitAction(event: React.FormEvent) {
    event.preventDefault();
    if (!action || busy) return;
    const trimmed = reason.trim();
    if (trimmed.length < 1 || trimmed.length > 200) {
      setError(m.reasonHint);
      return;
    }
    setBusy(true);
    setError("");
    try {
      const response = await actOnAdminUser(
        action.user.id,
        action.kind,
        trimmed,
      );
      setNotice(
        action.kind === "REVOKE_SESSIONS" && !response.changed
          ? m.nothingRevoked
          : m.actionDone,
      );
      setAction(null);
      setReason("");
      setRevision((value) => value + 1);
      if (detailId === action.user.id) void loadDetail(detailId);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  const openAction = (user: AdminUser, kind: UserAction) => {
    setAction({ user, kind });
    setReason("");
    setError("");
  };
  const actions = (user: AdminUser) =>
    user.role === "ADMIN" ? (
      <span className="admin-muted">{m.adminProtected}</span>
    ) : (
      <div className="admin-row-actions">
        <button
          onClick={() =>
            openAction(user, user.is_active ? "BAN_USER" : "UNBAN_USER")
          }
        >
          {user.is_active ? m.ban : m.unban}
        </button>
        {user.is_active && (
          <button onClick={() => openAction(user, "REVOKE_SESSIONS")}>
            {m.revoke}
          </button>
        )}
      </div>
    );
  return (
    <div className="admin-page">
      <div className="admin-page-head">
        <div>
          <h1>{m.users}</h1>
          <p>{m.searchHint}</p>
        </div>
        <button onClick={() => setRevision((value) => value + 1)}>
          <RefreshCw size={16} />
          {m.refresh}
        </button>
      </div>
      {notice && (
        <p className="admin-success" role="status">
          {notice}
        </p>
      )}
      <section className="admin-panel">
        <div className="admin-toolbar">
          <label className="admin-search">
            <Search size={17} />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  setQuery((current) => ({
                    ...current,
                    page: 1,
                    keyword: search.trim(),
                  }));
                }
              }}
              placeholder={m.search}
              aria-label={m.search}
            />
          </label>
          <select
            aria-label={m.status}
            value={query.status}
            onChange={(event) =>
              setQuery((current) => ({
                ...current,
                page: 1,
                status: event.target.value as typeof current.status,
              }))
            }
          >
            <option value="">{m.statusAll}</option>
            <option value="ACTIVE">{m.active}</option>
            <option value="DISABLED">{m.disabled}</option>
          </select>
        </div>
        {error && (
          <div className="admin-alert" role="alert">
            {error}
            <button onClick={() => setRevision((value) => value + 1)}>
              {m.retry}
            </button>
          </div>
        )}
        {!result && !error ? (
          <p className="admin-skeleton" role="status">
            {m.loading}
          </p>
        ) : (
          result && (
            <>
              <div className="admin-table-scroll">
                <table className="admin-table">
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>{m.account}</th>
                      <th>{m.nickname}</th>
                      <th>{m.email}</th>
                      <th>{m.role}</th>
                      <th>{m.status}</th>
                      <th>{m.registeredAt}</th>
                      <th>{m.actions}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.items.map((user) => (
                      <tr key={user.id}>
                        <td>{user.id}</td>
                        <td>{user.username}</td>
                        <td>{user.nickname || "—"}</td>
                        <td>{user.email}</td>
                        <td>{user.role}</td>
                        <td>
                          <span
                            className={`admin-pill ${user.is_active ? "ok" : "danger"}`}
                          >
                            {user.is_active ? m.active : m.disabled}
                          </span>
                        </td>
                        <td>{time(user.created_at)}</td>
                        <td>
                          <button
                            className="admin-link"
                            onClick={() => void loadDetail(user.id)}
                          >
                            {m.view}
                          </button>
                          <details className="admin-action-menu">
                            <summary aria-label={m.actions}>
                              <MoreHorizontal size={17} />
                            </summary>
                            {actions(user)}
                          </details>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {result.items.length === 0 && (
                  <p className="admin-empty">{m.empty}</p>
                )}
              </div>
              <div className="admin-pagination">
                <span>
                  {m.total} {result.total}
                </span>
                <select
                  value={query.page_size}
                  aria-label={m.page}
                  onChange={(event) =>
                    setQuery((current) => ({
                      ...current,
                      page: 1,
                      page_size: Number(event.target.value),
                    }))
                  }
                >
                  {[20, 50, 100].map((size) => (
                    <option key={size} value={size}>
                      {size} / {m.page}
                    </option>
                  ))}
                </select>
                <button
                  disabled={query.page <= 1}
                  onClick={() =>
                    setQuery((current) => ({
                      ...current,
                      page: current.page - 1,
                    }))
                  }
                >
                  ‹
                </button>
                <span>
                  {query.page} /{" "}
                  {Math.max(1, Math.ceil(result.total / query.page_size))}
                </span>
                <button
                  disabled={query.page * query.page_size >= result.total}
                  onClick={() =>
                    setQuery((current) => ({
                      ...current,
                      page: current.page + 1,
                    }))
                  }
                >
                  ›
                </button>
              </div>
            </>
          )
        )}
      </section>
      <Dialog
        open={detailId !== null}
        onOpenChange={(open) => {
          if (!open) {
            detailSequence.current++;
            setDetailId(null);
            setDetail(null);
          }
        }}
      >
        <DialogContent className="admin-sheet">
          <DialogHeader>
            <div className="admin-sheet-head">
              <DialogTitle>{m.detail}</DialogTitle>
              <button
                onClick={() => {
                  detailSequence.current++;
                  setDetailId(null);
                  setDetail(null);
                }}
                aria-label={messages.profile.closeDialog}
              >
                <X size={19} />
              </button>
            </div>
            <DialogDescription>
              {detail?.username ?? m.loading}
            </DialogDescription>
          </DialogHeader>
          {detailError && (
            <p className="admin-alert" role="alert">
              {detailError}
            </p>
          )}
          {!detail && !detailError && (
            <p className="admin-skeleton">{m.loading}</p>
          )}
          {detail && (
            <>
              <dl className="admin-detail-list">
                {(
                  [
                    ["ID", detail.id],
                    [m.account, detail.username],
                    [m.nickname, detail.nickname],
                    [m.email, detail.email],
                    [m.role, detail.role],
                    [m.status, detail.is_active ? m.active : m.disabled],
                    [m.registeredAt, time(detail.created_at)],
                    [m.activePlans, detail.statistics.active_plan_count],
                    [m.notes, detail.statistics.note_count],
                    [m.aiToday, detail.statistics.today_ai_requests],
                    [m.sessions, detail.statistics.active_session_count],
                  ] as [string, string | number | null][]
                ).map(([label, value]) => (
                  <div key={label}>
                    <dt>{label}</dt>
                    <dd>{value ?? m.nullValue}</dd>
                  </div>
                ))}
              </dl>
              {actions(detail)}
            </>
          )}
        </DialogContent>
      </Dialog>
      <Dialog
        open={action !== null}
        onOpenChange={(open) => {
          if (!open && !busy) {
            setAction(null);
            setReason("");
            setError("");
          }
        }}
      >
        <DialogContent className="admin-confirm">
          <DialogHeader>
            <DialogTitle>
              {action ? m.actionLabels[action.kind] : m.confirm}
            </DialogTitle>
            <DialogDescription>
              {action?.user.username} ·{" "}
              {action?.kind === "BAN_USER"
                ? m.banImpact
                : action?.kind === "UNBAN_USER"
                  ? m.unbanImpact
                  : m.revokeImpact}
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={(event) => void submitAction(event)}>
            <label>
              {m.reason}
              <textarea
                value={reason}
                maxLength={200}
                onChange={(event) => setReason(event.target.value)}
                required
              />
            </label>
            <small>{m.reasonHint}</small>
            {error && (
              <p className="admin-alert" role="alert">
                {error}
              </p>
            )}
            <div className="admin-dialog-actions">
              <button
                type="button"
                disabled={busy}
                onClick={() => {
                  setAction(null);
                  setReason("");
                }}
              >
                {m.cancel}
              </button>
              <button
                className={action?.kind === "BAN_USER" ? "danger" : "primary"}
                disabled={busy || !reason.trim()}
                type="submit"
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
