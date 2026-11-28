"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import { sameAuthEpoch } from "@/lib/auth/coordinator";
import { registerUser, sendEmailCode } from "@/services/auth.service";
import { messages } from "@/messages";
import type { RegisterRequest } from "@/types/auth";
import "@/components/css/AuthFields.css";

const copy = messages.auth;

export default function RegisterForm() {
  const router = useRouter();
  const auth = useAuth();
  const [form, setForm] = useState<RegisterRequest>({
    username: "",
    email: "",
    code: "",
    password: "",
    nickname: "",
  });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [cooldown, setCooldown] = useState(0);

  async function sendCode() {
    if (busy || cooldown || !form.email) return;
    setBusy(true);
    setMessage("");
    try {
      await sendEmailCode(form.email, "REGISTER");
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
    setBusy(true);
    setMessage("");
    try {
      const result = await registerUser({
        ...form,
        nickname: form.nickname || null,
      });
      setForm((current) => ({ ...current, password: "", code: "" }));
      if (!sameAuthEpoch(result.authEpoch)) throw new Error(copy.sessionChanged);
      auth.completeLogin(result.data.user);
      router.replace("/");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : copy.registerFailed);
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
      <p className="login-formSubtitle">{copy.newUser}</p>
      <div className="login-field">
        <label htmlFor="register-username">{copy.username}</label>
        <input
          id="register-username"
          minLength={4}
          maxLength={32}
          pattern="[a-zA-Z0-9_]+"
          autoComplete="username"
          placeholder={copy.usernamePlaceholder}
          value={form.username}
          onChange={(event) =>
            setForm({ ...form, username: event.target.value })
          }
          required
        />
      </div>
      <div className="login-field">
        <label htmlFor="register-email">{copy.email}</label>
        <input
          id="register-email"
          type="email"
          autoComplete="email"
          placeholder={copy.emailPlaceholder}
          value={form.email}
          onChange={(event) => setForm({ ...form, email: event.target.value })}
          required
        />
      </div>
      <div className="login-field">
        <label htmlFor="register-code">{copy.emailCode}</label>
        <div className="auth-inline-field">
          <input
            id="register-code"
            inputMode="numeric"
            pattern="[0-9]{6}"
            maxLength={6}
            placeholder={copy.codePlaceholder}
            value={form.code}
            onChange={(event) => setForm({ ...form, code: event.target.value })}
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
        <label htmlFor="register-password">{copy.password}</label>
        <input
          id="register-password"
          type="password"
          minLength={8}
          maxLength={64}
          autoComplete="new-password"
          placeholder={copy.newPasswordPlaceholder}
          value={form.password}
          onChange={(event) =>
            setForm({ ...form, password: event.target.value })
          }
          required
        />
      </div>
      <div className="login-field">
        <label htmlFor="register-nickname">
          {copy.nickname}（{copy.optional}）
        </label>
        <input
          id="register-nickname"
          maxLength={50}
          placeholder={copy.nicknamePlaceholder}
          value={form.nickname ?? ""}
          onChange={(event) =>
            setForm({ ...form, nickname: event.target.value })
          }
        />
      </div>
      {message && (
        <p className="login-message" role="status">
          {message}
        </p>
      )}
      <button className="login-submit" type="submit" disabled={busy}>
        {busy ? copy.registering : copy.register}
      </button>
      <p className="login-register">
        {copy.hasAccount}
        <Link href="/login">{copy.backToLogin}</Link>
      </p>
    </form>
  );
}
