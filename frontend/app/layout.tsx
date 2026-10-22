import type { Metadata, Viewport } from "next";
import { Shell } from "@/components/ui/Shell";
import { I18nProvider } from "@/lib/i18n/client";
import { getLang, getT } from "@/lib/i18n/server";
import { fullSite } from "@/lib/site";
import "./globals.css";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT();
  return { title: t.common.meta.title, description: t.common.meta.description };
}

export const viewport: Viewport = {
  // `cover` : indispensable pour que les env(safe-area-inset-*) fonctionnent sur iOS.
  viewportFit: "cover",
  themeColor: "#262421",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const lang = await getLang();
  return (
    <html lang={lang}>
      <body>
        <I18nProvider lang={lang}>
          <Shell fullSite={fullSite()}>{children}</Shell>
        </I18nProvider>
      </body>
    </html>
  );
}
