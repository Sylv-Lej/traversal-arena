"use client";

import { useT } from "@/lib/i18n/client";

/** Indicateur de chargement (spinner + libellé). `page` : centré dans une zone haute, pour un écran entier. */
export function Loader({ label, page }: { label?: string; page?: boolean }) {
  const t = useT();
  return (
    <div className={page ? "loader pageLoader" : "loader"} role="status" aria-live="polite">
      <span className={page ? "spinner big" : "spinner"} />
      <span>{label ?? t.common.actions.loading}</span>
    </div>
  );
}
