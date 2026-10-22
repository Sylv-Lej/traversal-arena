"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { useT } from "@/lib/i18n/client";
import { useMe } from "@/lib/me";

/** Sans jeton : demande d'un lien par email. Avec ?token=… : choix du nouveau mot de passe. */
function ResetInner() {
  const router = useRouter();
  const token = useSearchParams().get("token");
  const { forgot, resetPassword } = useMe();
  const t = useT();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (ex) {
      setError((ex as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (token) {
    return (
      <div className="page narrow">
        <div className="card authCard">
          <h1>{t.auth.newPassword}</h1>
          <form
            className="stack"
            onSubmit={(e) => {
              e.preventDefault();
              if (password !== confirm) {
                setError(t.auth.mismatch);
                return;
              }
              void run(async () => {
                await resetPassword(token, password);
                router.push("/");
              });
            }}
          >
            <label className="field">
              <span>
                {t.auth.newPassword} <small className="muted">{t.auth.minChars}</small>
              </span>
              <input type="password" autoComplete="new-password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} />
            </label>
            <label className="field">
              <span>{t.auth.confirmation}</span>
              <input type="password" autoComplete="new-password" required minLength={8} value={confirm} onChange={(e) => setConfirm(e.target.value)} />
            </label>
            {error && <p className="error">{error}</p>}
            <button className="btn primary big" type="submit" disabled={busy}>
              {t.auth.saveAndLogIn}
            </button>
            {error && (
              <Link className="center small" href="/reset">
                {t.auth.requestNewLink}
              </Link>
            )}
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="page narrow">
      <div className="card authCard">
        <h1>{t.auth.forgotTitle}</h1>
        {sent ? (
          <div className="stack">
            <p>
              {t.auth.sentBefore} <b>{email}</b>
              {t.auth.sentAfter}
            </p>
            <p className="muted small">{t.auth.checkSpam}</p>
            <Link className="btn" href="/login">
              {t.auth.backToLogin}
            </Link>
          </div>
        ) : (
          <form
            className="stack"
            onSubmit={(e) => {
              e.preventDefault();
              void run(async () => {
                await forgot(email);
                setSent(true);
              });
            }}
          >
            <p className="muted">{t.auth.forgotIntro}</p>
            <label className="field">
              <span>{t.auth.email}</span>
              <input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
            </label>
            {error && <p className="error">{error}</p>}
            <button className="btn primary big" type="submit" disabled={busy}>
              {t.auth.sendLink}
            </button>
            <Link className="center small" href="/login">
              {t.auth.backToLogin}
            </Link>
          </form>
        )}
      </div>
    </div>
  );
}

export default function ResetPage() {
  return (
    <Suspense>
      <ResetInner />
    </Suspense>
  );
}
