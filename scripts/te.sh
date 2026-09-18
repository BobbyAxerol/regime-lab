#!/usr/bin/env bash
set -euo pipefail
TE_LAB_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd -- "$TE_LAB_ROOT"
export PYTHONDONTWRITEBYTECODE=1
export NUMBA_CACHE_DIR="$TE_LAB_ROOT/.cache/numba"
export MPLCONFIGDIR="$TE_LAB_ROOT/.cache/matplotlib"
export TMPDIR="$TE_LAB_ROOT/.cache/tmp"
exec "$TE_LAB_ROOT/environments/lab_venv/bin/python" -B "$TE_LAB_ROOT/scripts/run_time_edge.py" "$@"
