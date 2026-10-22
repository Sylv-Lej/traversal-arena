"use client";

import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useState } from "react";
import { LANG_COOKIE, type Lang } from "./core";
import { DICTS, type Dict } from "./dict";

const Ctx = createContext<{ lang: Lang; setLang: (l: Lang) => void }>({ lang: "fr", setLang: () => {} });

/** Fournie par le layout (serveur), qui a lu la langue dans le cookie / Accept-Language. */
export function I18nProvider({ lang: initial, children }: { lang: Lang; children: React.ReactNode }) {
  const [lang, setState] = useState<Lang>(initial);
  const router = useRouter();
  const setLang = useCallback(
    (l: Lang) => {
      document.cookie = `${LANG_COOKIE}=${l}; path=/; max-age=${60 * 60 * 24 * 365}; samesite=lax`;
      document.documentElement.lang = l;
      setState(l);
      router.refresh(); // composants serveur (règles, rangs, titres) dans la nouvelle langue
    },
    [router],
  );
  return <Ctx.Provider value={{ lang, setLang }}>{children}</Ctx.Provider>;
}

/** Dictionnaire de la langue courante : `const t = useT(); t.play.title`. */
export function useT(): Dict {
  return DICTS[useContext(Ctx).lang];
}

export function useLang() {
  return useContext(Ctx);
}
