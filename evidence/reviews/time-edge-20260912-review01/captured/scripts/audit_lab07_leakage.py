#!/usr/bin/env python
"""A leakage-specific re-audit of LAB-07 and its inputs from LAB-03 through LAB-06.

The phase audit asks whether each clause was discharged. This asks a narrower
and harsher question: **can any information from after a decision reach that
decision**, through the integration or through anything it inherited?

Each check is a property with an asserted precondition. A probe that would pass
because nothing happened is worse than no probe, so every one records whether it
actually had something to detect.
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


def load(name: str):
    path = CONFIGS / name
    return json.loads(path.read_text()) if path.is_file() else None


def check_role_boundary(trace: dict, eligibility: dict) -> dict:
    roles = eligibility["data_roles"]
    start, end = (pd.Timestamp(x) for x in trace["window"])
    return {
        "check": "the run stays inside the development role",
        "window": [str(start.date()), str(end.date())],
        "development": [roles["development"]["start"], roles["development"]["end"]],
        "outer_evaluation_starts": roles["outer_evaluation"]["start"],
        "had_something_to_detect": True,
        "passed": bool(start >= pd.Timestamp(roles["development"]["start"])
                       and end < pd.Timestamp(roles["outer_evaluation"]["start"])),
    }


def check_selection_causality(trace: dict, baseline: dict) -> dict:
    """A version may be requested only at or after the cutoff that selected it."""
    cell = next(c for c in baseline["cells"]
                if c["alpha_id"] == trace["alpha_id"] and c["symbol"] == trace["symbol"])
    rows = []
    for fold, switch in zip(cell["folds"][1:], trace["continuous_account"]["switches"]):
        evidence = fold["cutoff_evidence"]
        rows.append({
            "fold": fold["fold"],
            "trained_to": evidence["train_end"][:10],
            "cutoff": fold["cutoff"][:10],
            "requested_at_bar": switch["requested_at_bar"],
            "effective_at_bar": switch["effective_at_bar"],
            "train_end_at_or_before_cutoff":
                pd.Timestamp(evidence["train_end"]) <= pd.Timestamp(fold["cutoff"]),
            "effective_at_or_after_request":
                switch["effective_at_bar"] >= switch["requested_at_bar"],
        })
    return {
        "check": "every parameter version was selected before it was requested",
        "folds": rows,
        "had_something_to_detect": bool(rows),
        "passed": all(r["train_end_at_or_before_cutoff"] and r["effective_at_or_after_request"]
                      for r in rows),
    }


def check_future_mutation(trace: dict) -> dict:
    prefix = trace["prefix_stability"]
    return {
        "check": "replacing every input after a cutoff leaves the prefix bit-identical",
        "columns_mutated": prefix.get("columns_mutated"),
        "cutoff_bar": prefix["cutoff_bar"],
        "trades_before_the_cutoff": prefix["entries_in_prefix"],
        "had_something_to_detect": bool(prefix["suffix_actually_changed"]
                                        and prefix["entries_in_prefix"] > 0),
        "passed": bool(prefix["prefix_survives_future_mutation"]
                       and prefix["prefix_matches_longer_run"]),
        "note": ("this is also the empirical proof that the adapters' whole-slice indicator "
                 "precomputation is causal: if a value at bar t depended on any bar after the "
                 "cutoff, the prefix would move"),
    }


def check_activation_end(trace: dict) -> dict:
    guard = trace["activation_end_guard"]
    return {
        "check": "no activation event carries its own end",
        "activations_checked": guard["activations_checked"],
        "had_something_to_detect": guard["activations_checked"] > 0,
        "passed": guard["clean"],
    }


def check_segment_length(segments: dict) -> dict:
    guard = segments["future_length_guard"]
    return {
        "check": "no decision carries the length, end or total return of its own segment",
        "decisions_checked": guard["decisions_checked"],
        "open_segment_has_null_end": segments["open_segment_has_null_end"],
        "had_something_to_detect": guard["decisions_checked"] > 0 and segments["open"] > 0,
        "passed": bool(guard["clean"] and segments["open_segment_has_null_end"]),
    }


def check_regime_isolation(trace: dict) -> dict:
    isolation = trace["regime_information_isolation"]
    return {
        "check": "regime observations on the stream reach no decision in this calendar arm",
        "arm": isolation["arm"],
        "observations_on_the_stream": isolation["regime_observations_on_the_stream"],
        "activation_sources": isolation["activation_sources"],
        "had_something_to_detect": isolation["regime_observations_on_the_stream"] > 0,
        "passed": isolation["clean"],
    }


def check_job_cutoffs(trace: dict) -> dict:
    jobs = trace["training_jobs"]
    return {
        "check": "a refit reads nothing after its cutoff and pays a measured latency",
        "jobs": jobs["requested"],
        "latency_source": jobs["benchmark"]["source"],
        "zero_latency_jobs": jobs["zero_latency_jobs"],
        "min_delay_seconds": jobs["min_delay_seconds"],
        "deployment_account_reachable": jobs["deployment_account_reachable_from_here"],
        "had_something_to_detect": jobs["requested"] > 0,
        "passed": bool(jobs["zero_latency_jobs"] == 0
                       and jobs["benchmark"]["source"] == "measured_benchmark"
                       and jobs["deployment_account_reachable_from_here"] is False),
    }


def check_exit_fixed_point(trace: dict) -> dict:
    account = trace["continuous_account"]
    return {
        "check": "protective exits are iterated to a fixed point, not taken from one pass",
        "sweeps": account.get("sweeps"),
        "protective_exits": account.get("protective_exits"),
        "applied_exit_count": account.get("applied_exit_count"),
        "converged": account.get("exit_fixed_point_converged"),
        "had_something_to_detect": bool(account.get("protective_exits")),
        "passed": account.get("exit_fixed_point_converged") is True,
        "note": ("A-SC rests no protective orders, so this converges trivially on THIS cell. "
                 "The property is exercised on A-HMA, which does, in "
                 "test_the_fixed_point_holds_on_an_alpha_that_rests_protective_orders"),
    }


def check_publication_lag(trace: dict, lab_root: Path) -> dict:
    """LAB-07 must publish a regime observation no earlier than LAB-05 says it is knowable."""
    from crypto_regime_lab.data.panel import REGIME_INTERVAL

    expected = pd.Timedelta(REGIME_INTERVAL).total_seconds()
    used = trace.get("regime_publication_lag_seconds")
    lab05 = None
    for tape in reversed(sorted((lab_root / "evidence").rglob("emission_tape.json"))):
        document = json.loads(tape.read_text())
        if document.get("emissions"):
            record = document["emissions"][0]
            lab05 = (pd.Timestamp(record["available_at"])
                     - pd.Timestamp(record["observed_at"])).total_seconds()
            break
    return {
        "check": "a regime observation is published no earlier than LAB-05 says it is knowable",
        "regime_interval_seconds": expected,
        "lab07_lag_seconds": used,
        "lab05_emission_lag_seconds": lab05,
        "had_something_to_detect": used is not None and lab05 is not None,
        "passed": bool(used == expected and (lab05 is None or lab05 == expected)),
        "note": ("bars are left-labelled, so an observation stamped at a bar open is knowable "
                 "only when that bar closes. Publishing it sooner is a false availability that "
                 "the arms consuming regime information would inherit"),
    }


def check_parity_is_not_vacuous(trace: dict) -> dict:
    """Four surfaces that agree over empty lists are not four surfaces."""
    parity = trace["integration_baseline_parity"]
    hooks = trace["inert_hook_parity"]
    metrics = parity.get("canonical_metrics") or {}
    return {
        "check": "the parity surfaces compare something that actually moved",
        "canonical_fills": parity["canonical_fills"],
        "integrated_fills": parity["integrated_fills"],
        "inert_hook_fills_compared": hooks.get("fills_compared"),
        "metrics_fields_compared": sorted(metrics),
        "no_op_switch_fills": parity.get("no_op_switch_fills"),
        "had_something_to_detect": bool(parity["canonical_fills"] > 0
                                        and hooks.get("fills_compared", 0) > 0),
        "passed": bool(parity["identical"] and hooks["identical"]
                       and parity["canonical_fills"] > 0
                       and hooks.get("fills_compared", 0) > 0
                       and len(metrics) >= 4),
    }


def check_upstream_causality(causality: dict | None) -> dict:
    if causality is None:
        return {"check": "the four-layer causality gate", "passed": False,
                "had_something_to_detect": False,
                "note": "configs/causality_verification.json is missing"}
    return {
        "check": "loader, resampler, scaler, model and stream are each causal",
        "verdicts": causality["verdicts"],
        "leaky_control_detected": causality["leaky_control_is_detected"],
        "had_something_to_detect": causality["leaky_control_is_detected"],
        "passed": causality["status"] == "CAUSAL",
    }


def check_read_lock(readlock: dict | None) -> dict:
    if readlock is None:
        return {"check": "the read-lock", "passed": False, "had_something_to_detect": False}
    return {
        "check": "the bytes the run read still are what the manifest recorded",
        "status": readlock["status"],
        "snapshot_files_changed": len(readlock["snapshot_files_changed"]),
        "content_revisions": len(readlock.get("closed_partition_content_revisions") or []),
        "had_something_to_detect": bool(readlock["source_files_changed"]),
        "passed": bool(not readlock["snapshot_files_changed"]
                       and readlock["primary_run_valid"]),
    }


def main() -> int:
    policy = SandboxPolicy.load(CONFIGS / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    trace = load("lab07_continuous_trace.json")
    if trace is None:
        print("BLOCKED: run scripts/run_lab07.py first")
        return 1
    segments = load("operational_segments.json")
    baseline = load("lab04_calendar_baseline.json")
    eligibility = load("data_eligibility.json")

    with writer.attempt("L07.leakage_audit") as att:
        checks = [
            check_role_boundary(trace, eligibility),
            check_selection_causality(trace, baseline),
            check_future_mutation(trace),
            check_activation_end(trace),
            check_segment_length(segments),
            check_regime_isolation(trace),
            check_job_cutoffs(trace),
            check_exit_fixed_point(trace),
            check_publication_lag(trace, LAB_ROOT),
            check_parity_is_not_vacuous(trace),
            check_upstream_causality(load("causality_verification.json")),
            check_read_lock(load("readlock_verification.json")),
        ]
        att.detail = {"checks": len(checks),
                      "passed": sum(1 for c in checks if c["passed"])}

    vacuous = [c["check"] for c in checks if not c.get("had_something_to_detect")]
    document = {
        "schema": "crypto_regime_lab.lab07_leakage_audit.v1",
        "checked_at_utc": utc_now_iso(),
        "scope": ("LAB-07 and everything it inherits: the snapshot (LAB-03), the selections "
                  "(LAB-04), the state provider (LAB-05) and the decision ledger (LAB-06)"),
        "checks": checks,
        "checks_total": len(checks),
        "checks_passed": sum(1 for c in checks if c["passed"]),
        "checks_failed": [c["check"] for c in checks if not c["passed"]],
        "checks_with_nothing_to_detect": vacuous,
        "vacuity_rule": (
            "a probe that had nothing to detect is reported, not counted as evidence. Every "
            "defect found in LAB-06 and LAB-07 was a gate that passed because nothing happened"),
        "status": ("CLEAN" if all(c["passed"] for c in checks) else "LEAK_OR_UNPROVEN"),
    }
    writer.write_config("lab07_leakage_audit.json", document)
    writer.write_json("lab07_leakage_audit.json", document, schema=document["schema"])

    for check in checks:
        mark = "PASS" if check["passed"] else "FAIL"
        vac = "" if check.get("had_something_to_detect") else "   (nothing to detect)"
        print(f"  {mark}  {check['check']}{vac}")
    print(f"status: {document['status']} "
          f"({document['checks_passed']}/{document['checks_total']})")
    if vacuous:
        print(f"probes with nothing to detect: {vacuous}")
    print(f"evidence -> {writer.run_dir}")
    return 0 if document["status"] == "CLEAN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
