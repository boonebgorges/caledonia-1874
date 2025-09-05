#!/usr/bin/env bash
set -euo pipefail

OUTDIR="web"
ROOT="$(cd "$(dirname "$0")/.."; pwd)"

# 1) Clean
rm -rf "$OUTDIR"
mkdir -p "$OUTDIR/data"

# 2) Export JSONs from Gramps + associations
gramps -O "Caledonia" -e - -f gramps --yes > data/caledonia.gramps

python3 "$ROOT/scripts/export_from_gramps.py" \
  --gramps "$ROOT/data/caledonia.gramps" \
  --outdir "$OUTDIR/data" \
  --places origins \
  --associations "$ROOT/data/associations.csv"

# 3) Build families aggregate + crosswalk

# deps for the families builder (PyYAML only)
python3 scripts/build_families.py

# 4) Export parcels for the web
SRC_GPKG="$ROOT/data/qgis/parcels-1874.gpkg"
LAYER="parcels-1874-vectors"
OUT="$OUTDIR/data/parcels-1874.geojson"

if [ -f "$SRC_GPKG" ]; then
  echo "Exporting $LAYER → $OUT"
  ogr2ogr -f GeoJSON \
    -t_srs EPSG:4326 \
    -select parcel_id,plss_desc \
    "$OUT" "$SRC_GPKG" "$LAYER"
else
  echo "WARN: $SRC_GPKG not found; skipping parcel export"
fi

# 4) Copy app
rsync -a "$ROOT/app/" "$OUTDIR/"

# 4) Copy tiles (if you keep them local)
if [ -d "$ROOT/app/tiles" ]; then
  mkdir -p "$OUTDIR/tiles"
  rsync -a "$ROOT/app/tiles/" "$OUTDIR/tiles/"
fi

echo "Built to $OUTDIR/"
