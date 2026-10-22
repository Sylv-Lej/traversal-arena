"use client";

import { useMemo } from "react";
import { countryName, sortedCountries } from "@/lib/countries";
import { useLang, useT } from "@/lib/i18n/client";

/** Petit drapeau du pays représenté (rien si le joueur n'en a pas choisi). */
export function Flag({ code, size = 14 }: { code: string | null | undefined; size?: number }) {
  const { lang } = useLang();
  if (!code) return null;
  const name = countryName(code, lang);
  return (
    // eslint-disable-next-line @next/next/no-img-element -- SVG statique minuscule, pas besoin de next/image
    <img
      className="flag"
      src={`/flags/${code.toLowerCase()}.svg`}
      width={Math.round((size * 4) / 3)}
      height={size}
      alt={name}
      title={name}
      loading="lazy"
      decoding="async"
    />
  );
}

/** Liste des pays (noms dans la langue du joueur, triés), avec l'aperçu du drapeau. */
export function CountrySelect({
  value,
  onChange,
  required,
}: {
  value: string;
  onChange: (code: string) => void;
  required?: boolean;
}) {
  const { lang } = useLang();
  const t = useT();
  const list = useMemo(() => sortedCountries(lang), [lang]);
  return (
    <div className="countrySelect">
      <span className="countryFlag">{value ? <Flag code={value} size={18} /> : <span className="flag empty" />}</span>
      <select required={required} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="" disabled>
          {t.common.country.choose}
        </option>
        {list.map((c) => (
          <option key={c.code} value={c.code}>
            {c.name}
          </option>
        ))}
      </select>
    </div>
  );
}
