import { NextRequest, NextResponse } from "next/server";
import { LANG_COOKIE, pickLang, type Lang } from "@/lib/i18n/core";
import { closedApi } from "@/lib/site";

/**
 * Relais serveur unique entre le navigateur et l'API (règle du monolith : le
 * navigateur n'appelle jamais l'API directement).
 *
 * - La clé d'API (`API_KEY`) reste ici, côté serveur : jamais livrée au navigateur.
 * - La session du joueur vit dans un cookie `httpOnly` ; on la relaie en `x-session`.
 *   Pas de cookie, ou session inconnue de l'API (redémarrage en dev) : on crée un
 *   invité à la volée et on pose le cookie — le joueur n'a jamais d'écran de login.
 * - Les flux SSE (`/games/:id/stream`) sont relayés en streaming, sans buffer.
 * - La langue du joueur (cookie `tv_lang`, sinon Accept-Language) part en `x-lang` :
 *   l'API répond ses messages d'erreur (et l'email de réinitialisation) dans cette langue.
 * - Anti-CSRF : toute requête qui modifie quelque chose doit venir de NOS pages
 *   (`sameOrigin`). `SameSite=Lax` seul ne suffit pas : un site « voisin » (même domaine
 *   enregistrable, ex. un autre container sur `*.scw.cloud`) passerait.
 */

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const API_URL = (process.env.API_URL ?? "http://localhost:8000").replace(/\/$/, "");
const API_KEY = process.env.API_KEY ?? "";
const COOKIE = "tv_session";
// Liste blanche : seules ces routes de l'API sont exposées au navigateur (pas la
// création de joueur, réservée au relais lui-même, ni l'API du runner de l'arène).
const ALLOWED = /^(players\/[\w-]+(\/history)?|me|me\/games|games|games\/[\w-]+(\/[\w-]+){0,2}|matches|matches\/[\w-]+(\/[\w-]+)?|puzzles(\/[\w-]+){1,3}|lobby|lobby\/seek|leaderboard|ranks|terrain|sandbox|imports(\/status)?|arena\/(info|leaderboard|showcase|mine|bots|bots\/[\w-]+(\/retire)?)|auth\/(login|signup|logout|forgot|reset|password|verify|resend))$/;
const COOKIE_OPTS = {
  httpOnly: true,
  sameSite: "lax" as const,
  secure: process.env.NODE_ENV === "production",
  path: "/",
  // Aligné sur l'expiration glissante des sessions côté API (60 jours sans visite).
  maxAge: 60 * 60 * 24 * 60,
};

function clientIp(req: NextRequest): string {
  const forwarded = req.headers.get("x-forwarded-for");
  if (forwarded) {
    const parts = forwarded.split(",");
    return parts[parts.length - 1].trim();
  }
  return req.headers.get("x-real-ip") ?? "unknown";
}

const SAFE_METHODS = new Set(["GET", "HEAD"]);
// Le plus gros corps légitime : un bot de l'arène (1 Mo, ~1,4 Mo en base64). Même plafond
// que l'API (`backend/app/bodylimit.py`).
const MAX_BODY_BYTES = 2 * 1024 * 1024;

/** Corps de la requête, lu morceau par morceau et abandonné au-delà du plafond (null). */
async function readBody(req: NextRequest): Promise<string | null> {
  const declared = Number(req.headers.get("content-length") ?? "0");
  if (declared > MAX_BODY_BYTES) return null;
  if (!req.body) return "";
  const reader = req.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > MAX_BODY_BYTES) {
      await reader.cancel();
      return null;
    }
    chunks.push(value);
  }
  return Buffer.concat(chunks).toString("utf8");
}

