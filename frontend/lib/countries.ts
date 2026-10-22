// Pays qu'un joueur peut représenter : codes ISO 3166-1 alpha-2 (+ XK, Kosovo).
// Même liste que le backend (`backend/app/countries.py`) ; un drapeau par code dans
// `public/flags/<code>.svg` (flag-icons, MIT). Les noms viennent du navigateur
// (`Intl.DisplayNames`) : traduits dans toutes les langues sans rien embarquer.

import type { Lang } from "./i18n/core";

export const COUNTRIES: readonly string[] = `AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CP CR CU CV CW CX CY CZ DE DG DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU IC ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS XK YE YT ZA ZM ZW`.split(" ");

const names = new Map<Lang, Intl.DisplayNames>();

export function countryName(code: string, lang: Lang): string {
  let d = names.get(lang);
  if (!d) {
    d = new Intl.DisplayNames([lang], { type: "region" });
    names.set(lang, d);
  }
  try {
    return d.of(code.toUpperCase()) ?? code;
  } catch {
    return code;
  }
}

/** Pays triés par nom dans la langue du joueur (pour la liste de choix). */
export function sortedCountries(lang: Lang): { code: string; name: string }[] {
  return COUNTRIES.map((code) => ({ code, name: countryName(code, lang) })).sort((a, b) => a.name.localeCompare(b.name, lang));
}

/** Pays probable d'après le navigateur (« fr-BE » → BE), à confirmer par le joueur. */
export function guessCountry(): string {
  if (typeof navigator === "undefined") return "";
  for (const l of navigator.languages ?? [navigator.language]) {
    const region = l.split("-")[1]?.toUpperCase();
    if (region && COUNTRIES.includes(region)) return region;
  }
  return "";
}
