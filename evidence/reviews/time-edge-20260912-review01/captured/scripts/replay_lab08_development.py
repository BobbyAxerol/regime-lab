#!/usr/bin/env python
"""Replay LAB-08's development accounts, for two reasons at once.

L09.6.5 asks whether a selected run replays to the same result. L09.3.8 asks for
a block length chosen on DEVELOPMENT and applied unchanged to the confirmation
interval. A third question arrived with the cost-binding defect that L09.6.1
found: does LAB-08's conclusion survive the fee the study actually registered?
All three need the same thing -- the development accounts re-run by today's code
from the selections LAB-08 recorded.

The replay is cheap because it skips the expensive half. Selection is not
repeated -- the recorded choices are redeployed -- so what is being tested is the
account, the engine and the execution contract, which is exactly what a
confirmation depends on. A difference in net return here would mean the code that
produced the committed LAB-08 numbers and the code running now are not the same
code, and nothing downstream could be trusted.

No daily series survived LAB-08 (it stored contrast summaries), so this is also
the only way to get one without re-running the selector for three hours.

The AS_DECLARED pass re-runs the same accounts with the fee the study registered
-- one-way 0.0004, which the engine only charges when it is handed 0.0008,
because its `fee` parameter is documented as round-trip. What it CANNOT correct
is the selection: every candidate was scored under the halved fee, and rescoring
them is the three-hour run this replay exists to avoid. So the pass bounds the
damage to a fixed schedule and says so.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))
sys.path.insert(0, str(LAB_ROOT / "scripts"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter, utc_now_iso  # noqa: E402
from crypto_regime_lab.experiments import calendar_baseline as CB  # noqa: E402
from crypto_regime_lab.experiments.factorial import (ARMS, paired_daily_difference,  # noqa: E402
                                                     run_arm)
from crypto_regime_lab.experiments.stress import scaled_costs  # noqa: E402
from crypto_regime_lab.experiments.uncertainty import choose_block_length  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402
from run_lab08_factorial import DEV_END, DEV_START, bars_for, calendar_selections  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"
CONFIGS = LAB_ROOT / "configs"
#: net return must match to this tolerance. It is exact arithmetic on the same
#: inputs, so the tolerance is for float formatting in JSON and nothing else.
REPLAY_TOLERANCE = 1e-12


def load(name: str):
    path = CONFIGS / name
    return json.loads(path.read_text()) if path.is_file() else None


def dynamic_selections(evidence: list[dict], alpha_id: str, which: str) -> list[dict]:
    """Replay the retention chain LAB-08's runner walked at the regime cutoffs.

    Mirrors `selections_at_cutoffs` exactly: a cutoff that selected nothing keeps
    the incumbent, and the incumbent starts at the registered seed point.
    """
    incumbent = dict(CB.SEED_POINTS[alpha_id])
    out = []
    for entry in evidence:
        if entry.get("status") != "OK":
            continue
        selection = entry["cutoff_evidence"][f"arm_{which}"]
        params = selection.get("params") or incumbent
        incumbent = dict(params)
        out.append({"cutoff": entry["cutoff"], "params": dict(params),
                    "point_id": selection.get("point_id"),
                    "retained": selection.get("params") is None,
                    "source": "regime_triggered"})
    return out


def _as_result(series: dict, arm: str, alpha_id: str, symbol: str):
    """Wrap an already-computed daily series so the shared contrast code can read it."""
    from crypto_regime_lab.experiments.factorial import ArmResult

    holder = ArmResult(arm, alpha_id, symbol, "RUN")
    holder.daily_returns = lambda _s=series[arm]: _s      # noqa: E731
    return holder


def _pool_declared(per_cell: dict) -> dict:
    """Mean of each registered contrast over the cells, under the declared fee."""
    out = {}
    for name in ("B-A", "C-A", "D-B", "D-C"):
        values = [record["contrasts"][name]["mean_daily_difference"]
                  for record in per_cell.values()
                  if name in record["contrasts"]
                  and record["contrasts"][name].get("mean_daily_difference") is not None]
        out[name] = {"cells": len(values),
                     "mean_daily_difference": float(np.mean(values)) if values else None}
    if out["D-C"]["mean_daily_difference"] is not None \
            and out["B-A"]["mean_daily_difference"] is not None:
        out["(D-C)-(B-A)"] = {
            "cells": min(out["D-C"]["cells"], out["B-A"]["cells"]),
            "mean_daily_difference": (out["D-C"]["mean_daily_difference"]
                                      - out["B-A"]["mean_daily_difference"])}
    return out


def main() -> int:
    policy = SandboxPolicy.load(CONFIGS / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    factorial = load("lab08_factorial_full.json")
    if factorial is None:
        print("BLOCKED: configs/lab08_factorial_full.json is missing")
        return 1
    protocol = load("lab08_pilot_protocol.json")
    baseline = load("lab04_calendar_baseline.json")
    baseline_cells = {(c["alpha_id"], c["symbol"]): c for c in baseline["cells"]}

    cache: dict = {}
    rows, mismatches = [], []
    daily_by_cell: dict[str, dict] = {}
    declared_results: dict[str, dict] = {}
    started = time.perf_counter()

    for cell in factorial["cells"]:
        if cell["status"] != "RUN":
            continue
        alpha_id, symbol = cell["alpha_id"], cell["symbol"]
        print(f"  {alpha_id}/{symbol} ...", flush=True)
        bars = bars_for(alpha_id, symbol, protocol, cache, window=(DEV_START, DEV_END))
        source = baseline_cells[(alpha_id, symbol)]
        regime_evidence = (cell.get("notes") or {}).get("regime_cutoff_evidence") or []
        selections = {
            "A": calendar_selections(source, "arm_A"),
            "B": calendar_selections(source, "arm_B"),
            "C": dynamic_selections(regime_evidence, alpha_id, "A"),
            "D": dynamic_selections(regime_evidence, alpha_id, "B"),
            "E": dynamic_selections(regime_evidence, alpha_id, "B"),
        }
        series: dict[str, pd.Series] = {}
        declared: dict[str, pd.Series] = {}
        for arm in ARMS:
            recorded = (cell.get("arms") or {}).get(arm) or {}
            if recorded.get("status") != "RUN" or not selections[arm]:
                rows.append({"alpha_id": alpha_id, "symbol": symbol, "arm": arm,
                             "status": recorded.get("status", "MISSING"), "replayed": False})
                continue
            result = run_arm(arm, alpha_id, symbol, bars, selections[arm])
            record = result.as_record()
            gap = record["net_return"] - recorded["net_return"]
            matched = abs(gap) <= REPLAY_TOLERANCE
            rows.append({"alpha_id": alpha_id, "symbol": symbol, "arm": arm, "status": "RUN",
                         "replayed": True,
                         "recorded_net_return": recorded["net_return"],
                         "replayed_net_return": record["net_return"],
                         "difference": gap, "matches": bool(matched),
                         "recorded_trades": recorded.get("trades"),
                         "replayed_trades": record["trades"],
                         "trades_match": recorded.get("trades") == record["trades"]})
            if not matched:
                mismatches.append(f"{alpha_id}/{symbol}/{arm}: {gap:+.3e}")
            series[arm] = result.daily_returns()
            # the same deployment under the fee the study registered
            with scaled_costs(1.0, fee_multiplier=2.0, slippage_multiplier=1.0):
                corrected = run_arm(arm, alpha_id, symbol, bars, selections[arm])
            declared[arm] = corrected.daily_returns()
            rows[-1]["as_declared_net_return"] = corrected.as_record()["net_return"]
            rows[-1]["cost_of_the_binding_defect"] = (
                corrected.as_record()["net_return"] - record["net_return"])
        if declared:
            declared_results[f"{alpha_id}/{symbol}"] = {
                "contrasts": {f"{left}-{right}": paired_daily_difference(
                    _as_result(declared, left, alpha_id, symbol),
                    _as_result(declared, right, alpha_id, symbol))
                    for left, right in (("B", "A"), ("C", "A"), ("D", "B"), ("D", "C"))
                    if left in declared and right in declared},
                "net_return": {arm: float(s.add(1).prod() - 1) for arm, s in declared.items()},
            }
        if series:
            axis = sorted(set().union(*(set(s.index) for s in series.values())))
            daily_by_cell[f"{alpha_id}/{symbol}"] = {
                "dates": [str(t.date()) for t in axis],
                "by_arm": {arm: [None if pd.isna(v) else float(v)
                                 for v in s.reindex(axis).to_numpy()]
                           for arm, s in series.items()}}

    # ---- the block length, chosen HERE and applied to the confirmation interval
    pooled = []
    for payload in daily_by_cell.values():
        left = payload["by_arm"].get("D")
        right = payload["by_arm"].get("B")
        if not left or not right:
            continue
        pooled.extend([a - b for a, b in zip(left, right)
                       if a is not None and b is not None])
    block = choose_block_length(np.asarray(pooled, dtype=float)) if len(pooled) >= 20 else None

    document = {
        "schema": "crypto_regime_lab.lab09_development_replay.v1",
        "generated_at_utc": utc_now_iso(),
        "window": [DEV_START, DEV_END],
        "purpose": ("L09.6.5 replay verification and L09.3.8 block-length calibration, from one "
                    "pass over the development accounts"),
        "what_is_replayed": ("the account, engine and execution contract, from the selections "
                             "LAB-08 recorded. Selection itself is NOT repeated, so a difference "
                             "here is a difference in the deterministic half"),
        "tolerance": REPLAY_TOLERANCE,
        "arms_replayed": sum(1 for r in rows if r.get("replayed")),
        "arms_matching": sum(1 for r in rows if r.get("matches")),
        "mismatches": mismatches,
        "replay_is_exact": not mismatches,
        "per_arm": rows,
        "block_length_calibration": {
            **(block or {"block_length": None, "status": "NOT_COMPUTABLE"}),
            "series": "the D-B paired daily difference pooled over every development cell",
            "why_this_series": ("the block has to carry the dependence of the quantity being "
                                "bootstrapped, which is a paired DIFFERENCE between two arms on "
                                "the same days -- not a raw return series"),
            "applied_to": "the confirmation interval, unchanged (L09.3.8)",
        },
        "as_declared_economics": {
            "what_changed": ("the one-way taker fee, from the 0.0002 the engine was charging to "
                             "the 0.0004 the study registered. Slippage is untouched: it was "
                             "measured correct at 1 bp per side"),
            "measured_in": "configs/cost_binding_verification.json",
            "what_it_cannot_correct": ("selection. Every candidate in LAB-04 and LAB-08 was "
                                       "scored under the halved fee, and rescoring them means "
                                       "re-running the search. This pass therefore bounds the "
                                       "damage to a FIXED schedule"),
            "per_cell": declared_results,
            "pooled_contrasts": _pool_declared(declared_results),
        },
        "daily_returns_by_cell": daily_by_cell,
        "wall_seconds": time.perf_counter() - started,
    }
    with writer.attempt("L09.6.replay_development") as att:
        att.detail = {"arms": document["arms_replayed"], "exact": document["replay_is_exact"]}
    writer.write_config("lab09_development_replay.json", document)
    writer.write_json("lab09_development_replay.json", document, schema=document["schema"])

    print(f"\nreplayed {document['arms_replayed']} arms, "
          f"{document['arms_matching']} match to {REPLAY_TOLERANCE:g}")
    for line in mismatches:
        print(f"  MISMATCH {line}")
    pooled_declared = document["as_declared_economics"]["pooled_contrasts"]
    print("contrasts under the REGISTERED fee (mean daily difference):")
    for name, entry in pooled_declared.items():
        value = entry["mean_daily_difference"]
        print(f"  {name:<12} {value:+.3e}" if value is not None else f"  {name:<12} none")
    if block:
        print(f"block length     : {block['block_length']} days "
              f"(first lag inside +-{block['band']:.4f} band, "
              f"acf[1:5]={block['autocorrelation_lag_1_to_5']})")
    print(f"wall: {document['wall_seconds']:.0f}s")
    print(f"evidence -> {writer.run_dir}")
    return 0 if document["replay_is_exact"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
