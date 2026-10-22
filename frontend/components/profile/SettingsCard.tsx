"use client";

import Link from "next/link";
import { useState } from "react";
import { CountrySelect } from "@/components/ui/Flag";
import { LangSwitch } from "@/components/ui/Shell";
import { useT } from "@/lib/i18n/client";
import { useMe } from "@/lib/me";
import { updateSettings, useSettings, type Quality } from "@/lib/settings";

/** Compte, pseudo, pays et réglages d'affichage (section de la page Profil). */
export function SettingsCard() {
  const s = useSettings();
  const t = useT();
  const { me, rename, logout } = useMe();
  const [name, setName] = useState("");
  const [country, setCountry] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const qualities: Quality[] = ["auto", "high", "medium", "low"];
  return (
    <section className="card" id="settings">
      <h2 className="cardTitle">{t.common.nav.settings}</h2>
      <form
        className="stack"
        onSubmit={async (e) => {
          e.preventDefault();
          setErr(null);
          setSaved(false);
          try {
            await rename(name || me?.name || "", country || undefined);
            setSaved(true);
          } catch (ex) {
            setErr((ex as Error).message);
          }
        }}
      >
        <div className="accountBox">
          {me?.isGuest ? (
            <>
              <span>{t.shell.guestNotice}</span>
              <Link className="btn small primary" href="/login?tab=signup">
                {t.shell.createAccount}
              </Link>
              <Link className="btn small" href="/login">
                {t.shell.logIn}
              </Link>
            </>
          ) : (
            <>
              <span>
                {t.shell.loggedInAs} <b>{me?.email}</b>
              </span>
              <button type="button" className="btn small ghost" onClick={() => void logout()}>
                {t.shell.logOut}
              </button>
            </>
          )}
        </div>
        <label className="field">
          <span>{t.shell.nickname}</span>
          <input defaultValue={me?.name} onChange={(e) => setName(e.target.value)} maxLength={20} minLength={3} />
        </label>
        <div className="field">
          <span>{t.common.country.short}</span>
          <CountrySelect value={country || me?.country || ""} onChange={setCountry} />
        </div>
        {err && <p className="error">{err}</p>}
        <div className="field">
          <span>{t.common.lang.label}</span>
          <LangSwitch />
        </div>
        <div className="field">
          <span>{t.shell.quality}</span>
          <div className="segmented">
            {qualities.map((q) => (
              <button type="button" key={q} className={s.quality === q ? "on" : ""} onClick={() => updateSettings({ quality: q })}>
                {t.shell.qualities[q]}
              </button>
            ))}
          </div>
        </div>
        <label className="check">
          <input type="checkbox" checked={s.showHeights} onChange={(e) => updateSettings({ showHeights: e.target.checked })} />
          {t.shell.showHeights}
        </label>
        <label className="check">
          <input type="checkbox" checked={s.sound} onChange={(e) => updateSettings({ sound: e.target.checked })} />
          {t.shell.sound}
        </label>
        <button className="btn primary" type="submit">
          {t.common.actions.save}
        </button>
        {saved && <p className="muted small center">{t.shell.saved}</p>}
      </form>
    </section>
  );
}
