#!/usr/bin/env -S bash --login
set -euo pipefail

# Build / refresh the runtime environment for the Black Marble OGC / DPS job.

basedir=$(cd "$(dirname "$(readlink -f "$0" 2>/dev/null || echo "$0")")" && pwd)

CONDA_ENV_NAME="${CONDA_ENV_NAME:-notebook}"
conda=${CONDA_EXE:-conda}

echo "Updating conda environment '${CONDA_ENV_NAME}' from environment.yml"
PIP_REQUIRE_VENV=0 "${conda}" env update --quiet --file "${basedir}/environment.yml" --name "${CONDA_ENV_NAME}"

# Prefer local checkout (upstream/) when present; otherwise install from GitHub.
if [[ -f "${basedir}/upstream/pyproject.toml" ]]; then
  echo "Installing blackmarble from local upstream/"
  PIP_REQUIRE_VENV=0 "${conda}" run --name "${CONDA_ENV_NAME}" \
    python -m pip install --no-cache-dir -e "${basedir}/upstream"
else
  echo "Installing blackmarble from GitHub (NASA-IMPACT/veda-black-marble)"
  PIP_REQUIRE_VENV=0 "${conda}" run --name "${CONDA_ENV_NAME}" \
    python -m pip install --no-cache-dir \
    "git+https://github.com/NASA-IMPACT/veda-black-marble.git@main"
fi

echo "Verifying blackmarble CLI"
"${conda}" run --name "${CONDA_ENV_NAME}" blackmarble --help >/dev/null
echo "Build complete"
