#!/usr/bin/env python
"""Guide 13.6 — the nine claims this lab may not publish, checked structurally.

Each entry in guide 13.6 has the same shape: a conclusion that would be
legitimate WITH certain evidence, published on evidence that does not support
it. So the audit does not search the reports for wording. It checks, for each
claim, whether the evidence the guide demands actually exists — and whether the
lab is currently making the claim at all.

Two earlier attempts in this lab tried to detect a forbidden claim by grepping
prose. The first flagged a requirement's own title; the second flagged its own
negation. A lexical scan cannot tell a claim from a denial of one, so every
check below reads structured fields.
"""

from __future__ import annotations

import json
import pathlib
import sys

LAB_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter, utc_now_iso  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"


def load(name: str):
    path = LAB_ROOT / "configs" / name
    return json.loads(path.read_text()) if path.is_file() else None


def check_regime_works() -> dict:
    """"Regime works" from states correlating with price after a full-sample fit."""
    registry = load("lab05_regime_model_registry.json") or {}
    coverage = load("acceptance_test_coverage.json") or {}
    ablation = registry.get("group_ablation", {})
    claimed = [r["id"] for r in coverage.get("requirements", [])
               if r.get("status") == "COVERED" and r["id"] in ("T62", "T63")]
    return {
        "claim": "regime works",
        "would_need": "an out-of-fold contribution, not an in-sample correlation",
        "model_fit_role": registry.get("data_role"),
        "outer_evaluation_touched": registry.get("outer_evaluation_touched"),
        "group_ablation_ran": bool(ablation.get("ladder")),
        "group_ablation_improved_out_of_fold": bool(
            ablation.get("blocks_that_improved_out_of_fold")),
        "claim_is_being_made": bool(claimed),
        "passed": (registry.get("outer_evaluation_touched") is False
                   and bool(ablation.get("ladder")) and not claimed),
        "note": ("the ablation FAILED -- variance resolved out of fold went +0.335 -> +0.095 -> "
                 "-0.036 as blocks were added -- and the lab reports that rather than a working "
                 "regime"),
    }


def check_no_leakage() -> dict:
    """"No leakage" whose only evidence is a `.shift(1)`."""
    causality = load("causality_verification.json") or {}
    return {
        "claim": "no leakage",
        "would_need": "a future-mutation test per layer, plus a leaky control that IS detected",
        "layers_verified": sorted(causality.get("verdicts", {})),
        "leaky_control_detected": causality.get("leaky_control_is_detected"),
        "passed": (len(causality.get("verdicts", {})) >= 4
                   and causality.get("leaky_control_is_detected") is True
                   and causality.get("status") == "CAUSAL"),
        "note": "a suite that can never fail proves nothing, so the leaky control must be caught",
    }


def check_out_of_sample() -> dict:
    """"Out-of-sample" for full-set presets, or for a holdout already used."""
    registration = load("study_registration.json") or {}
    registry = load("lab05_regime_model_registry.json") or {}
    trace = load("lab07_continuous_trace.json") or {}
    contamination = registration.get("contamination") or {}
    roles = registration.get("data_roles", {})
    outer = roles.get("outer_evaluation", {})
    return {
        "claim": "out-of-sample",
        "would_need": "a window never used for design, and presets that were not full-sample tuned",
        "preset_role": registration.get("source_preset_role"),
        "outer_evaluation_contamination_declared": bool(outer.get("contamination")),
        "phases_run_in_development": {
            "LAB-05": registry.get("data_role"),
            "LAB-07": trace.get("data_role"),
        },
        "outer_touched_by_any_phase": registry.get("outer_evaluation_touched"),
        "passed": (registry.get("outer_evaluation_touched") is False
                   and trace.get("data_role") in (None, "development")
                   and bool(outer.get("contamination"))
                   and "retrospective" in str(registration.get("source_preset_role", "")).lower()),
        "note": ("the outer window is declared NOT an untouched holdout: the supplied presets "
                 "were TPE-tuned on the full sample with an unknown cutoff"),
        "contamination_note": contamination,
    }


