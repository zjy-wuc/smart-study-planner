"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import * as AlertDialog from "@radix-ui/react-alert-dialog";
import {
  Camera,
  ChevronDown,
  ChevronRight,
  KeyRound,
  Mail,
  MonitorSmartphone,
  Pencil,
  ShieldCheck,
  UserRound,
  X,
} from "lucide-react";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useAuth } from "@/contexts/AuthContext";
import {
  changeEmail,
  changePassword,
  deleteAvatar,
  getCurrentUser,
  listSessions,
  logoutAllSessions,
  logoutUser,
  revokeOtherSessions,
  revokeSession,
  sendEmailCode,
  updateNickname,
  uploadAvatar,
} from "@/services/auth.service";
import { API_BASE_URL } from "@/lib/api/client";
import { messages } from "@/messages";
import type { LoginSession } from "@/types/auth";
import { LandscapeScene } from "@/components/common/LandscapeScene";
import "@/components/css/Profile.css";
import "@/components/css/ProfileAuth.css";

const p = messages.profile;
const a = messages.auth;
type SessionAction =
  | { kind: "single"; familyId: string; deviceName: string }
  | { kind: "others" }
  | { kind: "all" };

type SecurityField =
  | "oldPassword"
  | "newPassword"
  | "emailPassword"
  | "oldCode"
  | "newEmail"
  | "newCode";

