#!/usr/bin/env python
"""Does the fee-binding defect change what the selector CHOSE, or only what it earned?

L09.6.1 found that the account was charged half the registered one-way taker fee.
The deployment side of that is corrected arithmetically by re-running the
accounts (`replay_lab08_development.py`, the AS_DECLARED cost level). The
SELECTION side cannot be: every candidate was scored with a net objective that
understated cost, and a selector that rescored at the registered fee might have
chosen differently.

Whether it would have is a measurement, not an argument, and it decides how
serious the defect is. So one cell is re-selected at the registered fee and the
chosen parameter set is compared at every cutoff. The trial points themselves are
unchanged -- the sampler seed is fixed -- so any difference is the objective
moving a ranking, which is exactly the mechanism in question.

One cell, because the point is the MECHANISM. If the selections are identical
here the defect is an accounting one; if they differ, it is a design one, and the
report says so either way.
"""

from __future__ import annotations

import sys
import time
import warnings
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))
sys.path.insert(0, str(LAB_ROOT / "scripts"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter, utc_now_iso  # noqa: E402
from crypto_regime_lab.experiments import calendar_baseline as CB  # noqa: E402
from crypto_regime_lab.experiments.evaluator import ACCOUNT  # noqa: E402
from crypto_regime_lab.experiments.stress import scaled_costs  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402
from run_lab08_factorial import bars_for, load  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"
CONFIGS = LAB_ROOT / "configs"
#: the pilot cell. Its first cutoff's incumbents are the registered seed points,
#: so the chain reconstructs exactly.
CELL = ("A-SC", "BTCUSDT")
DEV_START, DEV_END = "2021-01-01", "2023-12-31"


def main() -> int:
    policy = SandboxPolicy.load(CONFIGS / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    alpha_id, symbol = CELL
    baseline = load("lab04_calendar_baseline.json")
    committed = next(c for c in baseline["cells"]
                     if (c["alpha_id"], c["symbol"]) == CELL)
    protocol = load("lab08_pilot_protocol.json")
    bars = bars_for(alpha_id, symbol, protocol, {}, include_training_history=True,
                    window=(DEV_START, DEV_END))

    incumbents = {arm: dict(CB.SEED_POINTS[alpha_id]) for arm in CB.ARMS}
    rows = []
    started = time.perf_counter()
    for fold in committed["folds"]:
        if fold.get("status") != "OK":
            continue
        cutoff = fold["cutoff"]
        train = bars[(bars.index >= fold["train_start"]) & (bars.index < cutoff)]
        print(f"  cutoff {cutoff[:10]} train={len(train)} ...", flush=True)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with scaled_costs(1.0, fee_multiplier=2.0, slippage_multiplier=1.0):
                record = CB.run_cutoff(alpha_id, symbol, train, fold["fold"], incumbents,
                                       budget=CB.BUDGET, calendar=CB.CALENDAR,
                                       backend="reference")
        row = {"cutoff": cutoff[:10], "arms": {}}
        for arm in CB.ARMS:
            was = (fold["cutoff_evidence"] or {})[f"arm_{arm}"]
            now = record[f"arm_{arm}"]
            params_now = now.get("params") or incumbents[arm]
            incumbents[arm] = dict(params_now)
            row["arms"][arm] = {
                "committed_point_id": was.get("point_id"),
                "registered_fee_point_id": now.get("point_id"),
                "same_point": was.get("point_id") == now.get("point_id"),
                "committed_status": was.get("status"),
                "registered_fee_status": now.get("status"),
                "committed_params": was.get("params"),
                "registered_fee_params": now.get("params"),
                "same_params": was.get("params") == now.get("params"),
            }
        rows.append(row)

    comparisons = [entry for row in rows for entry in row["arms"].values()]
    same_point = sum(1 for c in comparisons if c["same_point"])
    same_params = sum(1 for c in comparisons if c["same_params"])
    document = {
        "schema": "crypto_regime_lab.fee_sensitivity_probe.v1",
        "generated_at_utc": utc_now_iso(),
        "cell": {"alpha_id": alpha_id, "symbol": symbol},
        "question": ("does correcting the one-way taker fee from 0.0002 to the registered 0.0004 "
                     "change WHICH parameter set the selector chooses, or only what it earns?"),
        "economics": {"as_run_one_way_fee": ACCOUNT["taker_fee_rate"] / 2,
                      "registered_one_way_fee": ACCOUNT["taker_fee_rate"],
                      "how": ("the binding is untouched; the probe doubles ACCOUNT's rate so the "
                              "engine's round-trip halving lands on the registered one-way rate"),
                      "slippage_unchanged": True},
        "sampler_seed_unchanged": True,
        "why_seed_matters": ("the trial POINTS are identical, so a difference in the selection is "
                            "the objective moving a ranking and nothing else"),
        "cutoffs": len(rows),
        "comparisons": len(comparisons),
        "selections_identical": same_point,
        "parameter_sets_identical": same_params,
        "all_identical": same_point == len(comparisons) == same_params,
        "reading": ("identical selections mean the fee defect is an ACCOUNTING one: it changed "
                    "what the arms earned, not what they deployed. A difference at any cutoff "
                    "would make it a DESIGN one, because the candidate bank itself would depend "
                    "on the understated cost"),
        "scope": ("one cell, six cutoffs, both arms. It is evidence about the MECHANISM, not a "
                  "guarantee for the other fourteen cells"),
        "per_cutoff": rows,
        "wall_seconds": time.perf_counter() - started,
    }
    with writer.attempt("L09.6.fee_sensitivity") as att:
        att.detail = {"all_identical": document["all_identical"]}
    writer.write_config("lab09_fee_sensitivity.json", document)
    writer.write_json("lab09_fee_sensitivity.json", document, schema=document["schema"])

    print(f"\n{alpha_id}/{symbol}: {len(rows)} cutoffs, {len(comparisons)} arm-selections")
    for row in rows:
        for arm, entry in row["arms"].items():
            mark = "same" if entry["same_point"] else "DIFFERENT"
            print(f"  {row['cutoff']}  arm {arm}: {mark}  "
                  f"{entry['committed_point_id']} -> {entry['registered_fee_point_id']}")
    print(f"selections identical: {same_point}/{len(comparisons)}")
    print(f"reading: {'ACCOUNTING defect' if document['all_identical'] else 'DESIGN defect'}")
    print(f"wall: {document['wall_seconds']:.0f}s")
    print(f"evidence -> {writer.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