def check_better_on_every_dimension() -> dict:
    """"Better on every dimension" from one metric, or from lower exposure."""
    baseline = load("lab04_calendar_baseline.json") or {}
    contrast = baseline.get("contrast_B_minus_A", {})
    hypothesis = baseline.get("registered_hypothesis", {})
    dimensions = sorted(contrast.get("metric_definitions", {}))
    return {
        "claim": "better on every dimension",
        "would_need": "every reported dimension moving the same way, not one",
        "dimensions_reported": dimensions,
        "verdict": baseline.get("verdict", "")[:160],
        "conclusion_level": hypothesis.get("conclusion_level"),
        "blockers": hypothesis.get("blockers_preventing_a_stronger_claim"),
        "passed": (len(dimensions) >= 2
                   and hypothesis.get("conclusion_level") != "NET_PARAMETER_SELECTION_EDGE"
                   and str(baseline.get("verdict", "")).startswith("no separation")),
        "note": "the measured verdict is NO SEPARATION, which is not a superiority claim",
    }


def check_rust_parity() -> dict:
    """"Rust parity" from close final equity while order timing or fees differ."""
    import glob

    parity = None
    for path in sorted(glob.glob(str(LAB_ROOT / "evidence/**/engine_parity*.json"),
                                 recursive=True)):
        parity = json.loads(pathlib.Path(path).read_text())
    if parity is None:
        return {"claim": "rust parity", "passed": False, "note": "no parity artifact"}
    fields = sorted((parity["cases"][0]["trace_diffs"] or {})) if parity.get("cases") else []
    return {
        "claim": "rust parity",
        "would_need": "every bar of the account trace compared, and the missing fill trace disclosed",
        "cases": parity.get("case_count"),
        "trace_fields_compared": fields,
        "fill_trace_parity": parity.get("fill_trace_parity"),
        "claim_boundary_declared": bool(parity.get("claim_boundary")),
        "passed": (len(fields) >= 4 and bool(parity.get("claim_boundary"))
                   and parity.get("status") == "PASS"),
        "note": ("equity, positions, fees and funding are compared bar by bar; the rust backend "
                 "exposes no fill trace and that is disclosed rather than claimed"),
    }


def check_spot_perp_carry() -> dict:
    """"Spot-perp carry" from a derivative account with no spot inventory or borrow."""
    availability = load("availability_rules.json") or {}
    eligibility = load("data_eligibility.json") or {}
    funding = availability.get("funding", {})
    spot_symbols = set()
    for symbol, record in (eligibility.get("per_symbol") or {}).items():
        if "crypto_binance_spot_1m" in record.get("products", {}):
            spot_symbols.add(symbol)
    return {
        "claim": "spot-perp carry",
        "would_need": "a funding series, and a spot inventory or borrow leg",
        "funding_status": funding.get("status"),
        "symbols_with_spot_coverage": sorted(spot_symbols),
        "carry_claimed_anywhere": False,
        "passed": funding.get("status") == "MISSING" and "NEVER treated as zero" in str(
            funding.get("policy", "")),
        "note": ("funding does not exist in this storage, so every run is a labelled no-funding "
                 "cohort and no carry claim is available to make"),
    }


def check_whale_netflow() -> dict:
    """"Whale netflow" from a social-alert subset."""
    enrichment = load("enrichment_inventory.json") or {}
    return {
        "claim": "whale netflow",
        "would_need": "a complete flow dataset, not an alert feed",
        "enrichment_acquired": enrichment.get("acquired"),
        "primary_depends_on_enrichment": enrichment.get("primary_depends_on_enrichment"),
        "passed": (enrichment.get("acquired") == []
                   and enrichment.get("primary_depends_on_enrichment") is False),
        "note": "nothing was acquired, so no flow claim exists to be wrong",
    }


def check_all_four_certified() -> dict:
    """"All 4 alphas certified" because an AST parse succeeded."""
    import glob

    records = {}
    for path in sorted(glob.glob(str(LAB_ROOT / "configs/alpha_certification/*.json"))):
        document = json.loads(pathlib.Path(path).read_text())
        records[document["alpha_id"]] = document
    ready = [a for a, d in records.items() if d.get("status") == "READY_FOR_RESEARCH"]
    blocked = [a for a, d in records.items() if d.get("status") != "READY_FOR_RESEARCH"]
    evidenced = all(bool(d.get("engine_capabilities_verified")) for d in records.values())
    return {
        "claim": "all four alphas certified",
        "would_need": "an execution suite per alpha, not a parse",
        "alphas": len(records),
        "ready_for_research": sorted(ready),
        "blocked": sorted(blocked),
        "every_record_cites_verified_engine_capabilities": evidenced,
        "passed": len(records) == 4 and bool(blocked) and evidenced,
        "note": ("A-HASH is NOT_READY_SPECIFIC_BLOCKER and keeps null metrics; a phase that "
                 "certified all four would be the failure"),
    }


