#!/usr/bin/env python
"""L08.3 — run STATE_PLACEBO and DELAYED_STATE as ARMS, not just as tapes.

Generating a placebo tape and reporting its dwell statistics controls for
nothing. The alternative explanation those two controls exist to remove is that
the dynamic arm's result comes from switching on ANY persistent signal, or that
it evaporates under a realistic observation delay -- and neither can be answered
without running a full arm on the substituted tape and comparing it to arm D.

Guide 10.2 permits a staged design rather than every control on every cell, so
these run on a declared subset. The subset is chosen by cell ORDER, before any
result is read, and is recorded here so it cannot be re-chosen afterwards.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter, utc_now_iso  # noqa: E402
from crypto_regime_lab.experiments import calendar_baseline as CB  # noqa: E402
from crypto_regime_lab.experiments.controls import (  # noqa: E402
    delayed_states,
    dwell_profile,
    placebo_fidelity,
    placebo_states,
)
from crypto_regime_lab.experiments.factorial import run_arm  # noqa: E402
from crypto_regime_lab.experiments.regime_schedule import transition_cutoffs  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402

sys.path.insert(0, str(LAB_ROOT / "scripts"))
from run_lab08_factorial import (  # noqa: E402
    DEV_END,
    DEV_START,
    bars_for,
    emissions_for,
    selections_at_cutoffs,
)

STUDY_ID = "crypto_regime_timeedge_v2"
CONFIGS = LAB_ROOT / "configs"


def load(name: str):
    path = CONFIGS / name
    return json.loads(path.read_text()) if path.is_file() else None


def substituted_tape(emissions: list[dict], *, control: str, seed: int) -> tuple[list[dict], dict]:
    """The tape this control substitutes for the real one, plus its fidelity record."""
    if control == "STATE_PLACEBO":
        states = [(e["state_namespace"], e["state_id"]) for e in emissions]
        profile = dwell_profile(states)
        fake = placebo_states(profile, length=len(states), seed=seed)
        tape = [{**e, "state_id": int(value), "state_namespace": "placebo"}
                for e, value in zip(emissions, fake)]
        return tape, placebo_fidelity(states, [t["state_id"] for t in tape])
    if control == "DELAYED_STATE":
        tape = delayed_states(emissions, observations=1)
        differing = sum(1 for a, b in zip(emissions, tape) if a["state_id"] != b["state_id"])
        return tape, {"observations_of_delay": 1, "states_that_differ": differing}
    raise ValueError(f"unknown control {control!r}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cells", type=int, default=3,
                        help="how many cells the staged control covers, taken in order")
    args = parser.parse_args(argv)

    policy = SandboxPolicy.load(CONFIGS / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    protocol = load("lab08_pilot_protocol.json")
    factorial = load("lab08_factorial_full.json")
    if factorial is None:
        print("BLOCKED: run scripts/run_lab08_factorial.py --stage full first")
        return 1

    runnable = [c for c in factorial["cells"] if c["status"] == "RUN"][:args.cells]
    cache: dict = {}
    records = []
    started = time.perf_counter()

    for cell in runnable:
        alpha_id, symbol = cell["alpha_id"], cell["symbol"]
        print(f"  {alpha_id}/{symbol} ...", flush=True)
        bars = bars_for(alpha_id, symbol, protocol, cache)
        training_bars = bars_for(alpha_id, symbol, protocol, cache,
                                 include_training_history=True)
        emissions = emissions_for(symbol)
        entry = {"alpha_id": alpha_id, "symbol": symbol, "controls": {}}

        for control, seed in (("STATE_PLACEBO", protocol["seeds"]["placebo"]),
                              ("DELAYED_STATE", 0)):
            tape, fidelity = substituted_tape(emissions, control=control, seed=seed)
            try:
                schedule = transition_cutoffs(
                    tape, count=CB.CALENDAR.folds,
                    earliest=f"{DEV_START} 00:00:00+00:00",
                    latest=f"{DEV_END} 00:00:00+00:00")
            except Exception as exc:
                entry["controls"][control] = {"status": "NO_SCHEDULE", "reason": str(exc),
                                              "fidelity": fidelity}
                continue
            print(f"    {control}: {[c[:10] for c in schedule.cutoffs]}", flush=True)
            dynamic = selections_at_cutoffs(alpha_id, symbol, training_bars,
                                            list(schedule.cutoffs))
            # the control arm mirrors arm D: the neighbourhood selector, the same
            # refresh count, the same training memory -- only the TAPE differs
            arm = run_arm("D", alpha_id, symbol, bars, dynamic["per_arm"]["B"])
            entry["controls"][control] = {
                "status": "RUN",
                "arm_mirrored": "D",
                "cutoffs": list(schedule.cutoffs),
                "fidelity": fidelity,
                **arm.as_record(),
            }
        records.append(entry)

    # compare each control arm against the real arm D on the same cell
    real_by_cell = {(c["alpha_id"], c["symbol"]): c for c in runnable}
    for entry in records:
        real = real_by_cell[(entry["alpha_id"], entry["symbol"])]["arms"]["D"]
        entry["versus_arm_D"] = {}
        for control, record in entry["controls"].items():
            if record["status"] != "RUN" or real.get("net_return") is None:
                entry["versus_arm_D"][control] = {"status": "INCOMPARABLE"}
                continue
            entry["versus_arm_D"][control] = {
                "arm_D_net_return": real["net_return"],
                "control_net_return": record["net_return"],
                "difference": record["net_return"] - real["net_return"],
                "reading": (
                    "a control arm that matches arm D means the result came from switching on "
                    "any persistent signal, not on this one" if control == "STATE_PLACEBO"
                    else "a control arm that matches arm D means the result survives a realistic "
                         "observation delay"),
            }

    document = {
        "schema": "crypto_regime_lab.lab08_control_arms.v1",
        "generated_at_utc": utc_now_iso(),
        "staged": True,
        "staging_rule": ("guide 10.2 permits a staged control design. The subset is the first "
                         f"{args.cells} runnable cells IN ORDER, chosen before any result was "
                         "read and recorded here so it cannot be re-chosen afterwards"),
        "cells": records,
        "cells_covered": len(records),
        "cells_total_runnable": sum(1 for c in factorial["cells"] if c["status"] == "RUN"),
        "why_arms_not_tapes": (
            "generating a placebo tape and reporting its dwell statistics controls for nothing. "
            "The alternative explanation is about what an ARM would have earned on that tape"),
        "wall_seconds": time.perf_counter() - started,
    }
    with writer.attempt("L08.3.control_arms") as att:
        att.detail = {"cells": len(records)}
    writer.write_config("lab08_control_arms.json", document)
    writer.write_json("lab08_control_arms.json", document, schema=document["schema"])

    print(f"\nstaged control arms over {len(records)} of "
          f"{document['cells_total_runnable']} runnable cells")
    for entry in records:
        for control, comparison in entry["versus_arm_D"].items():
            if comparison.get("status") == "INCOMPARABLE":
                print(f"  {entry['alpha_id']}/{entry['symbol']} {control}: INCOMPARABLE")
                continue
            print(f"  {entry['alpha_id']}/{entry['symbol']} {control:<15} "
                  f"D={comparison['arm_D_net_return']:+.2%}  "
                  f"control={comparison['control_net_return']:+.2%}  "
                  f"diff={comparison['difference']:+.2%}")
    print(f"wall: {document['wall_seconds']:.0f}s")
    print(f"evidence -> {writer.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
