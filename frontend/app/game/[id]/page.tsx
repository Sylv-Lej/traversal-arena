import { GameClient } from "@/components/game/GameClient";

export default async function GamePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <GameClient id={id} />;
}
