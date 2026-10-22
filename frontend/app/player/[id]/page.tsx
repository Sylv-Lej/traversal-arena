"use client";

import { use } from "react";
import { PlayerProfile } from "@/components/profile/PlayerProfile";

export default function PlayerPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return <PlayerProfile id={id} />;
}
