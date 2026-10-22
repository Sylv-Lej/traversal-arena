import { NextResponse, type NextRequest } from "next/server";

/**
 * Pages du site complet (jouer, puzzles, regarder, classement des joueurs, matchs) :
 * redirigées vers l'accueil tant que FULL_SITE n'est pas activé (voir `lib/site.ts`).
 * Runtime Node : la variable est relue à chaque requête (rouvrir = changer la variable).
 */
export function middleware(req: NextRequest) {
  if (process.env.FULL_SITE === "1") return NextResponse.next();
  // `nextUrl` garde l'hôte demandé par le visiteur (en-têtes Host / X-Forwarded-*).
  const home = req.nextUrl.clone();
  home.pathname = "/";
  home.search = "";
  return NextResponse.redirect(home, 307);
}

export const config = {
  matcher: ["/play/:path*", "/puzzles/:path*", "/watch/:path*", "/leaderboard/:path*", "/match/:path*"],
  runtime: "nodejs",
};
