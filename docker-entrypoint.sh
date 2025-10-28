#!/usr/bin/env bash
set -euo pipefail

mkdir -p "${CAPTURE_DIR:-/data/uploads}" \
         "${DETECTADAS_DIR:-/data/uploads_detectadas}" \
         "${NODETECCION_DIR:-/data/uploads_nodeteccion}"

# Ensure the sqlite path directory exists
if [[ -n "${DB_PATH:-}" ]]; then
  db_dir="$(dirname "${DB_PATH}")"
  mkdir -p "${db_dir}"
fi

exec "$@"
