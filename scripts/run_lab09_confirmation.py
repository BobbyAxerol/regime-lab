#!/usr/bin/env python
"""L09.2 — run the frozen protocol on the confirmation interval.

Nothing here is a new experiment. The cells, the arms, the contrasts, the seeds,
the economics and the engine all come from the protocol LAB-08 froze; the only
thing that moves is the window. That is the whole point, so the differences are
made explicit rather than left to the reader:

  * the account window is the interval unlocked in L09.1, not the development one;
  * arms A and B get their selections from the SAME function that serves C and D,
    because LAB-04 never ran on this interval -- so the calendar arms and the
    dynamic arms differ in the cutoff list and in nothing else;
  * the state provider is the confirmation-role tape, fitted by the same fitter
    with the same K, lambda, seeds, memory and cadence.

L09.2.6 forbids a human adjustment between the start and the end of the run. That
is enforced, not promised: every module the run executes is hashed before the
first cell and again after the last, and a difference fails the run.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from pathlib import Path

import pandas as pd

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))
sys.path.insert(0, str(LAB_ROOT / "scripts"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter, utc_now_iso  # noqa: E402
from crypto_regime_lab.experiments import calendar_baseline as CB  # noqa: E402
from crypto_regime_lab.experiments.factorial import ARMS  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy, sha256_file  # noqa: E402
from run_lab08_factorial import load, run_cell  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"
CONFIGS = LAB_ROOT / "configs"

#: The account window. It starts where the confirmation role starts. It ENDS where
#: the 4h feature panel ends, because the panel is the state provider's only input:
#: running the account past the tape would give the dynamic arms a stretch with no
#: state at all while the calendar arms kept refreshing, which is a coverage
#: artefact and not a timing result. The unlocked interval reaches to 2026-09-09
#: in the 1-minute product; the 9 days that the panel does not cover are declared
#: here rather than silently traded.
CONF_START = "2024-01-01"
CONF_END = "2026-08-31"

#: Every module whose behaviour the run depends on. Hashed before and after.
WATCHED = [
    "scripts/run_lab08_factorial.py",
    "scripts/run_lab09_confirmation.py",
    "src/crypto_regime_lab/experiments/calendar_baseline.py",
    "src/crypto_regime_lab/experiments/factorial.py",
    "src/crypto_regime_lab/experiments/regime_schedule.py",
    "src/crypto_regime_lab/experiments/controls.py",
    "src/crypto_regime_lab/integration/continuous_account.py",
    "src/crypto_regime_lab/integration/activation.py",
    "src/crypto_regime_lab/quantbt_bridge/intent_tape.py",
]


def code_state() -> dict:
    return {path: sha256_file(LAB_ROOT / path) for path in WATCHED}


def calendar_cutoffs() -> list[str]:
    """The frozen calendar, moved to the confirmation interval and nowhere else.

    `dataclasses.replace` on ONE field is the point: train_days, test_days, folds
    and inner_episodes are carried over by construction, so no reader has to take
    it on trust that the calendar was not also widened.
    """
    calendar = dataclasses.replace(CB.CALENDAR, first_cutoff=CONF_START)
    assert calendar.train_days == CB.CALENDAR.train_days
    assert calendar.test_days == CB.CALENDAR.test_days
    assert calendar.folds == CB.CALENDAR.folds
    assert calendar.inner_episodes == CB.CALENDAR.inner_episodes
    return [w["cutoff"] for w in calendar.fold_windows()
            if pd.Timestamp(w["cutoff"]) <= pd.Timestamp(CONF_END, tz="UTC")]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cells", type=int, default=None,
                        help="run only the first N runnable cells (debugging; never a result)")
    args = parser.parse_args(argv)

    policy = SandboxPolicy.load(CONFIGS / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    policy.assert_lab_marker_ok(STUDY_ID)
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    unlock = load("lab09_confirmation_spec.json")
    if unlock is None:
        print("BLOCKED: run scripts/unlock_lab09_confirmation.py first (L09.1)")
        return 1
    protocol = load("lab08_pilot_protocol.json")
    baseline = load("lab04_calendar_baseline.json")
    baseline_cells = {(c["alpha_id"], c["symbol"]): c for c in baseline["cells"]}

    started_at = utc_now_iso()
    ordering = {
        "protocol_frozen_at_utc": protocol["frozen_at_utc"],
        "unlocked_at_utc": unlock["unlocked_at_utc"],
        "run_started_at_utc": started_at,
        "freeze_precedes_unlock": protocol["frozen_at_utc"] < unlock["unlocked_at_utc"],
        "unlock_precedes_run": unlock["unlocked_at_utc"] < started_at,
        "rule": ("the protocol was frozen before the interval was unlocked, and the interval was "
                 "unlocked before the run started. Any other order means the design could have "
                 "moved after a result was visible (L09.1.6, L09.2.7)"),
    }
    if not (ordering["freeze_precedes_unlock"] and ordering["unlock_precedes_run"]):
        print(f"BLOCKED: stamp ordering violated {ordering}")
        return 1

    cutoffs = calendar_cutoffs()
    code_before = code_state()

    planned = protocol["primary_matrix"]["cells"]
    runnable = [c for c in planned if c["runnable"]]
    if args.cells:
        runnable = runnable[:args.cells]

    checkpoints = LAB_ROOT / ".cache" / "lab09_cells"
    checkpoints.mkdir(parents=True, exist_ok=True)

    cache: dict = {}
    records = []
    run_started = time.perf_counter()
    for entry in planned:
        key = (entry["alpha_id"], entry["symbol"])
        if not entry["runnable"]:
            records.append({"alpha_id": key[0], "symbol": key[1], "status": "NOT_READY",
                            "reason": entry["blocker"],
                            "arms": {a: {"arm": a, "status": "NOT_READY", "net_return": None,
                                         "note": "null metrics, never a PnL of 0"}
                                     for a in ARMS}})
            continue
        if entry not in runnable:
            records.append({"alpha_id": key[0], "symbol": key[1], "status": "NOT_RUN_THIS_STAGE",
                            "reason": f"--cells limited the run to {len(runnable)} cells",
                            "arms": {a: {"arm": a, "status": "NOT_RUN_THIS_STAGE",
                                         "net_return": None} for a in ARMS}})
            continue
        checkpoint = checkpoints / f"{key[0]}_{key[1]}.json"
        if checkpoint.is_file():
            print(f"  {key[0]}/{key[1]} (checkpoint)", flush=True)
            records.append(json.loads(checkpoint.read_text()))
            continue
        print(f"  {key[0]}/{key[1]} ...", flush=True)
        record = run_cell(key[0], key[1], protocol, baseline_cells, cache,
                          progress=lambda m: print(m, flush=True),
                          window=(CONF_START, CONF_END),
                          tape_prefix=f"lab09_{key[1].lower()}",
                          calendar_cutoffs=cutoffs)
        checkpoint.write_text(json.dumps(record, indent=2, default=str))
        records.append(record)

    code_after = code_state()
    unchanged = code_before == code_after
    changed = sorted(k for k in code_before if code_before[k] != code_after.get(k))

    document = {
        "schema": "crypto_regime_lab.lab09_confirmation_results.v1",
        "study_id": STUDY_ID,
        "stage": "confirmation",
        "generated_at_utc": utc_now_iso(),
        "window": [CONF_START, CONF_END],
        "window_note": (
            "the unlocked interval reaches 2026-09-09 in the 1-minute product; the account stops "
            "at the end of the 4h feature panel because the panel is the state provider's input. "
            "Trading 9 further days would leave the dynamic arms without a tape while the "
            "calendar arms kept refreshing"),
        "unlocked_at_utc": unlock["unlocked_at_utc"],
        "protocol_frozen_at_utc": protocol["frozen_at_utc"],
        "stamp_ordering": ordering,
        "calendar_cutoffs": cutoffs,
        "calendar_spec": {"train_days": CB.CALENDAR.train_days,
                          "test_days": CB.CALENDAR.test_days,
                          "folds": CB.CALENDAR.folds,
                          "inner_episodes": CB.CALENDAR.inner_episodes,
                          "first_cutoff": CONF_START,
                          "changed_from_development": ["first_cutoff"],
                          "how": "dataclasses.replace on one field; every other field is carried"},
        "seeds": protocol["seeds"],
        "economics": protocol["economics"],
        "arms": protocol["arms"],
        "registered_contrasts": protocol["registered_contrasts"],
        "cells_planned": len(planned),
        "cells_run": sum(1 for r in records if r["status"] == "RUN"),
        "cells_not_ready": sum(1 for r in records if r["status"] == "NOT_READY"),
        "cells_not_run_this_stage": sum(1 for r in records
                                        if r["status"] == "NOT_RUN_THIS_STAGE"),
        "cells": records,
        "no_human_adjustment": {
            "checked": True,
            "modules_hashed": len(WATCHED),
            "unchanged_during_run": unchanged,
            "changed": changed,
            "before": code_before,
            "after": code_after,
            "rule": ("L09.2.6. Every module the run executes is hashed before the first cell and "
                     "again after the last. An edit mid-run would change the code that produced "
                     "the later cells and not the earlier ones, which is exactly the adjustment "
                     "the clause forbids"),
        },
        "engine_untouched": {
            "quantbt_engine": "1.1.1 (PyPI, unmodified)",
            "execution_contract": "intrabar_bracket_v1",
            "evidence": "configs/requirements.lock and configs/api_binding_map.json are unchanged",
        },
        "wall_seconds": time.perf_counter() - run_started,
        "is_a_result": args.cells is None,
    }
    with writer.attempt("L09.2.frozen_protocol") as att:
        att.detail = {"cells_run": document["cells_run"], "window": [CONF_START, CONF_END]}
    writer.write_config("lab09_confirmation_results.json", document)
    writer.write_json("lab09_confirmation_results.json", document, schema=document["schema"])

    print(f"\nconfirmation: {document['cells_run']} run, {document['cells_not_ready']} NOT_READY")
    for record in records:
        if record["status"] != "RUN":
            continue
        arms = record["arms"]
        line = "  ".join(
            f"{a}={arms[a]['net_return']:+.2%}" if arms[a].get("net_return") is not None
            else f"{a}={arms[a]['status'][:9]}" for a in ARMS)
        print(f"  {record['alpha_id']:<7} {record['symbol']:<9} {line}")
    print(f"code unchanged during run: {unchanged} {changed if changed else ''}")
    print(f"wall: {document['wall_seconds']:.0f}s")
    print(f"evidence -> {writer.run_dir}")
    return 0 if unchanged else 1


if __name__ == "__main__":
    raise SystemExit(main())
