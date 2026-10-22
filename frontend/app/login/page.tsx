"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { CountrySelect } from "@/components/ui/Flag";
import { guessCountry } from "@/lib/countries";
import { useT } from "@/lib/i18n/client";
import { useMe } from "@/lib/me";
import { useFullSite } from "@/components/ui/Shell";

function ChangePassword() {
  const { changePassword } = useMe();
  const t = useT();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <div className="card authCard">
      <h2 className="cardTitle">{t.auth.changePassword}</h2>
      <form
        className="stack"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setMsg(null);
          try {
            await changePassword(current, next);
            setMsg({ ok: true, text: t.auth.passwordChanged });
            setCurrent("");
            setNext("");
          } catch (ex) {
            setMsg({ ok: false, text: (ex as Error).message });
          } finally {
            setBusy(false);
          }
        }}
      >
        <label className="field">
          <span>{t.auth.currentPassword}</span>
          <input type="password" autoComplete="current-password" required value={current} onChange={(e) => setCurrent(e.target.value)} />
        </label>
        <label className="field">
          <span>
            {t.auth.newPassword} <small className="muted">{t.auth.minChars}</small>
          </span>
          <input type="password" autoComplete="new-password" required minLength={8} value={next} onChange={(e) => setNext(e.target.value)} />
        </label>
        {msg && <p className={msg.ok ? "success" : "error"}>{msg.text}</p>}
        <button className="btn" type="submit" disabled={busy}>
          {t.auth.changePassword}
        </button>
      </form>
    </div>
  );
}

function LoginInner() {
  const router = useRouter();
  const params = useSearchParams();
  const { me, login, signup, logout } = useMe();
  const t = useT();
  const fullSite = useFullSite();
  const [tab, setTab] = useState<"login" | "signup">(params.get("tab") === "signup" ? "signup" : "login");
  // Pays pré-rempli d'après le navigateur (« fr-BE » → Belgique), à confirmer.
  const [country, setCountry] = useState("");
  useEffect(() => setCountry((c) => c || guessCountry()), []);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (me && !me.isGuest) {
    return (
      <div className="page narrow">
        <div className="card authCard">
          <h1>{t.auth.loggedIn}</h1>
          <p>
            {t.auth.loggedInAs} <b>{me.name}</b> ({me.email}).
          </p>
          <div className="stack">
            {fullSite ? (
              <Link className="btn primary" href="/play">
                {t.common.nav.play}
              </Link>
            ) : (
              <Link className="btn primary" href="/arena">
                {t.arena.title}
              </Link>
            )}
            <button className="btn ghost" onClick={() => void logout()}>
              {t.auth.logOut}
            </button>
          </div>
        </div>
        <ChangePassword />
      </div>
    );
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (tab === "login") await login(email, password);
      else await signup(email, password, country);
      router.push("/");
    } catch (ex) {
      setError((ex as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page narrow">
      <div className="card authCard">
        <div className="tabs big">
          <button className={tab === "login" ? "on" : ""} onClick={() => setTab("login")}>
            {t.auth.logIn}
          </button>
          <button className={tab === "signup" ? "on" : ""} onClick={() => setTab("signup")}>
            {t.auth.createAccount}
          </button>
        </div>
        {tab === "signup" && me && (
          <p className="muted">
            {t.auth.guestNoticeBefore} <b>{me.name}</b>
            {t.auth.guestNoticeAfter}
          </p>
        )}
        <form className="stack" onSubmit={submit}>
          <label className="field">
            <span>{t.auth.email}</span>
            <input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
          <label className="field">
            <span>
              {t.auth.password} {tab === "signup" && <small className="muted">{t.auth.minChars}</small>}
            </span>
            <input
              type="password"
              autoComplete={tab === "login" ? "current-password" : "new-password"}
              required
              minLength={tab === "signup" ? 8 : undefined}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          {tab === "signup" && (
            <div className="field">
              <span>{t.common.country.label}</span>
              <CountrySelect value={country} onChange={setCountry} required />
              <small className="muted">{t.common.country.hint}</small>
            </div>
          )}
          {error && <p className="error">{error}</p>}
          <button className="btn primary big" type="submit" disabled={busy}>
            {tab === "login" ? t.auth.logIn : t.auth.createMyAccount}
          </button>
        </form>
        {tab === "login" && (
          <p className="center small">
            <Link href="/reset">{t.auth.forgotLink}</Link>
          </p>
        )}
        {tab === "login" && (
          <p className="muted small center">
            {t.auth.noAccount}{" "}
            <button className="linkBtn" onClick={() => setTab("signup")}>
              {t.auth.orCreateOne}
            </button>
            .
          </p>
        )}
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginInner />
    </Suspense>
  );
}
