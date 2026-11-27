"use client";

import { useEffect, useState } from "react";
import { RefreshCw, X } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { getAdminAudit } from "@/services/admin.service";
import { auditChanges } from "@/lib/admin/audit";
import type { AdminAction, AuditLog, PageResult } from "@/types/admin";
import { messages } from "@/messages";

const m = messages.admin;
const formatTime = (value: string) =>
  new Date(value).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" });
const formatValue = (value: unknown, exists: boolean) =>
  !exists
    ? m.missing
    : value === null
      ? m.nullValue
      : typeof value === "boolean"
        ? value
          ? m.yes
          : m.no
        : typeof value === "object"
          ? JSON.stringify(value)
          : String(value);

export function AdminAudit() {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [action, setAction] = useState<AdminAction | "">("");
  const [result, setResult] = useState<PageResult<AuditLog> | null>(null);
  const [selected, setSelected] = useState<AuditLog | null>(null);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let live = true;
    void getAdminAudit({
      page,
      page_size: pageSize,
      action: action || undefined,
    })
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
  }, [page, pageSize, action, revision]);

  const before = selected?.before_data ?? {};
  const after = selected?.after_data ?? {};
  const { changed, resultOnly } = auditChanges(before, after);
  return (
    <div className="admin-page">
      <div className="admin-page-head">
        <div>
          <h1>{m.audit}</h1>
          <p>{m.changeDetails}</p>
        </div>
        <button onClick={() => setRevision((value) => value + 1)}>
          <RefreshCw size={16} />
          {m.refresh}
        </button>
      </div>
      <section className="admin-panel">
        <div className="admin-toolbar">
          <select
            aria-label={m.type}
            value={action}
            onChange={(event) => {
              setAction(event.target.value as AdminAction | "");
              setPage(1);
            }}
          >
            <option value="">{m.allActions}</option>
            {(Object.keys(m.actionLabels) as AdminAction[]).map((key) => (
              <option key={key} value={key}>
                {m.actionLabels[key]}
              </option>
            ))}
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
          <p className="admin-skeleton">{m.loading}</p>
        ) : (
          result && (
            <>
              <div className="admin-table-scroll">
                <table className="admin-table">
                  <thead>
                    <tr>
                      <th>{m.operationTime}</th>
                      <th>{m.operator}</th>
                      <th>{m.type}</th>
                      <th>{m.target}</th>
                      <th>{m.reason}</th>
                      <th>{m.actions}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.items.map((log) => (
                      <tr key={log.id}>
                        <td>{formatTime(log.created_at)}</td>
                        <td>{log.admin_username ?? `#${log.admin_id}`}</td>
                        <td>{m.actionLabels[log.action] ?? log.action}</td>
                        <td>
                          {log.target_type} #{log.target_id}
                        </td>
                        <td className="admin-reason-cell">{log.reason}</td>
                        <td>
                          <button
                            className="admin-link"
                            onClick={() => setSelected(log)}
                          >
                            {m.view}
                          </button>
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
                  value={pageSize}
                  aria-label={m.page}
                  onChange={(event) => {
                    setPageSize(Number(event.target.value));
                    setPage(1);
                  }}
                >
                  {[20, 50, 100].map((size) => (
                    <option key={size} value={size}>
                      {size} / {m.page}
                    </option>
                  ))}
                </select>
                <button disabled={page <= 1} onClick={() => setPage(page - 1)}>
                  ‹
                </button>
                <span>
                  {page} / {Math.max(1, Math.ceil(result.total / pageSize))}
                </span>
                <button
                  disabled={page * pageSize >= result.total}
                  onClick={() => setPage(page + 1)}
                >
                  ›
                </button>
              </div>
            </>
          )
        )}
      </section>
      <Dialog
        open={selected !== null}
        onOpenChange={(open) => {
          if (!open) setSelected(null);
        }}
      >
        <DialogContent className="admin-sheet">
          <DialogHeader>
            <div className="admin-sheet-head">
              <DialogTitle>{m.changeDetails}</DialogTitle>
              <button
                onClick={() => setSelected(null)}
                aria-label={messages.profile.closeDialog}
              >
                <X size={19} />
              </button>
            </div>
            <DialogDescription>
              {selected
                ? (m.actionLabels[selected.action] ?? selected.action)
                : ""}
            </DialogDescription>
          </DialogHeader>
          {selected && (
            <>
              <dl className="admin-detail-list">
                <div>
                  <dt>{m.operator}</dt>
                  <dd>{selected.admin_username ?? `#${selected.admin_id}`}</dd>
                </div>
                <div>
                  <dt>{m.operationTime}</dt>
                  <dd>{formatTime(selected.created_at)}</dd>
                </div>
                <div>
                  <dt>{m.target}</dt>
                  <dd>
                    {selected.target_type} #{selected.target_id}
                  </dd>
                </div>
                <div>
                  <dt>{m.reason}</dt>
                  <dd>{selected.reason}</dd>
                </div>
              </dl>
              <h3>{m.changeDetails}</h3>
              {changed.length ? (
                <div className="admin-table-scroll">
                  <table className="admin-table">
                    <thead>
                      <tr>
                        <th>{m.type}</th>
                        <th>{m.before}</th>
                        <th>{m.after}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {changed.map((key) => (
                        <tr key={key}>
                          <td>{m.fieldLabels[key] ?? key}</td>
                          <td>
                            {formatValue(
                              before[key],
                              Object.hasOwn(before, key),
                            )}
                          </td>
                          <td className="admin-changed">
                            {formatValue(after[key], Object.hasOwn(after, key))}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="admin-empty">{m.noChanges}</p>
              )}
              {resultOnly.length > 0 && (
                <>
                  <h3>{m.resultDetails}</h3>
                  <dl className="admin-detail-list">
                    {resultOnly.map((key) => (
                      <div key={key}>
                        <dt>{m.fieldLabels[key] ?? key}</dt>
                        <dd>{formatValue(after[key], true)}</dd>
                      </div>
                    ))}
                  </dl>
                </>
              )}
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
