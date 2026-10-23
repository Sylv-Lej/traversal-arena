"use client";

import { Loader } from "@/components/ui/Loader";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { arenaName, type ArenaBot, type ArenaInfo, type MyBot } from "@/lib/arena";
import { useT } from "@/lib/i18n/client";
import { VerifyNotice } from "@/components/ui/VerifyNotice";
import { useMe } from "@/lib/me";

// Dépôt public du SDK (miroir de engine-rs, `make sdk-push`). Tag : la version publiée.
const SDK_REPO = "https://github.com/Sylv-Lej/traversal-rust-sdk";
const BUILD = `cargo build --release --target wasm32-unknown-unknown
# -> target/wasm32-unknown-unknown/release/mon_bot.wasm`;
const DUEL = `git clone ${SDK_REPO} && cd traversal-rust-sdk
docker build -f arena/Dockerfile -t traversal-arena .
docker run --rm -v "$PWD":/w traversal-arena duel /w/mon_bot.wasm sommet --games 20`;
const CARGO = `[lib]
crate-type = ["cdylib"]

[dependencies]
traversal-bot = { git = "${SDK_REPO}", tag = "v0.2.0" }`;
const STARTER = `use traversal_bot::core::MoveKind;
use traversal_bot::{bot, Turn};

// turn.state : la position, turn.moves : les coups légaux, turn.seed : le hasard.
fn choose(turn: &Turn) -> usize {
    // Une sortie si possible, sinon le premier coup.
    turn.moves.iter().position(|m| m.kind == MoveKind::Exit).unwrap_or(0)
}

bot!(choose);`;

/** Fichier binaire -> base64 (par morceaux : `btoa` n'accepte pas un très long argument). */
async function toBase64(file: File): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(bin);
}

export default function NewBotPage() {
  return (
    <Suspense>
      <NewBot />
    </Suspense>
  );
}

function NewBot() {
  const t = useT();
  const router = useRouter();
  const { me, ready } = useMe();
  const [info, setInfo] = useState<ArenaInfo | null>(null);
  const [name, setName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Mise à jour : nouvelle version d'un de mes bots (`?update=<id>` depuis sa fiche).
  const [mine, setMine] = useState<MyBot[]>([]);
  const [replaces, setReplaces] = useState<string | null>(useSearchParams().get("update"));
  const updating = replaces !== null;

  useEffect(() => {
    api<ArenaInfo>("arena/info").then(setInfo).catch(() => setInfo(null));
  }, []);
  useEffect(() => {
    if (ready && me && !me.isGuest) api<MyBot[]>("arena/mine").then(setMine).catch(() => setMine([]));
  }, [ready, me]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;
    if (info && file.size > info.maxWasmKb * 1024) {
      setError(t.arena.tooBig(info.maxWasmKb));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const body = updating ? { replaces } : { name: name.trim() };
      const bot = await api<ArenaBot>("arena/bots", { body: { ...body, wasm: await toBase64(file) } });
      router.push(`/arena/bot/${bot.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t.common.errors.generic);
      setBusy(false);
    }
  };

  return (
    <div className="page narrow">
      <p className="small">
        <Link href="/arena">← {t.arena.title}</Link>
      </p>
      <h1 className="pageTitle">{t.arena.newTitle}</h1>
      <p className="muted">{t.arena.newIntro}</p>

      <div className="card">
        <h2 className="cardTitle">{t.arena.upload}</h2>
        {!ready ? (
          <Loader />
        ) : !me || me.isGuest ? (
          <p>
            {t.arena.needAccount}{" "}
            <Link href="/login?tab=signup" className="btn primary small">
              {t.arena.signup}
            </Link>
          </p>
        ) : !me.emailVerified ? (
          <VerifyNotice email={me.email ?? ""} />
        ) : (
          <form className="botForm" onSubmit={submit}>
            <label className="field">
              <span>{t.arena.file}</span>
              <input type="file" accept=".wasm,application/wasm" onChange={(e) => setFile(e.target.files?.[0] ?? null)} required />
            </label>
            {file && mine.length > 0 && (
              <div className="field">
                <span>{t.arena.kind}</span>
                <div className="segmented">
                  <button type="button" className={updating ? "" : "on"} onClick={() => setReplaces(null)}>
                    {t.arena.kindNew}
                  </button>
                  <button type="button" className={updating ? "on" : ""} onClick={() => setReplaces(replaces ?? "")}>
                    {t.arena.kindUpdate}
                  </button>
                </div>
              </div>
            )}
            {file &&
              (updating && mine.length > 0 ? (
                <fieldset className="field">
                  <span>{t.arena.pickBot}</span>
                  <ul className="versionList">
                    {mine.map((b) => (
                      <li key={b.id}>
                        <label className="check grow">
                          <input type="radio" name="replaces" checked={replaces === b.id} onChange={() => setReplaces(b.id)} />
                          <span className="botName">{arenaName(b, t)}</span>
                        </label>
                        <span className={`chip ${b.status}`}>{t.arena.status[b.status]}</span>
                      </li>
                    ))}
                  </ul>
                  <small className="muted">{t.arena.updateHint}</small>
                </fieldset>
              ) : (
                <label className="field">
                  <span>{t.arena.name}</span>
                  <input value={name} onChange={(e) => setName(e.target.value)} placeholder={t.arena.namePlaceholder} maxLength={24} required />
                  <small className="muted">{t.arena.nameHint}</small>
                </label>
              ))}
            {error && <p className="error">{error}</p>}
            <button
              className="btn primary"
              disabled={busy || !file || (updating ? !mine.some((b) => b.id === replaces) : name.trim().length < 3)}
            >
              {busy ? t.arena.sending : t.arena.send}
            </button>
            {info && <small className="muted">{t.arena.limitsNote(info.maxLiveBots)}</small>}
          </form>
        )}
      </div>

      <div className="card">
        <h2 className="cardTitle">{t.arena.quick}</h2>
        <p>
          <a href={SDK_REPO} target="_blank" rel="noreferrer">
            {SDK_REPO.replace("https://", "")}
          </a>
        </p>
        <ol className="steps">
          <li>
            {t.arena.quickSteps[0]}
            <pre className="codeBlock">
              <code>{CARGO}</code>
            </pre>
            <pre className="codeBlock">
              <code>{STARTER}</code>
            </pre>
          </li>
          <li>
            {t.arena.quickSteps[1]}
            <pre className="codeBlock">
              <code>{BUILD}</code>
            </pre>
          </li>
          <li>
            {t.arena.quickSteps[2]}
            <pre className="codeBlock">
              <code>{DUEL}</code>
            </pre>
          </li>
          <li>{t.arena.quickSteps[3]}</li>
        </ol>
      </div>

      {info && (
        <div className="card">
          <h2 className="cardTitle">{t.arena.rules}</h2>
          <ul className="steps">
            {t.arena.limits(info.fuelPerMove / 1_000_000, info.memoryMb, info.maxWasmKb).map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="card">
        <h2 className="cardTitle">{t.arena.abi}</h2>
        <p>{t.arena.abiIntro}</p>
        <ul className="steps">
          {t.arena.abiExports.map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ul>
        <p>{t.arena.abiImports}</p>
        <p>{t.arena.abiFormat}</p>
        <pre className="codeBlock">
          <code>{t.arena.abiTable}</code>
        </pre>
      </div>
    </div>
  );
}
