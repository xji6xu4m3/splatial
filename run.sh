#!/usr/bin/env bash
# Run the Splatial server WITHOUT Docker.
#
# This is the SAME server the container runs (capture + viewer + reconstruct on one port),
# just launched directly. It only works on a machine that already has the heavy bits set up:
#   - a Python interpreter with torch (CUDA) + the AnySplat deps  (the `anysplat` conda env here)
#   - the built web viewer (web/dist/)  — this script builds it on first run
#   - the AnySplat weights (downloaded on first reconstruction, or pre-cached)
# On a fresh machine, installing those is exactly what the Docker image automates — prefer Docker
# there (see README "Run on your phone (Docker)"). This script is the one-command path once the
# environment exists.
#
# Usage:   ./run.sh                 # serves on :8080, prints a phone URL + QR
#          PORT=9000 ./run.sh       # different port
#          SPLATIAL_PY=/path/python ./run.sh   # choose the torch-enabled interpreter
set -euo pipefail
cd "$(dirname "$0")"

# Pick a Python that has torch. Default to the project's anysplat conda env; override with SPLATIAL_PY.
PY="${SPLATIAL_PY:-$HOME/anaconda3/envs/anysplat/bin/python}"
[ -x "$PY" ] || PY="$(command -v python3)"

if ! "$PY" -c "import torch" >/dev/null 2>&1; then
  echo "ERROR: '$PY' has no 'torch'. Point SPLATIAL_PY at an interpreter with torch + AnySplat deps,"
  echo "       or just use Docker (README → 'Run on your phone (Docker)')." >&2
  exit 1
fi

# Build the viewer once if it isn't built.
if [ ! -f web/dist/index.html ]; then
  echo "Building the web viewer (first run)…"
  ( cd web && npm install && npm run build )
fi

echo "Starting Splatial with $PY on port ${PORT:-8080} …"
exec "$PY" -m modules.serve
