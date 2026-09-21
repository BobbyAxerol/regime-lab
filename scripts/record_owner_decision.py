#!/usr/bin/env python3
"""Append one owner decision to the RA study's decision ledger.

R-18 (RA-GUIDE-1.0): a phase gate's own ``owner_review``/``approvals`` fields
must stay PENDING forever in that phase's frozen run directory (RA-01/RA-02
verifiers enforce exactly this — see ``ra/verifier.py``/``ra/verifier_ra02.py``).
A real approval is therefore a *separate*, append-only record, never a hand
edit of a frozen artifact. This script is that record: it never rewrites an
existing line (the ledger is append-only, one JSON object per line) and it
never fabricates the decision text — the quote is supplied verbatim by the
caller, not paraphrased.

Usage:
  lab_venv/bin/python scripts/record_owner_decision.py \\
    --decides "RA-01->RA-02" --quote "<verbatim user text>" \\
    --reference "<where this was said>" --ra01-run-id <run_id>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "src"))

from crypto_regime_lab.evidence.manifest import dumps_strict  # noqa: E402

LEDGER = LAB / "evidence" / "regime_time_edge_ra_v1" / "owner_decisions.jsonl"
SCHEMA = "regime_lab.ra_owner_decision.v1"


def utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="microseconds")


def existing_ids() -> set[str]:
    if not LEDGER.is_file():
        return set()
    ids = set()
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        if line.strip():
            ids.add(json.loads(line).get("decision_id"))
    return ids


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--decides", required=True,
                        help="what transition this approves, e.g. 'RA-01->RA-02'")
    parser.add_argument("--quote", required=True,
                        help="the owner's decision, verbatim, not paraphrased")
    parser.add_argument("--reference", required=True,
                        help="where/how this was said (session id, channel)")
    parser.add_argument("--ra01-run-id", default=None,
                        help="the RA-01 run directory this approval concerns, if any")
    parser.add_argument("--note", default=None,
                        help="agent-added context, kept separate from the quote")
    args = parser.parse_args()

    decision_id = "dec-" + hashlib.sha256(
        (args.decides + args.quote + args.reference + utcnow()).encode("utf-8")
    ).hexdigest()[:16]
    if decision_id in existing_ids():
        raise SystemExit("decision_id collision; refusing to append a duplicate")

    row = {
        "schema": SCHEMA,
        "decision_id": decision_id,
        "recorded_at_utc": utcnow(),
        "decided_by": "Bobby (owner)",
        "decides": args.decides,
        "quote": args.quote,
        "reference": args.reference,
        "ra01_run_id": args.ra01_run_id,
        "note": args.note,
    }
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with open(LEDGER, "a", encoding="utf-8") as handle:
        handle.write(dumps_strict(row, indent=None) + "\n")
        handle.flush()
        import os
        os.fsync(handle.fileno())
    print(json.dumps(row, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
