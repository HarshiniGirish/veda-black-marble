#!/usr/bin/env bash
set -euo pipefail

# OGC / DPS entrypoint. Named flags only (OGC requirement).
# Auth: MAAP_PGT injected by DPS; blackmarble/acquire/viirs.py uses maap-py.

mkdir -p output

BBOX=""
DATE=""
CONFIG="fast"
OSM_SOURCE="overpass"
WGS84="false"
BASENAME="black_marble_output"
LOG_LEVEL="INFO"

usage() {
  cat <<EOF
Usage: $(basename "$0") --bbox MINX,MINY,MAXX,MAXY --date YYYY-MM-DD [options]
  --config PRESET          default|high_quality|fast   [fast]
  --osm_source SRC         overpass|layercake          [overpass]
  --wgs84 true|false       also export EPSG:4326       [false]
  --basename NAME          → output/NAME.tif
  --log_level LEVEL        DEBUG|INFO|WARNING|ERROR    [INFO]
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bbox) BBOX="$2"; shift 2 ;;
    --date) DATE="$2"; shift 2 ;;
    --config) CONFIG="$2"; shift 2 ;;
    --osm_source) OSM_SOURCE="$2"; shift 2 ;;
    --wgs84) WGS84="$2"; shift 2 ;;
    --basename) BASENAME="$2"; shift 2 ;;
    --log_level) LOG_LEVEL="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage >&2; exit 1 ;;
  esac
done

if [[ -z "$BBOX" || -z "$DATE" ]]; then
  echo "ERROR: --bbox and --date are required" >&2
  usage >&2
  exit 1
fi

OUTPUT_PATH="output/${BASENAME}.tif"
DATA_DIR="output/data"
mkdir -p "${DATA_DIR}"

ARGS=(
  --bbox "${BBOX}"
  --date "${DATE}"
  --config "${CONFIG}"
  --osm-source "${OSM_SOURCE}"
  --output-path "${OUTPUT_PATH}"
  --data-dir "${DATA_DIR}"
  --log-level "${LOG_LEVEL}"
)
case "${WGS84}" in true|TRUE|1|yes|YES) ARGS+=(--wgs84) ;; esac

CONDA_ENV_NAME="${CONDA_ENV_NAME:-notebook}"
if ! command -v conda >/dev/null 2>&1; then
  for candidate in /opt/conda/etc/profile.d/conda.sh /srv/conda/etc/profile.d/conda.sh; do
    [[ -f "$candidate" ]] && source "$candidate" && break
  done
fi

echo "Running Black Marble: bbox=${BBOX} date=${DATE} output=${OUTPUT_PATH}"
conda run --live-stream --name "${CONDA_ENV_NAME}" blackmarble "${ARGS[@]}"
ls -la output || true
