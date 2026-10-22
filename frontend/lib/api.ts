// Client HTTP du navigateur. Il ne parle QU'au relais serveur du front (/api/...),
// jamais directement à l'API : la clé et la session restent côté serveur/cookie.

import { isLang, type Lang } from "./i18n/core";

// Repli quand l'API ne donne pas de message (les `detail` sont déjà traduits par le
// backend). La langue est celle de <html lang>, posée par le layout.
const NETWORK_ERROR: Record<Lang, string> = { fr: "Erreur réseau.", en: "Network error." };

function networkError(): string {
  const l = typeof document !== "undefined" ? document.documentElement.lang : "";
  return NETWORK_ERROR[isLang(l) ? l : "fr"];
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function api<T>(path: string, init?: { method?: string; body?: unknown }): Promise<T> {
  const res = await fetch(`/api/${path.replace(/^\//, "")}`, {
    method: init?.method ?? (init?.body !== undefined ? "POST" : "GET"),
    headers: init?.body !== undefined ? { "content-type": "application/json" } : undefined,
    body: init?.body !== undefined ? JSON.stringify(init.body) : undefined,
    cache: "no-store",
  });
  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (!res.ok) {
    const detail = (data as { detail?: unknown } | null)?.detail;
    throw new ApiError(res.status, typeof detail === "string" ? detail : networkError());
  }
  return data as T;
}
