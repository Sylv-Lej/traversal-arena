"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useT } from "@/lib/i18n/client";
import { useMe } from "@/lib/me";

/** Lien reçu par email (`/verify?token=…`) : confirme l'adresse, même sur un autre appareil. */
function VerifyInner() {
  const token = useSearchParams().get("token") ?? "";
  const t = useT();
  const { refresh } = useMe();
  const [state, setState] = useState<"busy" | "ok" | string>("busy");
  const sent = useRef(false); // une seule tentative (le lien est à usage unique)

  useEffect(() => {
    if (sent.current) return;
    sent.current = true;
    api("auth/verify", { body: { token } })
      .then(() => {
        setState("ok");
        void refresh();
      })
      .catch((e: Error) => setState(e.message));
  }, [token, refresh]);

  return (
    <div className="page narrow">
      <div className="card authCard stack">
        <h1>{t.auth.verifyTitle}</h1>
        {state === "busy" ? (
          <p className="muted">{t.auth.verifying}</p>
        ) : state === "ok" ? (
          <>
            <p>{t.auth.verifyOk}</p>
            <Link href="/arena/new" className="btn primary big">
              {t.auth.verifyGo}
            </Link>
          </>
        ) : (
          <p className="error">{state}</p>
        )}
      </div>
    </div>
  );
}

export default function VerifyPage() {
  return (
    <Suspense>
      <VerifyInner />
    </Suspense>
  );
}
