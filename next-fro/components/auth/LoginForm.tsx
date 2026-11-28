"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/contexts/AuthContext";
import { sameAuthEpoch } from "@/lib/auth/coordinator";
import {
  loginUser,
  loginWithEmail,
  sendEmailCode,
} from "@/services/auth.service";
import { messages } from "@/messages";
import "@/components/css/LoginForm.css";
import "@/components/css/AuthFields.css";

const copy = messages.auth;
type Mode = "username" | "email-password" | "email-code";

export default function LoginForm() {
  const router = useRouter();
  const auth = useAuth();
  const [mode, setMode] = useState<Mode>("username");
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [cooldown, setCooldown] = useState(0);

  async function sendCode() {
    if (busy || cooldown || !identifier) return;
    setBusy(true);
    setMessage("");
    try {
      await sendEmailCode(identifier, "LOGIN");
      setMessage(copy.loginCodeRequested);
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
    setBusy(true);
    setMessage("");
    try {
      const result =
        mode === "email-code"
          ? await loginWithEmail({ email: identifier, code })
          : await loginUser({ username: identifier, password });
      if (!sameAuthEpoch(result.authEpoch)) throw new Error(copy.sessionChanged);
      auth.completeLogin(result.data.user);
      router.replace("/");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : copy.loginFailed);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="login-form" onSubmit={submit}>
      <div className="login-formHeading">
        <span className="login-book" aria-hidden="true">
          ▤
        </span>
        <h1>{messages.common.appName}</h1>
      </div>
      <div className="auth-mode-tabs" role="group" aria-label={copy.loginMode}>
        {(["username", "email-password", "email-code"] as const).map(
          (value) => (
            <button
              key={value}
              type="button"
              aria-pressed={mode === value}
              onClick={() => {
                setMode(value);
                setIdentifier("");
                setMessage("");
              }}
            >
              {value === "username"
                ? copy.usernameLogin
                : value === "email-password"
                  ? copy.emailPasswordLogin
                  : copy.emailCodeLogin}
            </button>
          ),
        )}
      </div>
      <div className="login-field">
        <label htmlFor="login-identifier">
          {mode === "username" ? copy.username : copy.email}
        </label>
        <input
          id="login-identifier"
          autoComplete={mode === "username" ? "username" : "email"}
          type={mode === "username" ? "text" : "email"}
          placeholder={mode === "username" ? copy.usernamePlaceholder : copy.emailPlaceholder}
          value={identifier}
          onChange={(event) => setIdentifier(event.target.value)}
          required
        />
      </div>
      {mode === "email-code" ? (
        <div className="login-field">
          <label htmlFor="login-code">{copy.emailCode}</label>
          <div className="auth-inline-field">
            <input
              id="login-code"
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
      ) : (
        <div className="login-field">
          <label htmlFor="login-password">{copy.password}</label>
          <input
            id="login-password"
            type="password"
            autoComplete="current-password"
            minLength={8}
            placeholder={copy.passwordPlaceholder}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
        </div>
      )}
      {message && (
        <p className="login-message" role="status">
          {message}
        </p>
      )}
      <button className="login-submit" type="submit" disabled={busy}>
        {busy ? copy.loggingIn : copy.login}
      </button>
      <p className="login-register">
        <Link href="/register">{copy.newUser}</Link>
        <Link href="/forgot-password">{copy.forgotPassword}</Link>
      </p>
      <p className="login-motto">{copy.motto}</p>
    </form>
  );
}
