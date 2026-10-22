"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n/client";

/** Compte dont l'adresse n'est pas encore confirmée : rappel + renvoi du lien. */
export function VerifyNotice({ email }: { email: string }) {
  const t = useT();
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const resend = async () => {
    setBusy(true);
    try {
      await api("auth/resend", { body: {} });
      setMsg({ ok: true, text: t.auth.resent });
    } catch (e) {
      setMsg({ ok: false, text: e instanceof ApiError ? e.message : t.common.errors.generic });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="stack">
      <p>{t.auth.notVerified(email)}</p>
      <p className="muted small">{t.auth.checkSpam}</p>
      <button className="btn small" onClick={resend} disabled={busy}>
        {t.auth.resend}
      </button>
      {msg && <p className={msg.ok ? "muted small" : "error"}>{msg.text}</p>}
    </div>
  );
}
