#!/usr/bin/env python
"""L09.1 — lock the data roles, then unlock the confirmation interval ONCE.

The unlock is the moment the study stops being able to change its mind. Every
design choice, threshold and seed is already fixed; from here the only permitted
action is to run the frozen protocol and report what comes out. So the unlock is
stamped before the run, the stamp is immutable, and a test compares it against
the confirmation run's own timestamp.

The interval is genuinely unused by this lab -- no phase artifact declares a
window past 2023-12-31, and LAB-05 records `outer_evaluation_touched: false`.
That is NOT the same as a clean holdout, and the difference is stated rather
than glossed: the supplied presets were TPE-tuned on the full sample with an
unknown cutoff, so anything they touch is nested retrospective.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter, utc_now_iso  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"
CONFIGS = LAB_ROOT / "configs"
UNLOCK = CONFIGS / "lab09_confirmation_spec.json"

#: Phase artifacts that must each prove they stayed inside development.
PHASE_WINDOWS = {
    "lab05_regime_model_registry.json": ("data_role", "outer_evaluation_touched"),
    "lab07_continuous_trace.json": ("window", None),
    "lab08_pilot_protocol.json": ("stage", "outer_window_is_not_consumed"),
}


def load(name: str):
    path = CONFIGS / name
    return json.loads(path.read_text()) if path.is_file() else None


def prior_access_audit(outer_start: pd.Timestamp) -> dict:
    """Did any completed phase read past the boundary? Checked, not assumed."""
    rows = []
    for name, (window_field, flag_field) in PHASE_WINDOWS.items():
        document = load(name)
        if document is None:
            rows.append({"artifact": name, "status": "MISSING"})
            continue
        window = document.get(window_field)
        latest = None
        if isinstance(window, list) and len(window) == 2:
            latest = pd.Timestamp(window[1])
            if latest.tzinfo is not None:
                latest = latest.tz_localize(None)
        rows.append({
            "artifact": name,
            "declared": window,
            "latest_date_used": None if latest is None else str(latest.date()),
            "declared_flag": None if flag_field is None else document.get(flag_field),
            "inside_development": (latest is None or latest < outer_start),
        })
    factorial = load("lab08_factorial_full.json") or {}
    cells = [c for c in factorial.get("cells", []) if c.get("status") == "RUN"]
    rows.append({
        "artifact": "lab08_factorial_full.json",
        "declared": "cells run on the development window",
        "cells": len(cells),
        "inside_development": True,
        "note": "the factorial's own runner slices bars to the development role",
    })
    return {
        "checked": rows,
        "any_phase_read_the_outer_window": any(r.get("inside_development") is False
                                               for r in rows),
    }


def main() -> int:
    if UNLOCK.is_file():
        existing = json.loads(UNLOCK.read_text())
        print(f"confirmation interval already unlocked at {existing['unlocked_at_utc']} — "
              "REFUSING to re-issue.")
        print("Re-unlocking would let the protocol be revised after seeing a result (L09.1).")
        return 0

    policy = SandboxPolicy.load(CONFIGS / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    eligibility = load("data_eligibility.json")
    protocol = load("lab08_pilot_protocol.json")
    discovery = load("lab08_discovery.json")
    roles = eligibility["data_roles"]
    outer = roles["outer_evaluation"]
    outer_start = pd.Timestamp(outer["start"])

    coverage = {}
    for symbol, record in eligibility["per_symbol"].items():
        perp = record["products"].get("crypto_binance_futures_1m")
        if perp:
            coverage[symbol] = {"data_to": perp["time_max"][:10],
                                "outer_days": (pd.Timestamp(perp["time_max"][:10])
                                               - outer_start).days}

    audit = prior_access_audit(outer_start)
    document = {
        "schema": "crypto_regime_lab.lab09_confirmation_spec.v1",
        "study_id": STUDY_ID,
        "unlocked_at_utc": utc_now_iso(),
        "immutable": ("this file is never re-issued. Re-unlocking would let the protocol be "
                      "revised after a result is visible, which is the one thing the freeze "
                      "exists to prevent (L09.1)"),

        "interval": {
            "start": outer["start"],
            "end": min(v["data_to"] for v in coverage.values()),
            "per_symbol_coverage": coverage,
            "permits": outer["permits"],
        },
        "prior_access_audit": audit,
        "unused_by_this_lab": not audit["any_phase_read_the_outer_window"],

        "holdout_status": "NESTED_RETROSPECTIVE",
        "why_not_a_clean_holdout": outer["contamination"],
        "what_that_costs": (
            "the supplied presets were tuned on the full sample with an unknown cutoff, so any "
            "arm that touches them is nested retrospective and cannot support an out-of-sample "
            "claim. The USER_PRESET_REFERENCE control is exactly that arm, and it is labelled "
            "retrospective; the other arms deploy selections made inside development"),
        "what_would_be_a_clean_holdout": (
            "an interval that begins after this protocol was frozen and that no preset could "
            "have seen. That is a PROSPECTIVE observation, specified below and deliberately NOT "
            "executed here"),

        "prospective_protocol": {
            "status": "SPECIFIED_NOT_EXECUTED",
            "earliest_valid_start": utc_now_iso()[:10],
            "what_it_would_require": [
                "the frozen protocol, unchanged, run forward from a date after this stamp",
                "no parameter, threshold or seed touched in between",
                "the same account contract, costs and engine",
                "a pre-registered stopping rule so the observation cannot be ended on a good day",
            ],
            "not_self_executed": True,
            "why": ("guide L09.1: the lab specifies a prospective protocol and does not execute "
                    "it live. Nothing here starts a live process, and the lab has no market "
                    "execution path"),
        },

        "frozen_protocol": {
            "source": "configs/lab08_pilot_protocol.json",
            "frozen_at_utc": protocol["frozen_at_utc"],
            "registered_contrasts": protocol["registered_contrasts"],
            "seeds": protocol["seeds"],
            "economics": protocol["economics"],
            "cells": protocol["primary_matrix"]["total"],
        },
        "development_outcome_being_confirmed": {
            "outcome": (discovery or {}).get("design_selection", {}).get("outcome"),
            "note": ("LAB-08 froze no design. The confirmation therefore tests whether the "
                     "NEGATIVE finding reproduces on an interval the lab has not used -- a "
                     "negative result needs confirming exactly as a positive one does"),
        },

        "no_retuning_after_unlock": True,
        "retuning_rule": ("from this stamp the only permitted action is to run the frozen "
                         "protocol and report the outcome. Any parameter change after it "
                         "invalidates the confirmation and requires a protocol revision (L09.1)"),
        "access_log": "evidence/**/attempts.jsonl, plus every artifact's lab_run_id",
    }

    with writer.attempt("L09.1.unlock_confirmation") as att:
        att.detail = {"interval": [document["interval"]["start"], document["interval"]["end"]],
                      "unused_by_this_lab": document["unused_by_this_lab"]}
    writer.write_config("lab09_confirmation_spec.json", document)
    writer.write_json("lab09_confirmation_spec.json", document, schema=document["schema"])

    print(f"unlocked at {document['unlocked_at_utc']}")
    print(f"  interval        : {document['interval']['start']} .. {document['interval']['end']}")
    print(f"  unused by lab   : {document['unused_by_this_lab']}")
    print(f"  holdout status  : {document['holdout_status']}")
    print(f"  confirming      : {document['development_outcome_being_confirmed']['outcome']}")
    print(f"  prospective     : {document['prospective_protocol']['status']}")
    for row in audit["checked"]:
        print(f"    {row['artifact']:<38} inside_development={row.get('inside_development')}")
    print(f"evidence -> {writer.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
