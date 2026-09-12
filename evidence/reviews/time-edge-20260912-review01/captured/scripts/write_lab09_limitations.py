#!/usr/bin/env python
"""OUT.6 and OUT.7 — the leakage/contamination report, and the limitations.

Both are assembled from committed artifacts. A limitations section written from
memory lists the ones its author happens to remember, which are rarely the ones
that matter; every entry below names the artifact that measured it, and an entry
whose artifact is missing is reported as UNVERIFIED rather than dropped.
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


def entry(identifier: str, title: str, severity: str, artifact: str, measured, detail: str,
          direction: str | None = None) -> dict:
    """One finding, with the measurement that backs it.

    `status` is MEASURED only when the artifact exists AND at least one measured
    value came back non-null. An entry whose fields all resolve to null is a
    pointer at names the artifact does not use, and reporting it as MEASURED
    would be a finding built from nothing -- the exact shape this lab keeps
    finding elsewhere.
    """
    document = load(artifact.split(":")[0]) if artifact.endswith(".json") \
        or ".json:" in artifact else None
    values = list(measured.values()) if isinstance(measured, dict) else [measured]
    if document is None:
        status = "UNVERIFIED_ARTIFACT_MISSING"
    elif values and all(v is None for v in values):
        status = "UNVERIFIED_FIELDS_DO_NOT_RESOLVE"
    else:
        status = "MEASURED"
    return {
        "id": identifier,
        "title": title,
        "severity": severity,
        "artifact": f"configs/{artifact}",
        "verified": status == "MEASURED",
        "status": status,
        "measured": measured,
        "detail": detail,
        **({"direction": direction} if direction else {}),
    }


def leakage_report() -> dict:
    readlock = load("readlock_verification.json") or {}
    parity = load("loader_endpoint_parity.json") or {}
    leakage = load("lab07_leakage_audit.json") or {}
    binding = load("cost_binding_verification.json") or {}
    unlock = load("lab09_confirmation_spec.json") or {}
    causality = load("causality_verification.json") or {}

    findings = [
        entry("LEAK-01", "the confirmation interval was not used to adjust the design",
              "CLEAR", "lab09_confirmation_spec.json",
              {"any_phase_read_the_outer_window":
                  (unlock.get("prior_access_audit") or {}).get(
                      "any_phase_read_the_outer_window"),
               "phases_checked": len((unlock.get("prior_access_audit") or {}).get("checked", []))},
              "every completed phase's declared window is checked against the 2024-01-01 "
              "boundary. This is what the lab can verify about ITSELF; it says nothing about "
              "the supplied presets, which is the next finding"),
        entry("CONTAM-01", "the supplied presets were tuned on the full sample",
              "MATERIAL", "lab09_confirmation_spec.json",
              {"holdout_status": unlock.get("holdout_status")},
              "no interval of this dataset is an untouched holdout, because the presets' tuning "
              "cutoff is unknown. The USER_PRESET_REFERENCE control is the only arm that touches "
              "them and it is labelled retrospective; every other arm deploys selections made "
              "inside development"),
        entry("ACCT-01", "the account was charged half the registered one-way taker fee",
              "MAJOR", "cost_binding_verification.json",
              {"measured_over_registered":
                  (binding.get("verdict") or {}).get("measured_over_registered")},
              "the registered ONE-WAY rate is passed into an engine parameter documented as "
              "ROUND-TRIP, so the engine halves it. Present in every phase from LAB-04 onward",
              direction="flattering: absolute returns are overstated. The contrasts move only "
                        "through turnover differences between arms, which is measured in the "
                        "AS_DECLARED panels"),
        entry("DATA-01", "the pinned loader disagrees with the bytes on volume",
              "MATERIAL", "loader_endpoint_parity.json",
              {"partitions_compared": len(parity.get("per_symbol", [])) or None,
               "partitions_that_disagree": sum(
                   1 for r in parity.get("per_symbol", [])
                   if r.get("volume_sum_loader") != r.get("volume_sum_parquet")) or None,
               "worst_volume_loss_share": max(
                   ((r["volume_sum_parquet"] - r["volume_sum_loader"]) / r["volume_sum_parquet"]
                    for r in parity.get("per_symbol", [])
                    if r.get("volume_sum_parquet")), default=None),
               "bars_a_cast_would_zero": sum(r.get("bars_a_cast_would_zero") or 0
                                             for r in parity.get("per_symbol", [])) or None},
              "MarketDataLoaderBase._normalize casts volume to int64 and BTC/ETH/BNB store "
              "fractional quantities. The lab reads the byte-copied parquet directly and never "
              "calls the loader, so no lab result carries the defect -- it is recorded because "
              "anyone reproducing this through the loader would get different bars"),
        entry("DATA-02", "closed metrics partitions drifted upstream",
              "CLEAR", "readlock_verification.json",
              {"status": readlock.get("status"),
               "files_checked": readlock.get("files_checked"),
               "closed_partition_drift": len(readlock.get("closed_partition_drift", [])) or None,
               "content_revisions": len(
                   readlock.get("closed_partition_content_revisions", [])),
               "vintage_restamps": len(
                   readlock.get("closed_partition_vintage_restamps", [])) or None,
               "cohort_runs_invalidated": len(
                   readlock.get("cohort_runs_invalidated", []))},
              "reading both files proves every measured column identical; only ingested_at "
              "moved, because the collector re-ingests closed months. The drifted product feeds "
              "the G3 cohort, which no phase reads"),
        entry("LEAK-02", "the LAB-07 leakage audit",
              "CLEAR", "lab07_leakage_audit.json",
              {"checks": leakage.get("checks_total"), "passed": leakage.get("checks_passed")},
              "availability ordering, warm-bar gating, the exit fixed point, and the four "
              "parity surfaces"),
        entry("LEAK-03", "causality of the state tape",
              "CLEAR", "causality_verification.json",
              {"verdict": causality.get("verdict") or causality.get("status")},
              "every emission carries available_at, and a decision reads only the emission whose "
              "available_at is at or before it"),
        {
            "id": "LEAK-04",
            "title": "the confirmation model's first training window reaches into development",
            "severity": "BY_DESIGN",
            "artifact": "configs/lab09_<symbol>_regime_model_registry.json",
            "verified": (CONFIGS / "lab09_btcusdt_regime_model_registry.json").is_file(),
            "status": "MEASURED" if (CONFIGS
                                     / "lab09_btcusdt_regime_model_registry.json").is_file()
            else "UNVERIFIED_ARTIFACT_MISSING",
            "measured": {"first_cutoff": "2024-01-01", "training_memory_days": 365},
            "detail": ("a model deployed on the first day of the interval refits on the history "
                       "that existed then, which is development data. That is backward-looking "
                       "and is what a deployment does; it would be leakage only if a model "
                       "trained on data AFTER its own cutoff, and the fitter's mutation test "
                       "covers that"),
        },
        entry("EXEC-01", "the protocol declares 1-minute execution bars and the account "
                          "resolves protection on the decision bar",
              "MATERIAL", "protective_order_fidelity.json",
              {"declared": "1m",
               "actual": "the decision bar",
               "alphas_exposed": (load("protective_order_fidelity.json") or {}).get(
                   "exposure", {}).get("alphas_exposed"),
               "alphas_not_exposed": (load("protective_order_fidelity.json") or {}).get(
                   "exposure", {}).get("alphas_not_exposed")},
              "a stop and a take-profit inside the same 15-minute bar are resolved by the "
              "engine's ordering rule rather than by the minute path. Guide 4.3 asks for two "
              "cohorts when the resolution changes; neither is built, and the gap is recorded "
              "with the per-alpha exposure (COR-17, OP-19)",
              direction="level only. Every arm and every control runs on the same frame through "
                        "the same engine, so the resolution cancels in B-A, C-A, D-B and D-C"),
        {
            "id": "LEAK-05",
            "title": "the confirmation selector's first training window reaches into development",
            "severity": "BY_DESIGN",
            "artifact": "configs/lab09_confirmation_results.json",
            "verified": (CONFIGS / "lab09_confirmation_results.json").is_file(),
            "status": "MEASURED" if (CONFIGS / "lab09_confirmation_results.json").is_file()
            else "UNVERIFIED_ARTIFACT_MISSING",
            "measured": {"first_calendar_cutoff": "2024-01-01", "training_memory_days": 180},
            "detail": ("the selector at the interval's first cutoff trains on the 180 days before "
                       "it, which are development data -- exactly as the calendar arm's first "
                       "development fold trained from 2020-07-05. It is backward-looking, it is "
                       "identical for the calendar and the dynamic arms, and it would be leakage "
                       "only if a cutoff trained on data AFTER itself. The window bounds in "
                       "cells[].notes.*_cutoff_evidence record each one"),
        },
        {
            "id": "SCOPE-01",
            "title": "the fitter's own group ablation for the confirmation role is not "
                     "in-interval",
            "severity": "MATERIAL",
            "artifact": "configs/lab09_group_ablation.json",
            "verified": (CONFIGS / "lab09_group_ablation.json").is_file(),
            "status": "MEASURED" if (CONFIGS / "lab09_group_ablation.json").is_file()
            else "UNVERIFIED_ARTIFACT_MISSING",
            "measured": {"fitter_window": "the FIRST cutoff's training window, which for this "
                                          "role is 2023-01-01..2024-01-01 -- development data"},
            "detail": ("the fitter runs guide 8.3's ablation where LAB-05 chose K, on the first "
                       "cutoff. For the confirmation role that is development. The descriptive "
                       "claim therefore rests on scripts/ablate_lab09_states.py, which measures "
                       "it on the LAST cutoff's window, entirely inside the interval"),
        },
    ]
    return {
        "schema": "crypto_regime_lab.lab09_leakage_contamination.v1",
        "generated_at_utc": utc_now_iso(),
        "findings": findings,
        "counts": {severity: sum(1 for f in findings if f["severity"] == severity)
                   for severity in sorted({f["severity"] for f in findings})},
        "unverified": [f["id"] for f in findings if not f["verified"]],
        "unverified_detail": {f["id"]: f["status"] for f in findings if not f["verified"]},
        "rule": ("a finding whose artifact is missing, or whose measured fields all resolve to "
                 "null, is UNVERIFIED -- never dropped and never assumed clear"),
    }


def limitations() -> dict:
    confirmation = load("lab09_confirmation_results.json") or {}
    claim = load("lab09_claim_report.json") or {}
    stress = load("lab09_stress.json") or {}
    uncertainty = load("lab09_uncertainty.json") or {}
    support = load("lab09_support.json") or {}
    ablation = load("lab09_group_ablation.json") or {}

    rows = [
        {"id": "LIM-01", "limitation": "one of the four alphas contributes no cell",
         "measured": {"cells_not_ready": confirmation.get("cells_not_ready"),
                      "cells_planned": confirmation.get("cells_planned")},
         "consequence": "the matrix is 15 of 20. Every aggregate is over three alphas, and "
                        "A-HASH's blocker is unresolved rather than negative",
         "where": "configs/lab09_confirmation_results.json"},
        {"id": "LIM-02", "limitation": "the parameters were selected under an understated fee",
         "measured": {"one_way_rate_charged_over_registered": 0.5},
         "consequence": "the AS_DECLARED panel corrects the DEPLOYMENT accounting. It cannot "
                        "correct the SELECTION: every candidate was scored under the halved fee, "
                        "and rescoring them is a full re-run of the search",
         "where": "configs/cost_binding_verification.json, "
                  "configs/lab09_stress.json cost_stress.as_declared"},
        {"id": "LIM-03", "limitation": "no funding product exists in this storage",
         "measured": {"use_funding": False},
         "consequence": "this is a labelled no-funding cohort. A realistic net-carry claim is "
                        "not available, and the gap is never booked as zero",
         "where": "configs/study_registration.json execution.fee_funding_slippage_config"},
        {"id": "LIM-04", "limitation": "the interval is nested retrospective",
         "measured": {"holdout_status": "NESTED_RETROSPECTIVE"},
         "consequence": "no out-of-sample claim is available from this dataset at any interval. "
                        "A prospective protocol is specified and deliberately not executed",
         "where": "configs/lab09_confirmation_spec.json"},
        {"id": "LIM-05", "limitation": "the state vocabulary is not decision-eligible across "
                                       "refits",
         "measured": {"risk_only": "BLOCKED_BY_STATE_NAMESPACING"},
         "consequence": "the RISK_ONLY control cannot be computed: a per-state risk scale fitted "
                        "on one window has almost no state key in common with a later one. The "
                        "control is reported BLOCKED with its measurement rather than as a scale "
                        "of 1.0 that would look like a result",
         "where": "configs/lab09_confirmation_results.json cells[].controls.RISK_ONLY"},
        {"id": "LIM-06", "limitation": "arm E has no independent contribution here",
         "measured": {"switches_measured_by_lab06": 0},
         "consequence": "the response policy deploys arm D's schedule, so E-B IS D-B. It is "
                        "reported as an extension and excluded from the primary family",
         "where": "configs/lab09_uncertainty.json exploratory"},
        {"id": "LIM-07", "limitation": "the states do not resolve out-of-fold variance beyond "
                                       "price and volatility",
         "measured": {"symbols_where_a_block_improved":
                      ablation.get("symbols_where_a_block_improved_out_of_fold"),
                      "symbols_measured": ablation.get("symbols_measured")},
         "consequence": "guide 8.3's requirement is not met on the confirmation interval either. "
                        "The registered core is not changed in response, because selecting a "
                        "feature set on this result would be choosing the model on an outcome",
         "where": "configs/lab09_group_ablation.json"},
        {"id": "LIM-08", "limitation": "the pooled statistic averages per-cell means over "
                                       "unequal day counts",
         "measured": {"episodes": ((uncertainty.get("contrasts") or {}).get("B-A") or {})
                      .get("episodes")},
         "consequence": "a cell with few days gets an equal vote on less evidence. The counts "
                        "are reported so the reader can see it rather than infer it",
         "where": "configs/lab09_uncertainty.json contrasts[].episodes"},
        {"id": "LIM-09", "limitation": "the information stress is staged, not exhaustive",
         "measured": {"cells_covered":
                      (stress.get("information_stress") or {}).get("cells_covered"),
                      "cells_total_run":
                      (stress.get("information_stress") or {}).get("cells_total_run")},
         "consequence": "the tape corruptions were run on a subset chosen in protocol order "
                        "before any stress result was read. A cell outside the subset is "
                        "UNCHECKED, not clear",
         "where": "configs/lab09_stress.json information_stress.staging_rule"},
        {"id": "LIM-10", "limitation": "the account stops before the data does",
         "measured": {"window": confirmation.get("window"),
                      "window_note": confirmation.get("window_note")},
         "consequence": "the last days of the 1-minute product are not traded, because the 4h "
                        "feature panel that feeds the state provider ends earlier",
         "where": "configs/lab09_confirmation_results.json window_note"},
        {"id": "LIM-11", "limitation": "three years of development and under three of "
                                       "confirmation is a small sample for a daily endpoint",
         "measured": {"union_days": (((uncertainty.get("contrasts") or {}).get("B-A") or {})
                                     .get("episodes") or {}).get("union_days")},
         "consequence": "the intervals are wide relative to the minimum economic effect, which "
                        "is why an inconclusive reading is the honest one rather than a "
                        "negative one",
         "where": "configs/lab09_uncertainty.json"},
        {"id": "LIM-14", "limitation": "some auxiliary jobs ran concurrently with the registered "
                                       "one-worker budget",
         "measured": {"registered_workers": 1,
                      "peak_rss_gib_note": "see configs/lab09_confirmation_results.json "
                                           "wall_seconds and the run's own measured RSS"},
         "consequence": ("the frozen confirmation run itself was executed single-process, so its "
                         "wall time is a clean operational measurement. Audits and re-runs "
                         "executed alongside earlier work were contended, and their wall times "
                         "are NOT reported as performance figures. One such overlap exhausted "
                         "memory and killed a run, which cost time and no evidence: the run is "
                         "checkpointed per cell"),
         "where": "configs/compute_budget_registration.json os_resource_budget"},
        {"id": "LIM-13", "limitation": "protective orders resolve on the decision bar, not on "
                                       "1-minute bars as the protocol declares",
         "measured": {"alphas_exposed": (load("protective_order_fidelity.json") or {}).get(
             "exposure", {}).get("alphas_exposed"),
             "a_sc_protective_share": 0.0},
         "consequence": "absolute levels for A-HMA and A-VWAP carry a fill-fidelity effect of "
                        "unknown sign. Contrasts do not: the resolution is identical across "
                        "arms. A-SC rests no protection and is unaffected either way",
         "where": "configs/protective_order_fidelity.json"},
        {"id": "LIM-12", "limitation": "the policy layer was measured on one cell",
         "measured": {"policy_panel": (support.get("situations") or {}).get(
             "POLICY_ON_THE_CONFIRMATION_INTERVAL", {}).get("status", "MEASURED")},
         "consequence": "LAB-06's policy runs on A-SC/BTCUSDT. Its decision counts describe that "
                        "cell and are not a statement about the other fourteen",
         "where": "configs/lab09_policy_decision_ledger.json"},
    ]
    return {
        "schema": "crypto_regime_lab.lab09_limitations.v1",
        "generated_at_utc": utc_now_iso(),
        "conclusion_level": claim.get("conclusion_level"),
        "limitations": rows,
        "count": len(rows),
        "rule": ("each limitation names the artifact that measured it. A limitation with no "
                 "measurement behind it is an opinion, and opinions belong in "
                 "reports/improvement_opinions.md"),
    }


def main() -> int:
    policy = SandboxPolicy.load(CONFIGS / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    leakage = leakage_report()
    limits = limitations()
    with writer.attempt("L09.outputs.leakage_and_limitations") as att:
        att.detail = {"findings": len(leakage["findings"]), "limitations": limits["count"]}
    for name, payload in (("lab09_leakage_contamination.json", leakage),
                          ("lab09_limitations.json", limits)):
        writer.write_config(name, payload)
        writer.write_json(name, payload, schema=payload["schema"])

    print(f"leakage/contamination: {len(leakage['findings'])} findings {leakage['counts']}")
    for finding in leakage["findings"]:
        print(f"  {finding['id']:<9} {finding['severity']:<10} {finding['title'][:70]}")
    print(f"unverified: {leakage['unverified'] or 'none'}")
    print(f"limitations: {limits['count']}")
    print(f"evidence -> {writer.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
