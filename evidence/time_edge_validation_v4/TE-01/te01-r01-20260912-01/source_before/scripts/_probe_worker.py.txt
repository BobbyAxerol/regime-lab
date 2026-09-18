#!/usr/bin/env python
"""Appendix B probe worker. Runs INSIDE the bubblewrap sandbox.

Reads a lab root from argv, executes the probe suite against the raw alpha
sources via the AST harness, and prints one JSON document. Never imports an
alpha module; never writes outside LAB_ROOT.
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

LAB_ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.alphas.probes import run_all_probes  # noqa: E402

try:
    payload = run_all_probes(LAB_ROOT)
    print(json.dumps(payload, default=str))
except Exception:  # a crashing probe suite must be visible, not silent
    print(json.dumps({"fatal": traceback.format_exc()}))
    raise SystemExit(1)
