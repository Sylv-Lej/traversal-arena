#!/bin/sh
# Recopie le SDK des bots dans son dépôt public (miroir) : `make sdk-sync`.
#
#   sh scripts/sync_sdk.sh ../traversal-rust-sdk
#
# Le dépôt public est entièrement RÉGÉNÉRÉ (tout sauf .git) : on n'y édite rien, la
# référence est ici. Il contient traversal-core, traversal-bot, les bots d'exemple et le
# runner (pour tester en local) ; pas le module Python ni la CLI de simulation.
set -eu
SRC=$(cd "$(dirname "$0")/.." && pwd)
DEST=${1:?usage : sync_sdk.sh <dépôt du SDK>}
[ -d "$DEST/.git" ] || { echo "$DEST n'est pas un dépôt git" >&2; exit 1; }
VERSION=$(sed -n 's/^version = "\(.*\)"$/\1/p' "$SRC/Cargo.toml" | head -1)

STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
for d in core sdk bots arena; do
  rsync -a --exclude target "$SRC/$d" "$STAGE/"
done
cp "$SRC/boards.json" "$SRC/.dockerignore" "$SRC/sdk-repo/README.md" "$SRC/sdk-repo/LICENSE" "$STAGE/"
cp "$SRC/sdk-repo/gitignore" "$STAGE/.gitignore"
sed "s/@VERSION@/$VERSION/" "$SRC/sdk-repo/Cargo.toml" > "$STAGE/Cargo.toml"
# Le tag cité dans les README (`tag = "vX.Y.Z"`) est celui de cette version.
for f in README.md sdk/README.md; do
  sed "s/@VERSION@/$VERSION/g" "$STAGE/$f" > "$STAGE/$f.tmp" && mv "$STAGE/$f.tmp" "$STAGE/$f"
done
# Les crates publiés portent leur licence.
cp "$SRC/sdk-repo/LICENSE" "$STAGE/core/LICENSE"
cp "$SRC/sdk-repo/LICENSE" "$STAGE/sdk/LICENSE"
# Pas de dépendance externe dans ce workspace : le Cargo.lock se génère hors ligne.
docker run --rm -v "$STAGE":/w -w /w rust:1.88-slim cargo generate-lockfile --offline -q

# target/ : cache de compilation du dépôt du SDK, gardé. bots/custom/ : bots personnels,
# ignorés par git dans le dépôt du SDK, gardés aussi.
rsync -a --delete --exclude .git --exclude target --exclude /bots/custom "$STAGE/" "$DEST/"
echo "SDK $VERSION recopié dans $DEST"
