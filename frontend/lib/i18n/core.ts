// Langues du site, partagées serveur / client (pas de "use client").
//
// La langue vit dans un cookie (`tv_lang`), pas dans l'URL : un lien de partie envoyé à
// un ami s'ouvre dans SA langue. Première visite : langue du navigateur (Accept-Language),
// français par défaut.

export const LANGS = ["fr", "en"] as const;
export type Lang = (typeof LANGS)[number];
export const DEFAULT_LANG: Lang = "fr";
export const LANG_COOKIE = "tv_lang";

export function isLang(v: unknown): v is Lang {
  return typeof v === "string" && (LANGS as readonly string[]).includes(v);
}

/** Cookie s'il est valide, sinon la première langue connue de l'en-tête Accept-Language. */
export function pickLang(cookie?: string | null, acceptLanguage?: string | null): Lang {
  if (isLang(cookie)) return cookie;
  const prefs = (acceptLanguage ?? "")
    .split(",")
    .map((part) => {
      const [tag, q] = part.trim().split(";q=");
      return { lang: tag.slice(0, 2).toLowerCase(), q: q ? Number(q) : 1 };
    })
    .sort((a, b) => b.q - a.q);
  for (const p of prefs) if (isLang(p.lang)) return p.lang;
  return DEFAULT_LANG;
}

/** Locale pour Intl (dates, nombres). */
export const LOCALES: Record<Lang, string> = { fr: "fr-FR", en: "en-GB" };
