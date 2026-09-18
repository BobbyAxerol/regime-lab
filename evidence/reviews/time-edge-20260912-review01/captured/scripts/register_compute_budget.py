#!/usr/bin/env python
"""Guide 10.5 + L01.5 — register the compute-budget contract BEFORE arms C/D/E exist.

L01.5 lists "compute budgets" among the things preregistration must fix, and
guide 10.5 says exactly what that means: two parallel reports, and an
experiment-search ledger that counts every search decision rather than only the
Optuna alpha trials.

`configs/study_registration.json` pinned `resource_budget` -- one worker, two
CPUs, four GiB. That is the OS budget, not the comparison contract, and the
comparison contract is the one that can be gamed. It has to be fixed before
LAB-07 builds the refit scheduler, because after that the definition of "matched
compute" could be chosen once it is visible which definition flatters the new
method. Guide 10.5: "Không giảm time interval, phí, output hoặc số thử của
baseline để phương pháp mới đẹp hơn."

The ledger is opened with what LAB-04/05/06 ALREADY spent, read from their
artifacts, so it starts from measured history rather than from zero.
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


def load(name: str):
    path = CONFIGS / name
    return json.loads(path.read_text()) if path.is_file() else None


def spent_so_far() -> dict:
    """What the completed phases actually consumed, read from their artifacts."""
    baseline = load("lab04_calendar_baseline.json") or {}
    registry = load("lab05_regime_model_registry.json") or {}
    response = load("lab06_response_model.json") or {}
    ledger = load("lab06_decision_ledger.json") or {}
    k_sel = load("lab05_k_selection.json") or {}

    effort = baseline.get("search_effort", {})
    trace = load("lab07_continuous_trace.json")
    entries = [
        {
            "phase": "LAB-04", "kind": "candidate_evaluation",
            "what_was_searched": "robust-neighborhood probes around anchors, per cutoff",
            "unique_executions": effort.get("unique_executions"),
            "candidate_episode_visits": effort.get("candidate_episode_visits"),
            "wall_seconds": baseline.get("wall_seconds"),
            "design": baseline.get("search_budget"),
            "counts_against": "MATCHED_TOTAL_COMPUTE",
        },
        {
            "phase": "LAB-05", "kind": "model_fit",
            "what_was_searched": "jump-model fits on a rolling training memory",
            "fits": len(registry.get("models") or []),
            "starts_per_fit": len((registry.get("models") or [{}])[0].get("seeds", [])),
            "observation_interval": registry.get("observation_interval"),
            "counts_against": "MATCHED_TOTAL_COMPUTE",
        },
        {
            "phase": "LAB-05", "kind": "state_count_choice",
            "what_was_searched": "K",
            "candidates_considered": k_sel.get("candidates_considered"),
            "registered_starting_k": k_sel.get("registered_starting_k"),
            "k_used": k_sel.get("registered_k_used"),
            "chart_inspection_used": k_sel.get("chart_inspection_used"),
            "counts_against": "MATCHED_TOTAL_COMPUTE",
            "note": ("guide 10.5 names state-count choices as search. Counting only the alpha "
                     "trials would make the regime arm look cheaper than it is"),
        },
        {
            "phase": "LAB-05", "kind": "jump_penalty",
            "what_was_searched": "lambda_jump",
            "value_used": registry.get("lambda_jump"),
            "counts_against": "MATCHED_TOTAL_COMPUTE",
        },
        {
            "phase": "LAB-06", "kind": "response_hyperparameters",
            "what_was_searched": "bandwidth h, recency tau, shrinkage kappa, support gates",
            "values": response.get("hyperparameters"),
            "response_estimates": response.get("response_count"),
            "counts_against": "MATCHED_TOTAL_COMPUTE",
        },
        {
            "phase": "LAB-06", "kind": "switching_threshold",
            "what_was_searched": "z_alpha, delta margin, minimum spacing",
            "decisions_assessed": ledger.get("decisions"),
            "counts_against": "MATCHED_TOTAL_COMPUTE",
        },
    ]
    if trace:
        jobs = trace["training_jobs"]
        account = trace["continuous_account"]
        entries.append({
            "phase": "LAB-07", "kind": "operational_latency",
            "what_was_searched": "nothing; this is the OPERATIONAL_POLICY cost of delivering",
            "refit_jobs": jobs["requested"],
            "measured_seconds_per_fit": jobs["benchmark"]["measured_seconds_per_fit"],
            "latency_source": jobs["benchmark"]["source"],
            "min_refit_delay_seconds": jobs["min_delay_seconds"],
            "max_refit_delay_seconds": jobs["max_delay_seconds"],
            "activation_delay_bars": [s["blocked_bars"] for s in account["switches"]],
            "network_calls": 0,
            "counts_against": "OPERATIONAL_POLICY",
            "note": ("guide L07.3 forbids a refit latency of zero; this is the measured one. The "
                     "activation delays are the OTHER half of the operational cost -- a switch "
                     "that waits 368 bars for a flat book has a cost no latency model captures"),
        })
        entries.append({
            "phase": "LAB-07", "kind": "switching_policy_parameter",
            "what_was_searched": "the warm-bar requirement before a version may activate",
            "resolved_to": "derived from each adapter's own warmup_bars()",
            "values_used": account.get("warm_bar_requirements"),
            "free_parameter": False,
            "counts_against": "MATCHED_TOTAL_COMPUTE",
            "note": ("it started as a hardcoded 64 and moved the result (+0.45% vs -3.07% at 512 "
                     "bars), which is exactly what guide 10.5 means by a search decision that "
                     "must be logged. Deriving it from the alpha's own declaration removes it "
                     "from the search space rather than leaving it unregistered"),
        })
    return {"schema": "crypto_regime_lab.experiment_search_ledger.v1", "entries": entries}


def main() -> int:
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)
    registration = load("study_registration.json") or {}
    # The REGISTRATION is immutable: re-stamping registered_at_utc after LAB-07
    # landed would destroy the only evidence that the contract pre-dated the arm
    # whose cost it governs. The LEDGER appends.
    previous = load("compute_budget_registration.json")
    registered_at = (previous or {}).get("registered_at_utc") or utc_now_iso()

    document = {
        "schema": "crypto_regime_lab.compute_budget_registration.v1",
        "study_id": STUDY_ID,
        "guide_section": "10.5",
        "registered_at_utc": registered_at,
        "ledger_last_appended_utc": utc_now_iso(),
        "registration_is_immutable": (
            "registered_at_utc is preserved across re-runs. Re-stamping it after a phase landed "
            "would destroy the only evidence that the contract pre-dated the arm whose cost it "
            "governs; the ledger below appends instead"),
        "registered_before": ("LAB-07. No arm beyond A and B exists yet, so no definition here "
                              "can have been chosen to favour an arm whose cost is already known"),
        "os_resource_budget": registration.get("resource_budget"),
        "os_budget_is_not_the_comparison_contract": (
            "resource_budget pins workers/CPU/memory. It says nothing about whether two arms were "
            "given the same number of chances to find a good parameter set, which is the thing a "
            "comparison can be gamed on"),
        "reports": {
            "MATCHED_TOTAL_COMPUTE": {
                "question": "given the SAME total search effort, does the new method win?",
                "counted_units": [
                    "unique strategy evaluations (candidate x market x economics x seed)",
                    "fold-bar visits",
                    "independent local probes",
                    "regime model fits, including every multi-start",
                    "response evaluations",
                ],
                "rule": ("every arm is allotted the same total, and a unit is counted wherever it "
                         "is spent. A regime arm that spends its budget on model fits instead of "
                         "on alpha trials has still spent it"),
                "reported_per": "arm x cell",
            },
            "OPERATIONAL_POLICY": {
                "question": "at an equivalent per-refit budget, what does each method actually cost to run?",
                "counted_units": ["wall seconds per refit", "total wall seconds",
                                  "network calls (zero by policy during run/certify/report)",
                                  "activation latency"],
                "rule": ("real measured cost, never a modelled one. Guide L07.3 forbids taking a "
                         "refit latency of zero in order to fill earlier"),
                "reported_per": "arm x refit",
            },
        },
        "baseline_protection_rule": (
            "the baseline's time interval, fees, outputs and number of attempts are never reduced "
            "to make the new method look better (guide 10.5). A change to any of them is a change "
            "to BOTH arms or it is not made"),
        "sequencing_rule": (
            "the primary comparison runs on a deterministic sequential schedule or a fixed "
            "candidate matrix that reproduces. Adaptive batch and sequential have different "
            "semantics and are never reported as the same sequence [S10]"),
        "what_counts_as_search": [
            "optimizer trials on alpha parameters",
            "state-count (K) choices",
            "jump penalties",
            "response bandwidth and shrinkage",
            "switching thresholds",
            "alpha revisions",
        ],
        "what_counts_as_search_rule": (
            "guide 10.5: 'Không chỉ log Optuna alpha trials.' A method whose tuning happens "
            "outside the optimizer is not cheaper, it is accounted for elsewhere -- and if that "
            "elsewhere is nowhere, the comparison is wrong in the new method's favour"),
        "ledger_opened_with": spent_so_far(),
        "status": "REGISTERED_BEFORE_LAB07",
        "owed_by": {
            "LAB-07": "per-refit wall seconds and activation latency, measured not assumed",
            "LAB-08": "the per-arm MATCHED_TOTAL_COMPUTE table across the 20 cells",
        },
    }

    with writer.attempt("L01.5.register_compute_budget") as att:
        att.detail = {"entries": len(document["ledger_opened_with"]["entries"])}
    writer.write_config("compute_budget_registration.json", document)
    writer.write_json("compute_budget_registration.json", document, schema=document["schema"])

    print(f"registered {len(document['reports'])} budget reports, "
          f"{len(document['what_counts_as_search'])} search kinds")
    for entry in document["ledger_opened_with"]["entries"]:
        detail = {k: v for k, v in entry.items()
                  if k not in ("phase", "kind", "what_was_searched", "counts_against", "note")}
        print(f"  {entry['phase']} {entry['kind']:<26} {json.dumps(detail)[:110]}")
    print(f"evidence -> {writer.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
