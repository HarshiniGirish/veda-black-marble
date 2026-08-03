#!/usr/bin/env bash
set -euo pipefail

# MAAP OGC / DPS entrypoint for VEDA Black Marble.
# Persistable products must land under ./output (DPS convention).
#
# Auth: DPS injects MAAP_PGT. blackmarble/acquire/viirs.py uses maap-py.
# Do NOT pass Earthdata tokens on the CLI (they appear in job logs).
#
# Named flags:
#   ./run.sh --bbox "-122.55,37.69,-122.32,37.81" --date 2023-06-15
#
# Positional (Register Algorithm UI / DPS):
#   ./run.sh <bbox> <date> [config] [osm_source] [wgs84] [basename]

basedir=$(cd "$(dirname "$(readlink -f "$0" 2>/dev/null || echo "$0")")" && pwd)

mkdir -p output

BBOX="-122.55,37.69,-122.32,37.81"
DATE="2023-06-15"
CONFIG="fast"
OSM_SOURCE="overpass"
WGS84="false"
BASENAME="black_marble_output"
LOG_LEVEL="INFO"

trim() {
  local s="$1"
  s="${s#"${s%%[![:space:]]*}"}"
  s="${s%"${s##*[![:space:]]}"}"
  printf '%s' "$s"
}

usage() {
  cat <<EOF
Usage:
  $(basename "$0") --bbox MINX,MINY,MAXX,MAXY --date YYYY-MM-DD [options...]
  $(basename "$0") <bbox> <date> [config] [osm_source] [wgs84] [basename]

Options:
  --bbox BBOX           WGS84 bbox: min_lon,min_lat,max_lon,max_lat
  --date YYYY-MM-DD     Target date
  --config PRESET       default | high_quality | fast  [default: fast]
  --osm_source SRC      overpass | layercake           [default: overpass]
  --wgs84 true|false    Also export EPSG:4326          [default: false]
  --basename NAME       Output stem → output/NAME.tif  (maps to --output-path)
  --log_level LEVEL     DEBUG|INFO|WARNING|ERROR       [default: INFO]
EOF
}

if [[ $# -gt 0 && "${1}" != --* ]]; then
  BBOX="${1:-$BBOX}"
  DATE="${2:-$DATE}"
  CONFIG="${3:-$CONFIG}"
  OSM_SOURCE="${4:-$OSM_SOURCE}"
  WGS84="${5:-$WGS84}"
  BASENAME="${6:-$BASENAME}"
else
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --bbox) BBOX="$2"; shift 2 ;;
      --date) DATE="$2"; shift 2 ;;
      --config) CONFIG="$2"; shift 2 ;;
      --osm_source) OSM_SOURCE="$2"; shift 2 ;;
      --wgs84) WGS84="$2"; shift 2 ;;
      --basename) BASENAME="$2"; shift 2 ;;
      --log_level) LOG_LEVEL="$2"; shift 2 ;;
      --earthdata_token|--earthdata_secret_name)
        echo "ERROR: $1 is not accepted. Auth uses MAAP_PGT via maap-py inside the algorithm." >&2
        exit 2
        ;;
      -h|--help) usage; exit 0 ;;
      *)
        echo "Unknown argument: $1" >&2
        usage >&2
        exit 1
        ;;
    esac
  done
fi

BBOX="$(trim "$BBOX")"
DATE="$(trim "$DATE")"
CONFIG="$(trim "$CONFIG")"
OSM_SOURCE="$(trim "$OSM_SOURCE")"
WGS84="$(trim "$WGS84")"
BASENAME="$(trim "$BASENAME")"
LOG_LEVEL="$(trim "$LOG_LEVEL")"

if [[ -z "${BBOX}" || -z "${DATE}" ]]; then
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

case "${WGS84}" in
  true|TRUE|1|yes|YES) ARGS+=(--wgs84) ;;
esac

CONDA_ENV_NAME="${CONDA_ENV_NAME:-notebook}"

if ! command -v conda >/dev/null 2>&1; then
  for candidate in \
    "${CONDA_EXE:-}" \
    /opt/conda/etc/profile.d/conda.sh \
    /opt/conda/bin/conda \
    /usr/local/etc/profile.d/conda.sh \
    "${HOME}/.conda/etc/profile.d/conda.sh" \
    /srv/conda/etc/profile.d/conda.sh \
    /srv/conda/bin/conda
  do
    [[ -z "${candidate}" ]] && continue
    if [[ -f "${candidate}" && "${candidate}" == *.sh ]]; then
      # shellcheck disable=SC1090
      source "${candidate}"
      break
    elif [[ -x "${candidate}" ]]; then
      export PATH="$(dirname "${candidate}"):${PATH}"
      break
    fi
  done
fi

if ! command -v conda >/dev/null 2>&1; then
  echo "ERROR: conda not found in PATH." >&2
  exit 127
fi

echo "Running Black Marble pipeline"
echo "  bbox=${BBOX}"
echo "  date=${DATE}"
echo "  config=${CONFIG}"
echo "  osm_source=${OSM_SOURCE}"
echo "  output=${OUTPUT_PATH}"
echo "  conda=$(command -v conda) env=${CONDA_ENV_NAME}"

conda run --live-stream --name "${CONDA_ENV_NAME}" \
  blackmarble "${ARGS[@]}"

echo "Done. Products in ./output"
ls -la output || true
