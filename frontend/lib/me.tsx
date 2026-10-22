"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api } from "./api";
import type { Me } from "./types";

interface MeCtx {
  me: Me | null;
  ready: boolean;
  refresh: () => Promise<void>;
  rename: (name: string, country?: string) => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, country: string) => Promise<void>;
  logout: () => Promise<void>;
  forgot: (email: string) => Promise<void>;
  resetPassword: (token: string, password: string) => Promise<void>;
  changePassword: (current: string, next: string) => Promise<void>;
}

const noop = async () => {};
const Ctx = createContext<MeCtx>({
  me: null,
  ready: false,
  refresh: noop,
  rename: noop,
  login: noop,
  signup: noop,
  logout: noop,
  forgot: noop,
  resetPassword: noop,
  changePassword: noop,
});

/**
 * Le joueur courant. Le premier appel (/me) crée la session invité si besoin (le relais
 * pose le cookie) : les autres appels attendent `ready` pour ne pas créer plusieurs
 * invités en parallèle.
 */
export function MeProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [ready, setReady] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setMe(await api<Me>("me"));
    } catch {
      setMe(null);
    } finally {
      setReady(true);
    }
  }, []);

  const rename = useCallback(async (name: string, country?: string) => {
    setMe(await api<Me>("me", { method: "PATCH", body: { name, country: country || undefined } }));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    setMe(await api<Me>("auth/login", { body: { email, password } }));
  }, []);

  // Réclame le compte invité courant : on garde pseudo, parties et classement.
  const signup = useCallback(async (email: string, password: string, country: string) => {
    setMe(await api<Me>("auth/signup", { body: { email, password, country } }));
  }, []);

  const logout = useCallback(async () => {
    await api("auth/logout", { body: {} });
    await refresh(); // nouvelle session invité
  }, [refresh]);

  const forgot = useCallback(async (email: string) => {
    await api("auth/forgot", { body: { email } });
  }, []);

  // Lien reçu par email : nouveau mot de passe, et connexion directe (cookie posé par le relais).
  const resetPassword = useCallback(async (token: string, password: string) => {
    setMe(await api<Me>("auth/reset", { body: { token, password } }));
  }, []);

  const changePassword = useCallback(async (current: string, next: string) => {
    await api("auth/password", { body: { current, new: next } });
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <Ctx.Provider value={{ me, ready, refresh, rename, login, signup, logout, forgot, resetPassword, changePassword }}>
      {children}
    </Ctx.Provider>
  );
}

export const useMe = () => useContext(Ctx);
