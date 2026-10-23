"use client";

import { Flag } from "./Flag";
import Link from "next/link";
import { createContext, useContext } from "react";
import { usePathname } from "next/navigation";
import { LANGS } from "@/lib/i18n/core";
import { useLang, useT } from "@/lib/i18n/client";
import { MeProvider, useMe } from "@/lib/me";
import { IconArena, IconBook, IconChart, IconBot, IconEye, IconPuzzle, IconGear, IconHome, IconPlay, IconTrophy, IconUser, Logo } from "./icons";

// Arène seule (défaut) : seuls l'arène et les règles apparaissent. Avec FULL_SITE=1
// (`lib/site.ts`), les onglets du site complet s'ajoutent, après un séparateur.
const NAV = [
  { href: "/arena", key: "arena", Icon: IconArena },
  { href: "/analyse", key: "analyse", Icon: IconChart },
  { href: "/rules", key: "rules", Icon: IconBook },
] as const;
const NAV_SOON = [
  { href: "/play", key: "play", Icon: IconPlay },
  { href: "/play?tab=bot", key: "bots", Icon: IconBot },
  { href: "/puzzles", key: "puzzles", Icon: IconPuzzle },
  { href: "/watch", key: "watch", Icon: IconEye },
  { href: "/leaderboard", key: "leaderboard", Icon: IconTrophy },
] as const;

const FullSiteContext = createContext(false);

/** Site complet (FULL_SITE) ou arène seule : pour ne pas montrer de liens vers des pages fermées. */
export function useFullSite(): boolean {
  return useContext(FullSiteContext);
}

/** Sélecteur de langue (FR / EN) : cookie + rafraîchissement des composants serveur. */
export function LangSwitch() {
  const { lang, setLang } = useLang();
  const t = useT();
  return (
    <div className="segmented langSwitch" role="group" aria-label={t.common.lang.label}>
      {LANGS.map((l) => (
        <button type="button" key={l} className={lang === l ? "on" : ""} lang={l} aria-pressed={lang === l} onClick={() => setLang(l)}>
          {t.common.lang[l]}
        </button>
      ))}
    </div>
  );
}

function Avatar({ name, size = 32 }: { name: string; size?: number }) {
  const hue = [...name].reduce((a, c) => a + c.charCodeAt(0), 0) % 360;
  return (
    <span className="avatar" style={{ width: size, height: size, background: `linear-gradient(135deg, hsl(${hue} 45% 52%), hsl(${(hue + 40) % 360} 45% 34%))` }}>
      {name.slice(0, 1).toUpperCase()}
    </span>
  );
}

export { Avatar };

function Frame({ children, fullSite }: { children: React.ReactNode; fullSite: boolean }) {
  const path = usePathname();
  const t = useT();
  const { me } = useMe();
  const isActive = (href: string) => path.startsWith(href);
  /** Onglet du site complet : affiché seulement avec FULL_SITE. */
  const soon = (key: (typeof NAV_SOON)[number]["key"] | "home", Icon: React.ComponentType, href: string) =>
    fullSite && (
      <Link key={key} href={href} className={path === href.split("?")[0] && !href.includes("?") ? "active" : ""}>
        <Icon />
        <span>{t.common.nav[key]}</span>
      </Link>
    );

  return (
    <div className="shell">
      <aside className="sidebar">
        <Link href="/" className="brand">
          <Logo size={30} />
          <span className="brandName">
            Traversal<small>Bot Arena</small>
          </span>
        </Link>
        <nav>
          {NAV.map(({ href, key, Icon }) => (
            <Link key={href} href={href} className={isActive(href) ? "active" : ""}>
              <Icon />
              <span>{t.common.nav[key]}</span>
            </Link>
          ))}
          {fullSite && <hr className="navSep" />}
          {NAV_SOON.map(({ key, Icon, href }) => soon(key, Icon, href))}
        </nav>
        <div className="sidebarFoot">
          {me && (
            <Link href="/profile" className="meChip">
              <Avatar name={me.name} size={28} />
              <span>{me.name}</span>
              <Flag code={me.country} />
            </Link>
          )}
          {me?.isGuest && (
            <Link href="/login?tab=signup" className="btn small primary signupBtn">
              {t.common.nav.signup}
            </Link>
          )}
          <LangSwitch />
          <Link href="/profile#settings" className={`navBtn ${path === "/profile" ? "active" : ""}`}>
            <IconGear />
            <span>{t.common.nav.settings}</span>
          </Link>
        </div>
      </aside>

      <main className="main">{children}</main>

      <nav className="bottomNav">
        {NAV.map(({ href, key, Icon }) => (
          <Link key={href} href={href} className={isActive(href) ? "active" : ""}>
            <Icon />
            <span>{t.common.nav[key]}</span>
          </Link>
        ))}
        {fullSite && <span className="navSep" aria-hidden="true" />}
        {soon("home", IconHome, "/")}
        {soon("play", IconPlay, "/play")}
        {/* Le compte reste accessible : il en faut un pour inscrire un bot. */}
        <Link href="/profile" className={path === "/profile" ? "active" : ""}>
          <IconUser />
          <span>{t.common.nav.profile}</span>
        </Link>
      </nav>
    </div>
  );
}

export function Shell({ children, fullSite = false }: { children: React.ReactNode; fullSite?: boolean }) {
  return (
    <MeProvider>
      <FullSiteContext.Provider value={fullSite}>
        <Frame fullSite={fullSite}>{children}</Frame>
      </FullSiteContext.Provider>
    </MeProvider>
  );
}
