"use client";

import { Loader } from "@/components/ui/Loader";
import { PlayerProfile } from "@/components/profile/PlayerProfile";
import { SettingsCard } from "@/components/profile/SettingsCard";
import { useT } from "@/lib/i18n/client";
import { useMe } from "@/lib/me";

/** Mon profil : la fiche publique, puis compte et réglages. */
export default function ProfilePage() {
  const t = useT();
  const { me } = useMe();
  if (!me) return <div className="page narrow"><Loader page /></div>;
  // Clé : après un changement de pseudo ou de pays, la fiche se recharge.
  return (
    <PlayerProfile key={`${me.id}:${me.name}:${me.country ?? ""}`} id={me.id}>
      <SettingsCard />
    </PlayerProfile>
  );
}
