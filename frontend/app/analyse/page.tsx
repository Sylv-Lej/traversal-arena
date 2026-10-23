"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n/client";

// Bilan d'une partie jouée sur traversalgame.com : le backend l'importe (rejouée avec nos
// règles), on lance son analyse, puis on ouvre la partie sur l'onglet « Bilan ».
export default function AnalysePage() {
  const t = useT();
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<{ enabled: boolean }>("imports/status")
      .then((r) => setEnabled(r.enabled))
      .catch(() => setEnabled(null));
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { id } = await api<{ id: string }>("imports", { body: { url: url.trim() } });
      // Déjà analysée, ou limite atteinte : la page de la partie s'en charge.
      await api(`games/${id}/analysis`, { body: {} }).catch(() => undefined);
      router.push(`/game/${id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t.common.errors.generic);
      setBusy(false);
    }
  };

  return (
    <div className="page narrow">
      <h1 className="pageTitle">{t.analysis.importTitle}</h1>
      <p className="muted">{t.analysis.importIntro}</p>
      <div className="card">
        {enabled === false ? (
          <p>{t.analysis.importClosed}</p>
        ) : (
          <form className="botForm" onSubmit={submit}>
            <label className="field">
              <span>{t.analysis.importLink}</span>
              <input
                type="url"
                inputMode="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder={t.analysis.importPlaceholder}
                required
              />
            </label>
            <button className="btn primary" type="submit" disabled={busy || !url.trim()}>
              {busy ? t.analysis.importing : t.analysis.importSubmit}
            </button>
            {error && <p className="error">{error}</p>}
          </form>
        )}
      </div>
    </div>
  );
}