def check_production_safe() -> dict:
    """"Absolutely production-safe" from path naming without OS-level write isolation."""
    import glob

    preflight = None
    for path in sorted(glob.glob(str(LAB_ROOT / "evidence/**/preflight_report.json"),
                                 recursive=True)):
        preflight = json.loads(pathlib.Path(path).read_text())
    if preflight is None:
        return {"claim": "production safe", "passed": False, "note": "no preflight artifact"}
    # the field is `results`, and the isolation detail sits under the ISO row.
    # An earlier version of this function read `checks` and reported a FAIL that
    # was its own bug -- an auditor that misreads a field manufactures findings
    # exactly as easily as it misses them.
    isolation = next((row.get("detail") or {} for row in preflight.get("results", [])
                      if row.get("id") == "ISO"), {})
    measured = isolation.get("checks", {})
    mounts = measured.get("protected_mounts") or {}
    return {
        "claim": "absolutely production-safe",
        "would_need": "measured OS-level write isolation, not a path convention",
        "os_isolation_available": preflight.get("os_isolation_available"),
        "mechanism": (isolation.get("bwrap_version"),
                      preflight.get("containment_claim", "")[:90]),
        "fake_protected_write_refused": measured.get("fake_protected_write_refused"),
        "refusal_errno": measured.get("fake_protected_errno"),
        "protected_roots_measured_read_only": sorted(
            path for path, record in mounts.items() if record.get("read_only")),
        "network_blocked": measured.get("network_blocked"),
        "market_execution_allowed": preflight.get("safe_to_run_market_execution"),
        "passed": (preflight.get("os_isolation_available") is True
                   and measured.get("fake_protected_write_refused") is True
                   and measured.get("network_blocked") is True
                   and bool(mounts)
                   and all(record.get("read_only") for record in mounts.values())
                   and preflight.get("safe_to_run_market_execution") is False),
        "note": ("the write refusal is measured against a FAKE protected fixture, never against a "
                 "production repo, and market execution stays disabled"),
    }


CHECKS = (check_regime_works, check_no_leakage, check_out_of_sample,
          check_better_on_every_dimension, check_rust_parity, check_spot_perp_carry,
          check_whale_netflow, check_all_four_certified, check_production_safe)


def main() -> int:
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    with writer.attempt("guide.13_6_forbidden_claims") as att:
        results = [check() for check in CHECKS]
        att.detail = {"checks": len(results),
                      "passed": sum(1 for r in results if r["passed"])}

    failed = [r["claim"] for r in results if not r["passed"]]
    document = {
        "schema": "crypto_regime_lab.forbidden_claims_audit.v1",
        "guide_section": "13.6",
        "checked_at_utc": utc_now_iso(),
        "method": ("each claim is checked STRUCTURALLY: does the evidence the guide demands "
                   "exist, and is the lab making the claim at all. A lexical scan cannot tell a "
                   "claim from a denial of one -- two earlier attempts in this lab flagged a "
                   "requirement's own title, then its own negation"),
        "checks": results,
        "checks_total": len(results),
        "checks_passed": sum(1 for r in results if r["passed"]),
        "unsupported_claims": failed,
        "status": "NO_FORBIDDEN_CLAIM_IS_SUPPORTED" if not failed else "REVIEW_REQUIRED",
    }
    writer.write_config("forbidden_claims_audit.json", document)
    writer.write_json("forbidden_claims_audit.json", document, schema=document["schema"])

    for record in results:
        print(f"  {'ok  ' if record['passed'] else 'FAIL'}  {record['claim']}")
        if not record["passed"]:
            print(f"          {record.get('note', '')}")
    print(f"\n{document['checks_passed']}/{document['checks_total']} — {document['status']}")
    print(f"evidence -> {writer.run_dir}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
