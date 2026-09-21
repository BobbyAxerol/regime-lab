#!/usr/bin/env python3
"""FUP-05 — register the 12-month decay deep-dive + run its PLACEBO_TIMING control.

Registered follow-up study (appended to
``evidence/corrective_mode4_v3/followup-studies/followup_studies_registration.json``
as entry FUP-05, index 4). Two jobs, in order:

1. REGISTRATION (no engine call): lock the already-finished deep-dive run
   ``ra07decaydive-20260921T072850Z-22eb0631`` (10/7/9 folds, 50 trials,
   score profile) as FUP-05's discovery dataset with verdict DESCRIPTIVE_ONLY
   and every deviation from the frozen RA-05/07 contract disclosed, so the 26
   measured folds become citable evidence instead of an unregistered run.
2. PLACEBO (one real arm, host-only, background-safe): PLACEBO_TIMING on the
   SAME window/contract — a seeded synthetic state tape matching the
   development prefix's dwell profile (``ra07_controls.build_placebo_schedule``,
   the same function RA-07 used), through the SAME trigger mechanics and the
   SAME 50-trial score-profile search. Answers the open question the deep-dive
   left: is M4_REGIME's positive mean decay timing information, or cadence
   luck (RA-07's 90-day placebo matched real REGIME equity at matched
   cadence)?

Falsification contract (written before the placebo runs): if the placebo's
mean decay lands within the calendar arms' band (or matches M4_REGIME),
the REGIME signal is a cadence artifact and FUP-05 closes as such. If the
placebo decays like calendar while M4_REGIME stays positive, the signal
survives its hardest control and the recommendation is RA-08.

Nothing outside LAB_ROOT is written; no frozen artifact is edited.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy, sha256_file  # noqa: E402

STUDY_ID = "corrective_mode4_v3"
RUN_ID = "FUP-05"
REGISTRATION_PATH = (LAB_ROOT / "evidence" / STUDY_ID / "followup-studies" /
                     "followup_studies_registration.json")
DEEPDIVE_RUN_ID = "ra07decaydive-20260921T072850Z-22eb0631"
DEEPDIVE_DIR = LAB_ROOT / "evidence" / "regime_time_edge_ra_v1" / DEEPDIVE_RUN_ID
REGISTRATION_REF = ("evidence/corrective_mode4_v3/followup-studies/"
                    "followup_studies_registration.json#/studies/4")
# The deep-dive's deviations from the frozen RA-05/07 contract, disclosed not silent.
DISCLOSED_DEVIATIONS = [
    {"knob": "trials", "frozen_contract": 8, "deepdive_value": 50,
     "reason": ("user direction 2026-09-21: a 2-trial search cannot optimise; "
                "50 trials scales wall time, not peak (s2/s6 ratchet probe: flat "
                "~450 MiB transient per trial, no retention)")},
    {"knob": "M4_CAL test_days", "frozen_contract": 60, "deepdive_value": 40,
     "reason": ("user direction 2026-09-21: 100-day folds gave 4 folds, too few "
                "to read decay; measured 40-day folds give 10, balanced vs "
                "M4_REGIME's 9 real-trigger cutoffs")},
    {"knob": "engine output profile", "frozen_contract": "engine default",
     "deepdive_value": "score",
     "reason": ("FUP-04 parity: byte-equal equity, identical strategy-level "
                "counts, peak halved; the default profile OOM-killed this frame")},
    {"knob": "window", "frozen_contract": "RA-05/07 90-day pilot",
     "deepdive_value": "2021-01-01 -> 2022-01-01 (12 months)",
     "reason": ("user-requested follow-up: RA-07's 2-3 folds/arm cannot show a "
                "decay pattern; 12 months capture all 8 real regime triggers")},
]

# Falsification bar, written BEFORE the placebo exists: the calendar band from
# the deep-dive's own measured mean return-decays (M4_CAL -0.000169,
# M4_CAL_MATCHED -0.000186). A placebo inside/above this band is a cadence
# artifact verdict; clearly below it while M4_REGIME (+0.000109) stays positive
# is survival. No p-value here: n≈9 folds cannot carry one, said plainly.
CALENDAR_BAND = {"M4_CAL_mean_decay": -0.0001687721463185716,
                 "M4_CAL_MATCHED_mean_decay": -0.00018628576617384083,
                 "M4_REGIME_mean_decay": 0.00010944061223924072}


def _append_registration() -> dict:
    """Append the FUP-05 entry to the follow-up registration file (idempotent:
    re-running returns the existing entry instead of duplicating it)."""
    payload = json.loads(REGISTRATION_PATH.read_text(encoding="utf-8"))
    for index, study in enumerate(payload["studies"]):
        if study["id"] == RUN_ID:
            return {"index": index, "entry": study, "appended": False}
    entry = {
        "id": RUN_ID,
        "title": "12-month decay deep-dive registration + PLACEBO_TIMING control",
        "scope": [
            "register deep-dive ra07decaydive-20260921T072850Z-22eb0631 (10/7/9 folds, 50 trials, score profile) as FUP-05 discovery dataset, verdict DESCRIPTIVE_ONLY",
            "PLACEBO_TIMING on the same window/contract: seeded synthetic tape at the development prefix dwell profile through the same trigger mechanics and 50-trial search",
            "close with either a cadence-artifact verdict or a survived-falsification recommendation toward RA-08",
        ],
        "non_goals": [
            "any economic, market or edge claim (DESCRIPTIVE_ONLY by registration)",
            "rerunning, restating or superseding any frozen RF-05 or RA-07 number",
            "making the reduced engine profile or 50-trial budget a default for any registered phase",
        ],
        "required_inputs": [
            "snapshots/server_core_v1 (read-only) and the deep-dive's own committed artifacts",
            "ra07_controls.build_placebo_schedule (same function RA-07 used, same seed convention)",
        ],
        "exit": ("placebo measured against the pre-registered calendar band; "
                 "verdict recorded either way, recommendation toward RA-08 only on survival"),
        "budget": "T0 host-only: no charge to any shared TE ledger; ~2h engine time for one arm",
    }
    payload["studies"].append(entry)
    payload["current_blockers"][RUN_ID] = ("none at registration: host-only measurement, "
                                           "no shared compute budget, no market claim")
    REGISTRATION_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return {"index": len(payload["studies"]) - 1, "entry": entry, "appended": True}


def _discovery_dataset_record() -> dict:
    """Hash-lock the deep-dive artifacts FUP-05 cites, so the registration
    cannot drift from the run it registers."""
    files = ["decay_deepdive.json", "note.md", "attempts.jsonl",
             "scratch/M4_CAL.json", "scratch/M4_CAL_MATCHED.json",
             "scratch/M4_REGIME.json"]
    records = {}
    for rel in files:
        path = DEEPDIVE_DIR / rel
        assert path.is_file(), f"deep-dive artifact missing: {rel}"
        records[rel] = {"sha256": sha256_file(path), "bytes": path.stat().st_size}
    payload = json.loads((DEEPDIVE_DIR / "decay_deepdive.json").read_text(encoding="utf-8"))
    return {"deepdive_run_id": DEEPDIVE_RUN_ID, "files": records,
            "fold_counts": {arm: payload["arm_summaries"][arm]["meta"].get("fold_count")
                            for arm in payload["arm_summaries"]},
            "trials": payload["trials"], "window": payload["window"],
            "engine_report_level": payload["engine_report_level"],
            "verdict": "DESCRIPTIVE_ONLY"}


def run_placebo(args) -> dict:
    """One real arm: placebo schedule -> 50-trial score-profile search -> D1 rows."""
    import pandas as pd

    from crypto_regime_lab.experiments.dynamic_fold_provider import (
        ZeroSignalStrategy, engine_param_ranges, run_cutoff_walk_forward)
    from crypto_regime_lab.ra.ra05_market import (
        EMISSIONS_ARTIFACT, load_real_bars, load_real_emissions)
    from crypto_regime_lab.ra.ra07_controls import build_placebo_schedule
    from crypto_regime_lab.ra.ra07_decay import compute_d1_rows
    from crypto_regime_lab.time_edge.execution import PreparedAccount

    window_start, window_end = "2021-01-01", "2022-01-01"
    frame, partitions = load_real_bars("BTCUSDT", start="2020-11-01", end=window_end)
    frame = frame[["open", "high", "low", "close", "volume"]].copy()

    full_emissions = json.loads(EMISSIONS_ARTIFACT.read_text(encoding="utf-8"))["emissions"]
    window_emissions = load_real_emissions(window_start=window_start,
                                           window_end=window_end)["emissions"]
    built = build_placebo_schedule(
        full_emissions=full_emissions, window_emissions=window_emissions,
        window_start=window_start, window_end=window_end, train_memory_days=45,
        seed=args.placebo_seed, min_gap_days=45.0, max_age_days=180.0, budget=8)
    assert built["status"] == "OK", f"placebo schedule failed: {built['status']}"
    schedule = built["schedule"]

    started = time.perf_counter()
    run_result = run_cutoff_walk_forward(
        "A-SC", frame, schedule, param_ranges=engine_param_ranges("A-SC"),
        strategy_class=ZeroSignalStrategy, optuna_trials=50, seed=20260918,
        route="event", research_retention="none", engine_report_level="score")
    assert run_result.get("ok"), f"placebo arm failed: {run_result.get('error')}"
    run_wall = round(time.perf_counter() - started, 1)

    # D1 rows exactly the deep-dive's way: fresh small PreparedAccount per fold.
    fold_table = run_result.get("fold_selection_table") or []
    equity_daily = (run_result.get("account") or {}).get("equity_daily") or []
    window_end_fallback = fold_table[-1]["test_end"] if fold_table else None
    d1_rows = []
    evidence_dir = Path(args.evidence_dir) / "PLACEBO"
    for index, fold_row in enumerate(fold_table):
        cutoff = pd.Timestamp(fold_row["test_start"])
        sliced = frame.loc[frame.index < cutoff + pd.Timedelta(days=2)]
        prepared = PreparedAccount(sliced)
        deploy_end = (fold_table[index + 1]["test_start"] if index + 1 < len(fold_table)
                      else fold_row.get("test_end") or window_end_fallback)
        d1_rows.extend(compute_d1_rows(
            prepared=prepared, alpha_id="A-SC", symbol="BTCUSDT",
            arm="M4_REGIME_PLACEBO", fold_row=fold_row, equity_daily=equity_daily,
            deploy_end=deploy_end, evidence_dir=evidence_dir / str(index),
            lab_run_id=args.lab_run_id, regime_at_selection=None))
        del prepared
    ret = [r["signed_delta"] for r in d1_rows
           if r["metric_name"] == "mean_daily_return" and r["signed_delta"] is not None]
    shp = [r["signed_delta"] for r in d1_rows
           if r["metric_name"] == "sharpe" and r["signed_delta"] is not None]
    return {
        "schedule": {"cutoffs": list(schedule.cutoffs), "count": len(schedule.cutoffs),
                     "source": schedule.source},
        "fidelity": built["fidelity"],
        "development_states_count": built["development_states_count"],
        "window_observations_count": built["window_observations_count"],
        "fold_count": len(fold_table), "wall_seconds": run_wall,
        "equity_last": (run_result.get("account") or {}).get("equity_last"),
        "mean_daily_return_decay": {
            "n": len(ret), "mean_signed_delta": sum(ret) / len(ret) if ret else None,
            "median_signed_delta": sorted(ret)[len(ret) // 2] if ret else None,
            "per_fold_deltas": ret},
        "sharpe_decay": {
            "n": len(shp), "mean_signed_delta": sum(shp) / len(shp) if shp else None,
            "median_signed_delta": sorted(shp)[len(shp) // 2] if shp else None,
            "per_fold_deltas": shp},
        "market_partitions_used": partitions,
    }


def _verdict(placebo: dict) -> dict:
    """Apply the pre-registered falsification bar to the measured placebo."""
    mean = placebo["mean_daily_return_decay"].get("mean_signed_delta")
    cal_worst = max(CALENDAR_BAND["M4_CAL_mean_decay"],
                    CALENDAR_BAND["M4_CAL_MATCHED_mean_decay"])
    if mean is None:
        return {"label": "UNDECIDED", "reason": "no measurable placebo decay"}
    if mean >= cal_worst:
        return {"label": "CADENCE_ARTIFACT",
                "reason": (f"placebo mean decay {mean:.6f} lands inside/above the "
                           f"calendar band (worst {cal_worst:.6f}): a tape with no "
                           "market information reproduces the REGIME pattern"),
                "recommendation": "do not open RA-08 on this signal"}
    return {"label": "SURVIVED_FALSIFICATION",
            "reason": (f"placebo mean decay {mean:.6f} decays like/below calendar "
                       f"(worst {cal_worst:.6f}) while M4_REGIME measured "
                       f"{CALENDAR_BAND['M4_REGIME_mean_decay']:.6f}: the signal "
                       "survives its hardest control"),
            "recommendation": "proceed to request RA-08 approval (R-18)"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--placebo-seed", type=int, default=20260921,
                        help="seed for the synthetic placebo tape (registered on first run)")
    parser.add_argument("--lab-run-id", default=None)
    parser.add_argument("--evidence-dir", default=None)
    parser.add_argument("--register-only", action="store_true",
                        help="only append the FUP-05 registration + dataset lock, do not run placebo")
    args = parser.parse_args()

    policy = SandboxPolicy.discover(LAB_ROOT)
    started = time.perf_counter()
    reg = _append_registration()
    dataset = _discovery_dataset_record()

    if args.register_only:
        print(json.dumps({"registration": reg, "dataset": dataset}, indent=2))
        return 0

    from crypto_regime_lab.evidence.manifest import new_lab_run_id
    lab_run_id = args.lab_run_id or new_lab_run_id("fup05placebo")
    writer = EvidenceWriter.open(policy, study_id="regime_time_edge_ra_v1",
                                 lab_run_id=lab_run_id)
    run_dir = writer.run_dir
    evidence_dir = Path(args.evidence_dir) if args.evidence_dir else run_dir / "scratch"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    args.lab_run_id, args.evidence_dir = lab_run_id, str(evidence_dir)

    with writer.attempt("fup05_placebo") as att:
        placebo = run_placebo(args)
        verdict = _verdict(placebo)
        result = {
            "schema": "regime_lab.fup05_placebo.v1",
            "phase": RUN_ID, "registration_ref": REGISTRATION_REF,
            "purpose": ("PLACEBO_TIMING on the deep-dive window: does a synthetic "
                        "tape with no market information reproduce M4_REGIME's "
                        "positive mean decay at matched mechanics?"),
            "window": ["2021-01-01", "2022-01-01"], "trials": 50,
            "engine_report_level": "score", "placebo_seed": args.placebo_seed,
            "deepdive_run_id": DEEPDIVE_RUN_ID, "discovery_dataset": dataset,
            "disclosed_deviations": DISCLOSED_DEVIATIONS,
            "calendar_band": CALENDAR_BAND, "placebo": placebo, "verdict": verdict,
            "verdict_vocabulary": "DESCRIPTIVE_ONLY",
            "phase_wall_seconds": round(time.perf_counter() - started, 1),
        }
        writer.write_json("placebo_result.json", result, schema=result["schema"])
        att.detail = {"run_dir": str(run_dir), "verdict": verdict["label"]}
        # FUP-05's declaration lives under evidence/corrective_mode4_v3/FUP-05/
        # (same convention as FUP-04's report_level_memory_repair.json): the
        # declaration is the citable artifact, the RA-track run dir holds the
        # raw engine output. Copied by value with its hash recorded, so the two
        # can never silently diverge (the declaration test recomputes both).
        fup05_dir = LAB_ROOT / "evidence" / STUDY_ID / RUN_ID
        fup05_dir.mkdir(parents=True, exist_ok=True)
        declared_path = fup05_dir / "placebo_result.json"
        declared_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        att.detail["declaration"] = {
            "path": str(declared_path.relative_to(LAB_ROOT)),
            "sha256": sha256_file(declared_path),
            "source_run_dir": str(run_dir.relative_to(LAB_ROOT)),
            "source_sha256": sha256_file(run_dir / "placebo_result.json"),
        }

    print(json.dumps({"run_dir": str(run_dir), "verdict": verdict,
                      "fold_count": placebo["fold_count"],
                      "mean_decay": placebo["mean_daily_return_decay"].get("mean_signed_delta")},
                     indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

