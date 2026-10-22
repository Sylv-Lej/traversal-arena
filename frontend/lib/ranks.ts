// Données des rangs partagées entre composants serveur et client (pas de "use client").

// Ordre des paliers : sert à dessiner (ornements de plus en plus riches) et à comparer.
export const TIER_ORDER = ["slate", "bronze", "silver", "gold", "jade", "sapphire", "diamond", "master", "legend"] as const;
export type TierKey = (typeof TIER_ORDER)[number];

// Nom des paliers et étapes de l’ascension : `t.common.tiers` / `t.common.zones`.