export default function UserProfile() {
  const router = useRouter();
  const auth = useAuth();
  const user = auth.user;
  const [nickname, setNickname] = useState<string | null>(null);
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [emailPassword, setEmailPassword] = useState("");
  const [oldCode, setOldCode] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [newCode, setNewCode] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [sessionAction, setSessionAction] = useState<SessionAction | null>(
    null,
  );
  const [sessionError, setSessionError] = useState("");
  const [securityDialog, setSecurityDialog] = useState<
    "password" | "email" | null
  >(null);
  const [emailStep, setEmailStep] = useState<1 | 2>(1);
  const [securityError, setSecurityError] = useState("");
  const [securityNotice, setSecurityNotice] = useState("");
  const [securitySuccess, setSecuritySuccess] = useState("");
  const [editableSecurityFields, setEditableSecurityFields] = useState<
    Partial<Record<SecurityField, boolean>>
  >({});
  const [sessions, setSessions] = useState<LoginSession[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [codeCooldown, setCodeCooldown] = useState({ old: 0, next: 0 });

  useEffect(() => {
    if (!codeCooldown.old && !codeCooldown.next) return;
    const timer = window.setInterval(
      () =>
        setCodeCooldown((current) => ({
          old: Math.max(0, current.old - 1),
          next: Math.max(0, current.next - 1),
        })),
      1000,
    );
    return () => window.clearInterval(timer);
  }, [codeCooldown.old, codeCooldown.next]);

  useEffect(() => {
    let live = true;
    void listSessions(page)
      .then((result) => {
        if (live) {
          setSessions(result.data.items);
          setTotal(result.data.total);
        }
      })
      .catch((error) => {
        if (live)
          setMessage(error instanceof Error ? error.message : p.loadFailed);
      });
    return () => {
      live = false;
    };
  }, [page]);

  async function run(work: () => Promise<unknown>, success: string) {
    if (busy) return;
    setBusy(true);
    setMessage("");
    try {
      await work();
      setMessage(success);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : p.loadFailed);
    } finally {
      setBusy(false);
    }
  }

  async function refreshUser() {
    auth.updateUser((await getCurrentUser()).data);
  }
  async function refreshSessions() {
    const result = await listSessions(page);
    setSessions(result.data.items);
    setTotal(result.data.total);
  }

  function clearSecurityForm() {
    setOldPassword("");
    setNewPassword("");
    setEmailPassword("");
    setOldCode("");
    setNewEmail("");
    setNewCode("");
    setEmailStep(1);
    setSecurityError("");
    setSecurityNotice("");
    setEditableSecurityFields({});
  }

  function enableSecurityField(field: SecurityField) {
    setEditableSecurityFields((current) => ({ ...current, [field]: true }));
  }

  function openSecurityDialog(kind: "password" | "email") {
    clearSecurityForm();
    setSecuritySuccess("");
    setSecurityDialog(kind);
  }

  function closeSecurityDialog() {
    if (busy) return;
    setSecurityDialog(null);
    clearSecurityForm();
  }

  async function submitPassword(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    if (oldPassword.length < 8 || newPassword.length < 8) {
      setSecurityError(p.completePasswordFields);
      return;
    }
    setBusy(true);
    setSecurityError("");
    try {
      await changePassword({
        old_password: oldPassword,
        new_password: newPassword,
      });
      setSecuritySuccess(p.passwordChanged);
      setSecurityDialog(null);
      clearSecurityForm();
    } catch (error) {
      setSecurityError(error instanceof Error ? error.message : p.loadFailed);
    } finally {
      setBusy(false);
    }
  }

  async function sendChangeEmailCode(kind: "old" | "next") {
    const targetEmail = kind === "old" ? user?.email : newEmail;
    if (busy || !targetEmail || codeCooldown[kind] > 0) return;
    setBusy(true);
    setSecurityError("");
    setSecurityNotice("");
    try {
      await sendEmailCode(
        targetEmail,
        kind === "old" ? "CHANGE_EMAIL_OLD" : "CHANGE_EMAIL_NEW",
      );
      setCodeCooldown((value) => ({ ...value, [kind]: 60 }));
      setSecurityNotice(a.codeSent);
    } catch (error) {
      setSecurityError(error instanceof Error ? error.message : a.codeFailed);
    } finally {
      setBusy(false);
    }
  }

  async function submitEmail(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    if (!newEmail || !/^\d{6}$/.test(newCode)) {
      setSecurityError(p.completeNewEmailStep);
      return;
    }
    setBusy(true);
    setSecurityError("");
    setSecurityNotice("");
    try {
      await changeEmail({
        password: emailPassword,
        old_email_code: oldCode,
        new_email: newEmail,
        new_email_code: newCode,
      });
      await refreshUser();
      setSecuritySuccess(p.emailChanged);
      setSecurityDialog(null);
      clearSecurityForm();
    } catch (error) {
      setSecurityError(error instanceof Error ? error.message : p.loadFailed);
    } finally {
      setBusy(false);
    }
  }

  async function confirmSessionAction(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!sessionAction || !confirmPassword || busy) return;
    setBusy(true);
    setSessionError("");
    try {
      if (sessionAction.kind === "single") {
        await revokeSession(sessionAction.familyId, confirmPassword);
        await refreshSessions();
        setMessage(p.sessionRevoked);
      } else if (sessionAction.kind === "others") {
        await revokeOtherSessions(confirmPassword);
        await refreshSessions();
        setMessage(p.otherDevicesRevoked);
      } else {
        await logoutAllSessions(confirmPassword);
        auth.clear();
        router.replace("/login");
      }
      setSessionAction(null);
      setConfirmPassword("");
    } catch (error) {
      setSessionError(error instanceof Error ? error.message : p.loadFailed);
    } finally {
      setBusy(false);
    }
  }

  const name = user?.nickname || user?.username || p.defaultName;
  const actionTitle =
    sessionAction?.kind === "single"
      ? p.revokeDevice
      : sessionAction?.kind === "others"
        ? p.logoutOthers
        : p.logoutAll;

  return (
    <div className="profile-page">
      <LandscapeScene variant="ocean" />
      <div className="profile-heading">
        <h1>{messages.navigation.profile}</h1>
        <p>{p.subtitle}</p>
      </div>
      <section className="profile-banner" aria-label={p.overviewLabel}>
        <div className="profile-avatar">
          {user?.avatar_url ? (
            <Image
              src={`${API_BASE_URL}${user.avatar_url}`}
              alt={p.avatar}
              fill
              sizes="92px"
              unoptimized
            />
          ) : (
            Array.from(name)[0]
          )}
        </div>
        <div className="profile-welcome">
          <span>{p.welcome}</span>
          <h2>{name}</h2>
          <p>{p.bannerMotto}</p>
        </div>
      </section>
      {message && (
        <p className="profile-status" role="status">
          {message}
        </p>
      )}
      <div className="profile-cards">
        <section className="profile-card">
          <div className="profile-card-title">
            <span className="profile-card-icon">
              <UserRound aria-hidden="true" />
            </span>
            <div>
              <h2>{p.basicInfo}</h2>
              <p>{p.accountInfo}</p>
            </div>
          </div>
          <dl className="profile-details">
            <div>
              <dt>{a.username}</dt>
              <dd>{user?.username ?? "—"}</dd>
            </div>
            <div>
              <dt>{a.email}</dt>
              <dd>{user?.email ?? "—"}</dd>
            </div>
            <div>
              <dt>{a.nickname}</dt>
              <dd>{user?.nickname || p.notSet}</dd>
            </div>
          </dl>
          <div className="profile-edit-list">
            <details className="profile-edit-panel" name="profile-settings">
              <summary>
                <span className="profile-action-icon">
                  <Pencil aria-hidden="true" />
                </span>
                <span className="profile-edit-label">
                  <strong>{p.editNickname}</strong>
                  <small>{p.nicknameHelp}</small>
                </span>
                <ChevronDown
                  className="profile-edit-chevron"
                  aria-hidden="true"
                />
              </summary>
              <form
                className="profile-auth-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (user)
                    void run(async () => {
                      await updateNickname(
                        user.id,
                        nickname ?? user.nickname ?? "",
                      );
                      await refreshUser();
                    }, p.nicknameSaved);
                }}
              >
                <label>
                  {p.editNickname}
                  <input
                    value={nickname ?? user?.nickname ?? ""}
                    minLength={1}
                    maxLength={50}
                    onChange={(event) => setNickname(event.target.value)}
                    required
                  />
                </label>
                <button disabled={busy}>{p.save}</button>
              </form>
            </details>
            <details className="profile-edit-panel" name="profile-settings">
              <summary>
                <span className="profile-action-icon">
                  <Camera aria-hidden="true" />
                </span>
                <span className="profile-edit-label">
                  <strong>{p.avatar}</strong>
                  <small>{p.avatarHelp}</small>
                </span>
                <ChevronDown
                  className="profile-edit-chevron"
                  aria-hidden="true"
                />
              </summary>
              <div className="profile-auth-form">
                <label>
                  {p.avatar}
                  <input
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    onChange={(event) => {
                      const file = event.target.files?.[0];
                      if (file)
                        void run(async () => {
                          await uploadAvatar(file);
                          await refreshUser();
                        }, p.avatarSaved);
                    }}
                  />
                </label>
                <button
                  className="profile-button-subtle"
                  type="button"
                  disabled={busy || !user?.avatar_url}
                  onClick={() =>
                    void run(async () => {
                      await deleteAvatar();
                      await refreshUser();
                    }, p.avatarDeleted)
                  }
                >
                  {p.deleteAvatar}
                </button>
              </div>
            </details>
          </div>
        </section>
        <section className="profile-card">
          <div className="profile-card-title">
            <span className="profile-card-icon">
              <ShieldCheck aria-hidden="true" />
            </span>
            <div>
              <h2>{p.security}</h2>
              <p>{p.securityDescription}</p>
            </div>
          </div>
          {securitySuccess && (
            <p className="profile-security-success" role="status">
              {securitySuccess}
            </p>
          )}
          <div className="profile-edit-list">
            <button
              className="profile-security-trigger"
              type="button"
              disabled={busy}
              onClick={() => openSecurityDialog("password")}
            >
              <span className="profile-action-icon">
                <KeyRound aria-hidden="true" />
              </span>
              <span className="profile-edit-label">
                <strong>{p.changePassword}</strong>
                <small>{p.passwordHelp}</small>
              </span>
              <ChevronRight
                className="profile-edit-chevron"
                aria-hidden="true"
              />
            </button>
            <button
              className="profile-security-trigger"
              type="button"
              disabled={busy}
              onClick={() => openSecurityDialog("email")}
            >
              <span className="profile-action-icon">
                <Mail aria-hidden="true" />
              </span>
              <span className="profile-edit-label">
                <strong>{p.changeEmail}</strong>
                <small>{p.emailHelp}</small>
              </span>
              <ChevronRight
                className="profile-edit-chevron"
                aria-hidden="true"
              />
            </button>
          </div>
        </section>
        <section className="profile-card profile-sessions">
          <div className="profile-card-title">
            <span className="profile-card-icon">
              <MonitorSmartphone aria-hidden="true" />
            </span>
            <div>
              <h2>{p.devices}</h2>
              <p>{p.sessionDescription}</p>
            </div>
          </div>
          <ul>
            {sessions.map((session) => (
              <li key={session.family_id}>
                <div className="profile-session-info">
                  <strong>
                    {session.device_name}
                    {session.is_current && (
                      <span className="profile-current-badge">
                        {p.currentDevice}
                      </span>
                    )}
                  </strong>
                  <small>
                    {p.signedInAt}: {session.created_at} · {p.lastActive}:{" "}
                    {session.last_activity_at}
                  </small>
                </div>
                {!session.is_current && (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() =>
                      setSessionAction({
                        kind: "single",
                        familyId: session.family_id,
                        deviceName: session.device_name,
                      })
                    }
                  >
                    {p.revokeDevice}
                  </button>
                )}
              </li>
            ))}
          </ul>
          {total > 20 && (
            <div className="profile-session-pages">
              <button
                type="button"
                disabled={page <= 1}
                onClick={() => setPage(page - 1)}
              >
                {p.previous}
              </button>
              <span>
                {page} / {Math.max(1, Math.ceil(total / 20))}
              </span>
              <button
                type="button"
                disabled={page * 20 >= total}
                onClick={() => setPage(page + 1)}
              >
                {p.next}
              </button>
            </div>
          )}
          <div className="profile-auth-form">
            <div className="profile-device-buttons">
              <button
                type="button"
                disabled={busy}
                onClick={() =>
                  void run(async () => {
                    const result = await logoutUser();
                    if (!result.data.session_revoked)
                      throw new Error(p.logoutUnconfirmed);
                    auth.clear();
                    router.replace("/login");
                  }, p.logoutCurrent)
                }
              >
                {p.logoutCurrent}
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => setSessionAction({ kind: "others" })}
              >
                {p.logoutOthers}
              </button>
              <button
                className="profile-button-danger"
                type="button"
                disabled={busy}
                onClick={() => setSessionAction({ kind: "all" })}
              >
                {p.logoutAll}
              </button>
            </div>
          </div>
        </section>
      </div>
      <Dialog
        open={securityDialog !== null}
        onOpenChange={(open) => {
          if (!open) closeSecurityDialog();
        }}
      >
        <DialogContent
          className="profile-security-dialog"
          onEscapeKeyDown={(event) => {
            if (busy) event.preventDefault();
          }}
          onInteractOutside={(event) => {
            if (busy) event.preventDefault();
          }}
        >
          <DialogHeader>
            <div className="profile-security-dialog-heading">
              <DialogTitle>
                {securityDialog === "password"
                  ? p.changePassword
                  : p.changeEmail}
              </DialogTitle>
              <DialogClose
                type="button"
                disabled={busy}
                aria-label={p.closeDialog}
              >
                <X aria-hidden="true" size={18} />
              </DialogClose>
            </div>
            <DialogDescription>
              {securityDialog === "password"
                ? p.passwordHelp
                : p.emailDialogDescription}
            </DialogDescription>
          </DialogHeader>
          {securityDialog === "password" ? (
            <form
              className="profile-security-form"
              autoComplete="off"
              onSubmit={(event) => void submitPassword(event)}
            >
              <label htmlFor="profile-old-password">{p.currentPassword}</label>
              <input
                id="profile-old-password"
                type="password"
                autoComplete="off"
                readOnly={!editableSecurityFields.oldPassword}
                onFocus={() => enableSecurityField("oldPassword")}
                value={oldPassword}
                onChange={(event) => setOldPassword(event.target.value)}
                minLength={8}
                required
              />
              <label htmlFor="profile-new-password">{p.newPassword}</label>
              <input
                id="profile-new-password"
                type="password"
                autoComplete="off"
                readOnly={!editableSecurityFields.newPassword}
                onFocus={() => enableSecurityField("newPassword")}
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
                minLength={8}
                required
              />
              {securityError && (
                <p className="profile-security-error" role="alert">
                  {securityError}
                </p>
              )}
              <div className="profile-security-actions">
                <DialogClose type="button" disabled={busy}>
                  {messages.common.cancel}
                </DialogClose>
                <button type="submit" disabled={busy}>
                  {busy ? messages.common.savingCompact : p.save}
                </button>
              </div>
            </form>
          ) : securityDialog === "email" ? (
            <div className="profile-security-flow">
              <ol
                className="profile-security-steps"
                aria-label={p.emailChangeSteps}
              >
                <li aria-current={emailStep === 1 ? "step" : undefined}>
                  <span aria-hidden="true">1</span>
                  {p.emailStepOld}
                </li>
                <li aria-current={emailStep === 2 ? "step" : undefined}>
                  <span aria-hidden="true">2</span>
                  {p.emailStepNew}
                </li>
              </ol>
              {emailStep === 1 ? (
                <form
                  className="profile-security-form"
                  autoComplete="off"
                  onSubmit={(event) => {
                    event.preventDefault();
                    if (busy) return;
                    if (emailPassword.length < 8 || !/^\d{6}$/.test(oldCode)) {
                      setSecurityError(p.completeOldEmailStep);
                      return;
                    }
                    setEmailStep(2);
                    setSecurityError("");
                    setSecurityNotice("");
                  }}
                >
                  <h3 className="profile-security-step-title">
                    {p.emailStepOld}
                  </h3>
                  <p className="profile-security-step-description">
                    {p.emailStepOldDescription}
                  </p>
                  <p className="profile-security-current-email">
                    {p.currentEmail}：{user?.email ?? "—"}
                  </p>
                  <label htmlFor="profile-email-password">
                    {p.currentPassword}
                  </label>
                  <input
                    id="profile-email-password"
                    type="password"
                    autoComplete="off"
                    readOnly={!editableSecurityFields.emailPassword}
                    onFocus={() => enableSecurityField("emailPassword")}
                    value={emailPassword}
                    onChange={(event) => setEmailPassword(event.target.value)}
                    minLength={8}
                    required
                  />
                  <div className="profile-code-row">
                    <div className="profile-security-field">
                      <label htmlFor="profile-old-email-code">
                        {p.oldEmailCode}
                      </label>
                      <input
                        id="profile-old-email-code"
                        inputMode="numeric"
                        autoComplete="off"
                        readOnly={!editableSecurityFields.oldCode}
                        onFocus={() => enableSecurityField("oldCode")}
                        value={oldCode}
                        onChange={(event) =>
                          setOldCode(
                            event.target.value.replace(/\D/g, "").slice(0, 6),
                          )
                        }
                        pattern="[0-9]{6}"
                        maxLength={6}
                        required
                      />
                    </div>
                    <button
                      type="button"
                      className="profile-security-code-button"
                      disabled={busy || !user || codeCooldown.old > 0}
                      onClick={() => void sendChangeEmailCode("old")}
                    >
                      {codeCooldown.old
                        ? a.resendIn(codeCooldown.old)
                        : p.sendOldEmailCode}
                    </button>
                  </div>
                  {securityNotice && (
                    <p className="profile-security-notice" role="status">
                      {securityNotice}
                    </p>
                  )}
                  {securityError && (
                    <p className="profile-security-error" role="alert">
                      {securityError}
                    </p>
                  )}
                  <div className="profile-security-actions">
                    <DialogClose type="button" disabled={busy}>
                      {messages.common.cancel}
                    </DialogClose>
                    <button type="submit" disabled={busy}>
                      {p.emailNext}
                    </button>
                  </div>
                </form>
              ) : (
                <form
                  className="profile-security-form"
                  autoComplete="off"
                  onSubmit={(event) => void submitEmail(event)}
                >
                  <h3 className="profile-security-step-title">
                    {p.emailStepNew}
                  </h3>
                  <p className="profile-security-step-description">
                    {p.emailStepNewDescription}
                  </p>
                  <label htmlFor="profile-new-email">{p.newEmail}</label>
                  <input
                    id="profile-new-email"
                    type="email"
                    autoComplete="off"
                    readOnly={!editableSecurityFields.newEmail}
                    onFocus={() => enableSecurityField("newEmail")}
                    value={newEmail}
                    onChange={(event) => setNewEmail(event.target.value)}
                    required
                  />
                  <div className="profile-code-row">
                    <div className="profile-security-field">
                      <label htmlFor="profile-new-email-code">
                        {p.newEmailCode}
                      </label>
                      <input
                        id="profile-new-email-code"
                        inputMode="numeric"
                        autoComplete="off"
                        readOnly={!editableSecurityFields.newCode}
                        onFocus={() => enableSecurityField("newCode")}
                        value={newCode}
                        onChange={(event) =>
                          setNewCode(
                            event.target.value.replace(/\D/g, "").slice(0, 6),
                          )
                        }
                        pattern="[0-9]{6}"
                        maxLength={6}
                        required
                      />
                    </div>
                    <button
                      type="button"
                      className="profile-security-code-button"
                      disabled={busy || !newEmail || codeCooldown.next > 0}
                      onClick={() => void sendChangeEmailCode("next")}
                    >
                      {codeCooldown.next
                        ? a.resendIn(codeCooldown.next)
                        : p.sendNewEmailCode}
                    </button>
                  </div>
                  <p className="profile-security-hint">
                    {p.emailFinalVerification}
                  </p>
                  {securityNotice && (
                    <p className="profile-security-notice" role="status">
                      {securityNotice}
                    </p>
                  )}
                  {securityError && (
                    <p className="profile-security-error" role="alert">
                      {securityError}
                    </p>
                  )}
                  <div className="profile-security-actions">
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => {
                        setEmailStep(1);
                        setSecurityError("");
                        setSecurityNotice("");
                      }}
                    >
                      {p.emailBack}
                    </button>
                    <button type="submit" disabled={busy}>
                      {busy ? messages.common.savingCompact : p.emailSubmit}
                    </button>
                  </div>
                </form>
              )}
            </div>
          ) : null}
        </DialogContent>
      </Dialog>
      <AlertDialog.Root
        open={sessionAction !== null}
        onOpenChange={(open) => {
          if (!open && !busy) {
            setSessionAction(null);
            setConfirmPassword("");
            setSessionError("");
          }
        }}
      >
        <AlertDialog.Portal>
          <AlertDialog.Overlay className="profile-dialog-overlay" />
          <AlertDialog.Content className="profile-dialog">
            <AlertDialog.Title>{actionTitle}</AlertDialog.Title>
            <AlertDialog.Description>
              {sessionAction?.kind === "single"
                ? p.revokeDeviceDescription(sessionAction.deviceName)
                : sessionAction?.kind === "others"
                  ? p.logoutOthersDescription
                  : p.logoutAllDescription}
            </AlertDialog.Description>
            <form onSubmit={(event) => void confirmSessionAction(event)}>
              <label htmlFor="profile-session-confirm-password">
                {p.confirmPassword}
              </label>
              <input
                id="profile-session-confirm-password"
                type="password"
                autoComplete="current-password"
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
                minLength={8}
                required
              />
              {sessionError && (
                <p className="profile-dialog-error" role="alert">
                  {sessionError}
                </p>
              )}
              <div className="profile-dialog-actions">
                <AlertDialog.Cancel type="button" disabled={busy}>
                  {messages.common.cancel}
                </AlertDialog.Cancel>
                <button
                  type="submit"
                  className={
                    sessionAction?.kind === "all"
                      ? "profile-dialog-danger"
                      : undefined
                  }
                  disabled={busy || !confirmPassword}
                >
                  {actionTitle}
                </button>
              </div>
            </form>
          </AlertDialog.Content>
        </AlertDialog.Portal>
      </AlertDialog.Root>
    </div>
  );
}
