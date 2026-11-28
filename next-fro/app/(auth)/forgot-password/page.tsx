"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { messages } from "@/messages";
import { resetPassword, sendEmailCode } from "@/services/auth.service";
import { announceAuthChange, authEpoch, sameAuthEpoch } from "@/lib/auth/coordinator";
import { useAuth } from "@/contexts/AuthContext";
import AuthScene from "@/components/auth/AuthScene";
import "@/components/css/LoginForm.css";
import "@/components/css/AuthFields.css";

const copy = messages.auth;

export default function ForgotPasswordPage() {
  const router = useRouter();
  const auth = useAuth();
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [cooldown, setCooldown] = useState(0);

  async function sendCode() {
    if (busy || cooldown || !email) return;
    setBusy(true);
    setMessage("");
    try {
      await sendEmailCode(email, "RESET_PASSWORD");
      setMessage(copy.codeSent);
      setCooldown(60);
      const timer = window.setInterval(
        () =>
          setCooldown((seconds) => {
            if (seconds <= 1) {
              window.clearInterval(timer);
              return 0;
            }
            return seconds - 1;
          }),
        1000,
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : copy.codeFailed);
    } finally {
      setBusy(false);
    }
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    if (password !== confirm) {
      setMessage(copy.passwordMismatch);
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      const epoch = authEpoch();
      await resetPassword({ email, code, new_password: password });
      setPassword("");
      setConfirm("");
      setCode("");
      if (sameAuthEpoch(epoch) && auth.user?.email.toLowerCase() === email.trim().toLowerCase()) {
        auth.clear();
        announceAuthChange("logout");
      }
      setMessage(copy.resetSuccess);
      window.setTimeout(() => router.replace("/login"), 1500);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : copy.resetFailed);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-page">
      <form className="login-form" onSubmit={submit}>
        <h1>{copy.forgotPassword}</h1>
        <div className="login-field">
          <label htmlFor="reset-email">{copy.email}</label>
          <input
            id="reset-email"
            type="email"
            autoComplete="email"
            placeholder={copy.emailPlaceholder}
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />
        </div>
        <div className="login-field">
          <label htmlFor="reset-code">{copy.emailCode}</label>
          <div className="auth-inline-field">
            <input
              id="reset-code"
              inputMode="numeric"
              pattern="[0-9]{6}"
              maxLength={6}
              placeholder={copy.codePlaceholder}
              value={code}
              onChange={(event) => setCode(event.target.value)}
              required
            />
            <button
              type="button"
              disabled={busy || cooldown > 0}
              onClick={() => void sendCode()}
            >
              {cooldown ? copy.resendIn(cooldown) : copy.sendCode}
            </button>
          </div>
        </div>
        <div className="login-field">
          <label htmlFor="reset-password">{copy.newPassword}</label>
          <input
            id="reset-password"
            type="password"
            minLength={8}
            maxLength={64}
            autoComplete="new-password"
            placeholder={copy.newPasswordPlaceholder}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
        </div>
        <div className="login-field">
          <label htmlFor="reset-confirm">{copy.confirmPassword}</label>
          <input
            id="reset-confirm"
            type="password"
            minLength={8}
            maxLength={64}
            autoComplete="new-password"
            placeholder={copy.confirmPasswordPlaceholder}
            value={confirm}
            onChange={(event) => setConfirm(event.target.value)}
            required
          />
        </div>
        {message && (
          <p className="login-message" role="status">
            {message}
          </p>
        )}
        <button className="login-submit" disabled={busy}>
          {busy ? copy.resetting : copy.resetPassword}
        </button>
        <p className="login-register">
          <Link href="/login">{copy.backToLogin}</Link>
        </p>
      </form>
      <AuthScene />
    </main>
  );
}
