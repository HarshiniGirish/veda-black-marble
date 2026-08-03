#!/usr/bin/env bash
set -euo pipefail

basedir=$(cd "$(dirname "$(readlink -f "$0" 2>/dev/null || echo "$0")")" && pwd)

CONDA_ENV_NAME="${CONDA_ENV_NAME:-notebook}"
conda=${CONDA_EXE:-conda}

# Initialize conda if needed (same as run.sh)
if ! command -v conda >/dev/null 2>&1; then
  for candidate in \
    /opt/conda/etc/profile.d/conda.sh \
    /srv/conda/etc/profile.d/conda.sh \
    /usr/local/etc/profile.d/conda.sh
  do
    if [[ -f "${candidate}" ]]; then
      # shellcheck disable=SC1090
      source "${candidate}"
      break
    fi
  done
fi

if [[ -f "${basedir}/environment.yml" ]]; then
  ENV_FILE="${basedir}/environment.yml"
elif [[ -f "${basedir}/env.yml" ]]; then
  ENV_FILE="${basedir}/env.yml"
else
  echo "ERROR: neither environment.yml nor env.yml found in ${basedir}" >&2
  exit 1
fi

echo "Updating conda environment '${CONDA_ENV_NAME}' from $(basename "${ENV_FILE}")"
PIP_REQUIRE_VENV=0 "${conda}" env update --quiet --file "${ENV_FILE}" --name "${CONDA_ENV_NAME}"

echo "Installing blackmarble from this repository"
PIP_REQUIRE_VENV=0 "${conda}" run --name "${CONDA_ENV_NAME}" \
  python -m pip install --no-cache-dir -e "${basedir}"

echo "Verifying blackmarble CLI"
"${conda}" run --name "${CONDA_ENV_NAME}" blackmarble --help >/dev/null

echo "Verifying maap-py import (for MAAP secrets)"
"${conda}" run --name "${CONDA_ENV_NAME}" python -c "from maap.maap import MAAP; print('maap-py OK')"

chmod +x "${basedir}/run.sh" "${basedir}/build.sh" 2>/dev/null || true
echo "Build complete"
