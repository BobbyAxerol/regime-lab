#!/usr/bin/env python
"""L08.1 — freeze the pilot protocol BEFORE any arm runs.

The freeze is the whole point of the task. Everything below could be chosen
after seeing which arm wins: the timeframes, the seeds, which cells count, how
compute is matched, what the primary endpoint is. Guide L08.1 puts them in an
immutable registry first, and this script refuses to overwrite an existing
freeze so a later run cannot quietly re-decide them.

Nothing here is invented. Timeframes come from the LAB-01 registration, cells
from the LAB-02 certification and the LAB-03 qualification, the endpoint and the
minimum effect from the pre-registered study, and the budget contract from the
registration made before LAB-07.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter, utc_now_iso  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"
CONFIGS = LAB_ROOT / "configs"
FREEZE = CONFIGS / "lab08_pilot_protocol.json"


def load(name: str):
    path = CONFIGS / name
    return json.loads(path.read_text()) if path.is_file() else None


def main() -> int:
    if FREEZE.is_file():
        existing = json.loads(FREEZE.read_text())
        print(f"protocol already frozen at {existing['frozen_at_utc']} — REFUSING to overwrite.")
        print("A freeze that can be rewritten after a result is not a freeze (guide L08.1).")
        return 0

    policy = SandboxPolicy.load(CONFIGS / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    registration = load("study_registration.json")
    budget = load("compute_budget_registration.json")
    effect = load("minimum_economic_effect.json")
    certification = {}
    for path in sorted((CONFIGS / "alpha_certification").glob("*.json")):
        record = json.loads(path.read_text())
        certification[record["alpha_id"]] = record

    symbols = registration["trade_symbols"]
    cells = []
    for alpha_id, record in sorted(certification.items()):
        ready = record["status"] == "READY_FOR_RESEARCH"
        for symbol in symbols:
            cells.append({
                "alpha_id": alpha_id, "symbol": symbol,
                "runnable": ready,
                "status_if_not_runnable": None if ready else "NOT_READY_SPECIFIC_BLOCKER",
                "blocker": None if ready else record.get("blocker_summary")
                           or record.get("status_reason") or "see alpha_certification",
                "decision_bars": registration["timeframes"][alpha_id]["decision_bars"],
                "execution_bars": registration["timeframes"][alpha_id]["execution_bars"],
            })

    document = {
        "schema": "crypto_regime_lab.lab08_pilot_protocol.v1",
        "study_id": STUDY_ID,
        "frozen_at_utc": utc_now_iso(),
        "frozen_before": "any LAB-08 arm run. scripts/audit_lab08.py checks the ordering.",
        "immutable": ("this file is never overwritten. Re-running the freeze script prints the "
                      "existing stamp and exits. A protocol that can be rewritten after a result "
                      "is not frozen (guide L08.1)"),

        "timeframes": registration["timeframes"],
        "evaluation_interval": "daily UTC on the continuous account (guide 10.3)",
        "seeds": {"probe_design": 20260910, "model_multi_start": [11, 23, 37, 51],
                  "placebo": 20260911,
                  "rule": "every seed is fixed here; a seed chosen later is a search decision"},

        "primary_matrix": {
            "cells": cells,
            "total": len(cells),
            "runnable": sum(1 for c in cells if c["runnable"]),
            "not_runnable": sum(1 for c in cells if not c["runnable"]),
            "reporting_rule": ("all 20 cell statuses are reported. A NOT_READY cell keeps null "
                              "metrics and stays in the denominator; it is never dropped and "
                              "never recorded as a PnL of 0 (guide 10.4)"),
        },

        "arms": {
            "A": "installed WFO selector, frozen calendar — the baseline",
            "B": "neighborhood selector, same calendar — the robustness contribution",
            "C": "installed selector, regime-triggered refresh — the timing contribution",
            "D": "neighborhood selector, regime-triggered refresh — the interaction",
            "E": "selector + bank + response policy — an EXTENSION, not a substitute for C or D",
        },
        "registered_contrasts": ["B-A", "C-A", "D-B", "D-C", "(D-C)-(B-A)"],
        "arm_e_rule": ("E is compared against B and against BANK_CALENDAR. Using E in place of C "
                       "or D without saying so is forbidden (guide 10.1)"),

        "controls": {
            "RISK_ONLY": "same regime context, risk scaling only, parameters unchanged",
            "CALENDAR_MATCHED": "calendar cadence with compute equivalent to the dynamic policy",
            "BANK_CALENDAR": "same bank size and candidate identities, calendar switching, no regime",
            "STATE_PLACEBO": "fake labels with approximately the real dwell and switch frequency, "
                             "generated from the past only",
            "DELAYED_STATE": "one registered observation of extra delay, for transition sensitivity",
            "EXPOST_DIAGNOSTIC": "hindsight labels, diagnostic only, never an eligible trade result",
            "USER_PRESET_REFERENCE": "the supplied full-sample presets, labelled retrospective",
        },
        "control_rule": ("no control is dropped because it beats the proposed method. Controls "
                         "are staged rather than run as a full Cartesian product (guide 10.2)"),

        "economics": {
            "source": "configs/study_registration.json execution block, frozen at LAB-01",
            "identical_across_arms": True,
            "rule": ("fees, slippage, funding treatment and gross exposure constraints are the "
                     "same for every arm and every control (guide 10.3)"),
        },
        "account_rule": ("each arm holds ONE continuous account in chronological order. No reset "
                         "at a fold or regime boundary, and no splicing of segments from "
                         "independent runs (guide 10.3, T56)"),

        "data_roles": registration["data_roles"],
        "stage": "discovery",
        "outer_window_is_not_consumed": True,
        "contamination": registration.get("contamination"),
        "preset_role": registration.get("source_preset_role"),

        "primary_endpoint": registration.get("primary_endpoint"),
        "minimum_economic_effect": effect,
        "conclusion_vocabulary_source": "configs/hypothesis_registry.json",

        "compute_budget": {
            "source": "configs/compute_budget_registration.json",
            "registered_at_utc": (budget or {}).get("registered_at_utc"),
            "reports": sorted((budget or {}).get("reports", {})),
            "resource_budget": registration.get("resource_budget"),
            "rule": ("no arm gets more CPU than the registered budget in order to finish before "
                     "the baseline (guide L08.6)"),
        },

        "exit_options": ["DESIGN_FROZEN", "NO_PROMISING_DESIGN"],
        "exit_rule": ("profit is not required to close discovery, and a negative result is not a "
                      "technical failure to be re-run until it wins (guide L08 exit)"),
    }

    with writer.attempt("L08.1.freeze_protocol") as att:
        att.detail = {"cells": len(cells), "runnable": document["primary_matrix"]["runnable"]}
    writer.write_config("lab08_pilot_protocol.json", document)
    writer.write_json("lab08_pilot_protocol.json", document, schema=document["schema"])

    print(f"frozen at {document['frozen_at_utc']}")
    print(f"  cells        : {document['primary_matrix']['total']} "
          f"({document['primary_matrix']['runnable']} runnable, "
          f"{document['primary_matrix']['not_runnable']} NOT_READY with null metrics)")
    print(f"  arms         : {sorted(document['arms'])}")
    print(f"  contrasts    : {document['registered_contrasts']}")
    print(f"  controls     : {len(document['controls'])}")
    print(f"  stage        : {document['stage']}, outer window not consumed")
    print(f"evidence -> {writer.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