/** La requête vient-elle d'une page de ce site ? (pas d'un autre site, même voisin) */
function sameOrigin(req: NextRequest): boolean {
  // Navigateurs récents : en-tête posé par le navigateur, impossible à forger en JS.
  const site = req.headers.get("sec-fetch-site");
  if (site) return site === "same-origin";
  // Plus anciens : l'Origin doit correspondre à l'hôte servi.
  const origin = req.headers.get("origin");
  if (!origin) return true; // pas un navigateur (curl…) : il n'a pas les cookies d'un autre
  const host = req.headers.get("x-forwarded-host") ?? req.headers.get("host");
  try {
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}

const MESSAGES: Record<Lang, { origin: string; notFound: string; unreachable: string; misconfigured: string; tooLarge: string }> = {
  fr: {
    tooLarge: "Requête trop volumineuse.",
    origin: "Requête refusée (origine).",
    notFound: "Introuvable.",
    unreachable: "Serveur de jeu injoignable.",
    misconfigured: "Front mal configuré : clé d'API absente.",
  },
  en: {
    tooLarge: "Request too large.",
    origin: "Request refused (origin).",
    notFound: "Not found.",
    unreachable: "Can’t reach the game server.",
    misconfigured: "Frontend misconfigured: missing API key.",
  },
};

function langOf(req: NextRequest): Lang {
  return pickLang(req.cookies.get(LANG_COOKIE)?.value, req.headers.get("accept-language"));
}

async function createGuest(req: NextRequest): Promise<string | null> {
  const res = await fetch(`${API_URL}/api/players`, {
    method: "POST",
    headers: { "content-type": "application/json", "x-api-key": API_KEY, "x-client-ip": clientIp(req), "x-lang": langOf(req) },
    body: "{}",
    cache: "no-store",
  });
  if (!res.ok) return null;
  const data = (await res.json()) as { token: string };
  return data.token;
}

async function forward(req: NextRequest, sub: string, token: string, body: string | undefined) {
  const headers: Record<string, string> = {
    "x-api-key": API_KEY,
    "x-client-ip": clientIp(req),
    "x-session": token,
    "x-lang": langOf(req),
    accept: req.headers.get("accept") ?? "application/json",
  };
  if (body !== undefined) headers["content-type"] = "application/json";
  return fetch(`${API_URL}/api/${sub}${req.nextUrl.search}`, {
    method: req.method,
    headers,
    body,
    cache: "no-store",
    // Le client ferme l'onglet : on coupe aussi le flux SSE en amont.
    signal: req.signal,
  });
}

async function handler(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const msg = MESSAGES[langOf(req)];
  if (!API_KEY) {
    return NextResponse.json({ detail: msg.misconfigured }, { status: 503 });
  }
  if (!SAFE_METHODS.has(req.method) && !sameOrigin(req)) {
    return NextResponse.json({ detail: msg.origin }, { status: 403 });
  }
  const { path } = await ctx.params;
  const sub = path.map(encodeURIComponent).join("/");
  // Hors site complet (FULL_SITE), les routes des fonctions fermées n'existent pas.
  if (!ALLOWED.test(sub) || closedApi(sub)) {
    return NextResponse.json({ detail: msg.notFound }, { status: 404 });
  }

  let body: string | undefined;
  if (!SAFE_METHODS.has(req.method)) {
    const raw = await readBody(req);
    if (raw === null) return NextResponse.json({ detail: msg.tooLarge }, { status: 413 });
    body = raw || "{}";
  }
  let token = req.cookies.get(COOKIE)?.value ?? "";
  let fresh: string | null = null;

  let upstream: Response;
  try {
    // Pas encore de session : seul /me en crée une d'office (premier appel de chaque
    // page). Les routes publiques (terrain, classement…) n'en ont pas besoin, et les
    // autres déclenchent la création via le 401 ci-dessous.
    if (!token && sub === "me") {
      fresh = await createGuest(req);
      token = fresh ?? "";
    }
    upstream = await forward(req, sub, token, body);
    if (upstream.status === 401) {
      const detail = await upstream.clone().json().catch(() => null);
      if (detail?.detail === "session") {
        fresh = await createGuest(req);
        token = fresh ?? "";
        upstream = await forward(req, sub, token, body);
      }
    }
  } catch {
    return NextResponse.json({ detail: msg.unreachable }, { status: 502 });
  }

  // Connexion / nouveau mot de passe : l'API renvoie un nouveau jeton -> il devient le cookie, et ne part
  // jamais au navigateur dans le corps de la réponse.
  if ((sub === "auth/login" || sub === "auth/reset") && upstream.ok) {
    const data = (await upstream.json()) as { token: string; player: unknown };
    const res = NextResponse.json(data.player, { headers: { "cache-control": "no-store" } });
    res.cookies.set(COOKIE, data.token, COOKIE_OPTS);
    return res;
  }
  if (sub === "auth/logout") {
    const res = NextResponse.json({ ok: true }, { headers: { "cache-control": "no-store" } });
    res.cookies.delete(COOKIE);
    return res;
  }

  const isStream = (upstream.headers.get("content-type") ?? "").startsWith("text/event-stream");
  const res = new NextResponse(upstream.body, {
    status: upstream.status,
    headers: {
      "content-type": upstream.headers.get("content-type") ?? "application/json",
      "cache-control": isStream ? "no-cache, no-transform" : "no-store",
      ...(isStream ? { "x-accel-buffering": "no", connection: "keep-alive" } : {}),
    },
  });
  if (fresh) {
    res.cookies.set(COOKIE, fresh, COOKIE_OPTS);
  }
  return res;
}

export { handler as GET, handler as POST, handler as PATCH, handler as DELETE };
