// Langue côté composants serveur (lit le cookie, sinon Accept-Language).
import { cookies, headers } from "next/headers";
import { LANG_COOKIE, pickLang, type Lang } from "./core";
import { DICTS, type Dict } from "./dict";

export async function getLang(): Promise<Lang> {
  const [c, h] = await Promise.all([cookies(), headers()]);
  return pickLang(c.get(LANG_COOKIE)?.value, h.get("accept-language"));
}

export async function getT(): Promise<Dict> {
  return DICTS[await getLang()];
}
