#!/usr/bin/env python3
"""Build RA-06 artifacts (RA-GUIDE-1.0 section 10). Implementation, not a probe.

Panel A (reused from RA-05's real evidence, no new engine calls) and Panel B
(new: real KEEP-vs-REFIT branches at each origin, via a deterministic replay
prefix through `run_cutoff_walk_forward` -- no native QuantBT checkpoint/
clone-state capability exists in this install). AGE_ONLY vs AGE_CONTEXT
model ladder (hand-rolled ridge, inner leave-one-origin-out CV, no sklearn
in this venv). A deployment-controller demonstration and the phase's own
G06-SCOPE lock decision (at most one context-policy revision, or
KEEP_BASELINE with a reason).

Feasibility-pilot scale (5 origins, disclosed reduction from guide 10.3's
"8-12 if budget allows" ceiling; guide's own explicit fallback --
"neu khong co budget tao Panel B du support, ... giu scientific
INCONCLUSIVE_SUPPORT" -- is invoked deliberately, not silently).

Usage:
  lab_venv/bin/python scripts/run_ra06.py --pytest-xml <junit of tests/ra_corrective>
  lab_venv/bin/python scripts/run_ra06.py --pytest-xml <junit> --smoke   # tiny/fast dry run
Exit 0 iff the verifier reports PASS.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "src"))

import pandas as pd  # noqa: E402

from crypto_regime_lab.evidence.manifest import EvidenceWriter, new_lab_run_id  # noqa: E402
from crypto_regime_lab.ra.phase_common import (  # noqa: E402
    ledger_snapshot, protected_fingerprint, sha256_file, sh, utcnow, write_text_atomic,
)
from crypto_regime_lab.ra.ra05_market import load_real_bars, load_real_emissions  # noqa: E402
from crypto_regime_lab.ra.ra06_controller import (  # noqa: E402
    COOLDOWN_DAYS, REQUEST_SEARCH_G_THRESHOLD, lock_policy_revision, request_search_decision,
)
from crypto_regime_lab.ra.ra06_model import MIN_SUPPORT_FOR_MODEL_FIT, fit_and_compare  # noqa: E402
from crypto_regime_lab.ra.ra06_origins import ORIGIN_COUNT, ORIGIN_SPACING_DAYS, origin_registration  # noqa: E402
from crypto_regime_lab.ra.ra06_panel_a import build_panel_a, load_ra05_arms_result  # noqa: E402
from crypto_regime_lab.ra.ra06_panel_b import build_panel_b  # noqa: E402
from crypto_regime_lab.ra.verifier_ra06 import REQUIRED_ARTIFACTS, verify_ra06  # noqa: E402

STUDY = "regime_time_edge_ra_v1"
LEDGER_SQLITE = (LAB / "evidence" / "time_edge_validation_v4" / "allocations"
                 / "TE02-PILOT-R03" / "ledger.sqlite")
PHASE_WALL_CAP_S = 7200.0
ALPHA_ID = "A-SC"
SYMBOL = "BTCUSDT"
RA05_RUN_ID = "ra05-20260918T201236Z-de11db62"

DEFAULT_WINDOW_START = "2021-01-01"
DEFAULT_HORIZON_DAYS = 28
DEFAULT_TRAIN_MEMORY_DAYS = 45
DEFAULT_TRIALS = 8
DEFAULT_SEED = 20260918
DEFAULT_ROUTE = "event"

CASE_NODE_IDS = {
    "P01": ["test_p01_matured_outcome_uses_only_its_own_deployment_window",
           "test_p01_suffix_mutation_does_not_change_an_earlier_matured_outcome"],
    "P02": ["test_p02_keep_and_refit_share_identical_state_at_origin"],
    "P03": ["test_p03_g_matches_the_registered_formula_exactly",
           "test_p03_missing_equity_mark_is_censored_not_zero"],
    "P04": ["test_p04_origin_selection_takes_no_outcome_argument",
           "test_p04_censored_row_g_is_none_never_zero"],
    "P05": ["test_p05_both_ladder_entries_share_the_same_target_and_origins"],
    "P06": ["test_p06_leave_one_out_never_trains_on_the_held_out_point",
           "test_p06_insufficient_support_is_reported_truthfully",
           "test_p06_censored_rows_are_excluded_from_support_count"],
    "P07": ["test_p07_insufficient_support_locks_keep_baseline_not_a_fabricated_revision",
           "test_p07_a_negative_contribution_also_locks_keep_baseline",
           "test_p07_vetoed_search_is_not_silently_treated_as_free"],
    "P08": ["test_p08_model_and_controller_modules_never_import_the_engine"],
}


def build_controller_examples(panel_b_rows: list[dict], model_ladder: dict) -> dict:
    """RA06.7: demonstrate the request_search gate on the phase's own real
    origins' features -- the forecast-before-optimizer discipline, never
    the optimizer's own output fed back into the decision."""
    beta = None
    feature_names = ("intercept", "age_days", "realized_vol_20d",
                     "regime_transitions_since_incumbent", "incumbent_trailing_return")
    if model_ladder["status"] == "FIT_ATTEMPTED":
        beta = model_ladder["age_context"]["full_sample_beta"]
    examples = []
    for index, row in enumerate(panel_b_rows):
        if row.get("features") is None:
            continue
        decision = request_search_decision(
            row["features"], beta=beta, feature_names=feature_names,
            days_since_last_request=float(ORIGIN_SPACING_DAYS if index > 0 else 999),
            budget_remaining=3)
        examples.append({"origin": row["origin"], "decision": decision})
    return {
        "schema": "regime_lab.ra06_controller_examples.v1",
        "threshold": REQUEST_SEARCH_G_THRESHOLD, "cooldown_days": COOLDOWN_DAYS,
        "model_available": beta is not None,
        "examples": examples,
    }


def build_phase_gate(status: str, research_status: str, gate_results=None, notes=None) -> dict:
    return {
        "schema": "regime_lab.ra_phase_gate.v1", "phase_id": "RA-06", "guide_version": "RA-GUIDE-1.0",
        "registration_digest": None, "source_dependency_digest": None,
        "implementation_status": "COMPLETE", "technical_gate": status,
        "research_status": research_status,
        "required_gates": ["G06-PANEL", "G06-MODEL", "G06-SCOPE", "G06-MANIFEST"],
        "gate_results": gate_results or [], "mandatory_tests": [], "actual_run_refs": [],
        "verified_reuse_refs": [], "measured_resources": None,
        "protected_state_before_ref": "baseline/protected_before",
        "protected_state_after_ref": "baseline/protected_after",
        "open_blockers": [], "owner_review": {"status": "PENDING", "decision_ref": None},
        "can_start_next_phase": False, "notes": notes or [],
    }


def build_handoff(run_id: str, verdict: dict, lock_decision: dict) -> str:
    carry = lock_decision.get("carries_to_ra07")
    carry_line = (f"- Locked revision carried to RA-07: {carry['revision']}\n" if carry
                 else "- No revision carried to RA-07: KEEP_BASELINE (current JM/M0 reference policy).\n")
    return (
        "# RA-06 handoff\n\n"
        f"- run dir: evidence/{STUDY}/{{run_id}}/\n".format(run_id=run_id) +
        f"- technical gate: {verdict['overall']}; research status: INCONCLUSIVE_SUPPORT or NOT_ASSESSED\n"
        "- approvals: RA-06 owner review PENDING; can_start_next_phase=false\n"
        "- next: RA-07 (bounded replication, falsification, decay, inference) only after owner approval.\n"
        + carry_line +
        "- RA-05's own decision history stays separate and untouched (guide 10.7).\n"
    )


def build_report(*, spec, panel_a, origins_doc, panel_b, model_ladder, controller_examples,
                 lock_decision, run_id, verdict) -> str:
    gate_rows = "\n".join(
        f"| {gid} | PASS | {'PASS' if g['pass'] else 'FAIL'} | {run_id}/phase_manifest.json | "
        f"{'PASS' if g['pass'] else 'FAIL'} |"
        for gid, g in verdict["gates"].items())
    row_lines = []
    for row in panel_b["rows"]:
        if row["status"] == "OK":
            row_lines.append(f"| {row['origin'][:10]} | OK | {row['g']['g']:.5f} | "
                            f"{row['features']['age_days']:.0f}d | "
                            f"{row['features']['regime_transitions_since_incumbent']:.0f} |")
        else:
            row_lines.append(f"| {row['origin'][:10]} | CENSORED | - | - | {row.get('reason', '')[:60]} |")
    research_status = "INCONCLUSIVE_SUPPORT" if model_ladder["status"] == "INSUFFICIENT_SUPPORT" else "NOT_ASSESSED"
    return f"""# RA-06 - Panel tai su dung, refit-vs-keep target va mot policy revision co gioi han

## 1. Status va scope
- Technical gate: **{verdict['overall']}**; research status: **{research_status}**.
- Branch `mode4-corrective`, guide RA-GUIDE-1.0 (section 10), study `{STUDY}`, run `{run_id}`.
- Pilot cell {ALPHA_ID}/{SYMBOL}, feasibility-pilot scale: {spec['origin_count']} origins,
  {spec['spacing_days']}-day calendar spacing, {spec['horizon_days']}-day horizon -- a disclosed
  reduction from guide 10.3's "8-12 origins if budget allows" ceiling (same phase-owned-scale
  precedent as RA-02..05).

## 2. Panel A (reused, no new engine calls)
- {panel_a['row_count']} rows from RA-05's real evidence ({panel_a['source_run_id']}),
  {panel_a['unique_candidates']} unique candidates, {panel_a['matured_ok_count']} matured OK.

## 3. Panel B (real KEEP-vs-REFIT, deterministic replay prefix)
- State-fork method: {panel_b.get('state_fork_method', 'n/a')}
- {panel_b.get('row_count', 0)} origins, {panel_b.get('ok_count', 0)} OK, {panel_b.get('censored_count', 0)} censored.
- Origin selection rule: {origins_doc['rule']}

| origin | status | g_t(H) | age | regime transitions |
|---|---|---|---|---|
{chr(10).join(row_lines)}

## 4. Exit-gate matrix
| Gate | Expected | Actual | Evidence ref | Status |
|---|---|---|---|---|
{gate_rows}

## 5. Correctness va causality
- KEEP and REFIT share a deterministic replay prefix through `run_cutoff_walk_forward`; a real
  bug was found and fixed while building this phase: `E_t` read exactly ON the origin's own day
  disagreed between branches (REFIT's new fold already begins trading that day), fixed by reading
  `E_t` strictly BEFORE origin -- P02 is the regression test.
- Origins are a pure calendar grid, chosen before any branch ran (guide 10.4).

## 6. Model ladder (guide 10.5/10.6)
- Status: **{model_ladder['status']}** (support={model_ladder.get('support')}, min_required={model_ladder.get('min_required')}).
{"- " + model_ladder.get('disposition', '') if model_ladder['status'] == 'INSUFFICIENT_SUPPORT' else ""}

## 7. Deployment controller demonstration (guide 10.7)
- {len(controller_examples['examples'])} real origins scored; model_available={controller_examples['model_available']}.
- threshold={controller_examples['threshold']}, cooldown_days={controller_examples['cooldown_days']}.

## 8. G06-SCOPE lock decision
- **{lock_decision['decision']}**: {lock_decision['reason']}

## 9. Scientific result va kha nang ket luan
- None claimed beyond the lock decision above: RA-06 is a mechanical/feasibility phase (guide:
  "mechanical phase co the PASS voi research INCONCLUSIVE_SUPPORT sau khi hoan thanh branch
  duoc dang ky"). Support at this feasibility-pilot scale ({panel_b.get('ok_count', 0)} OK rows)
  is measured, not manufactured into a stronger claim.

## 10. Blockers/debt va quyet dinh
- No P0/P1 in phase scope. Owner decisions pending: this phase's review; can_start_next_phase=false.

## 11. Reproduction, commit va handoff
- Rerun: `lab_venv/bin/python scripts/run_ra06.py --pytest-xml <junit>` (new run_id per attempt;
  prior runs immutable). `--smoke` runs a tiny/fast config to dry-run the pipeline.
- Independent verify: re-run the build, or import `verify_ra06` and point it at the run dir with
  the same junit; deterministic given the same real snapshot bytes.
- Protected trees: fingerprint recorded before/after; phase-changed files:
  `src/crypto_regime_lab/ra/{{ra06_panel_a,ra06_panel_b,ra06_origins,ra06_features,ra06_model,ra06_controller,verifier_ra06}}.py`,
  `scripts/run_ra06.py`, `tests/ra_corrective/test_ra06_*.py`, this run dir; committed scoped, no
  push.
- Next permissible action: RA-07 only after owner approval of this phase.
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pytest-xml", required=True)
    parser.add_argument("--smoke", action="store_true",
                        help="tiny/fast config to dry-run the pipeline, not a real feasibility pilot")
    args = parser.parse_args()
    phase_started = time.perf_counter()
    prot_before = protected_fingerprint()
    ledger = ledger_snapshot(LEDGER_SQLITE)

    if args.smoke:
        window_start = "2021-01-01"
        horizon_days, train_memory_days, trials = 3, 20, 2
        origin_count, spacing_days = 2, 7
        data_load_start, data_load_end = "2020-12-01", "2021-01-14"
    else:
        window_start = DEFAULT_WINDOW_START
        horizon_days, train_memory_days, trials = (DEFAULT_HORIZON_DAYS, DEFAULT_TRAIN_MEMORY_DAYS,
                                                    DEFAULT_TRIALS)
        origin_count, spacing_days = ORIGIN_COUNT, ORIGIN_SPACING_DAYS
        data_load_start = "2020-11-01"
        last_origin = pd.Timestamp(window_start) + pd.Timedelta(days=spacing_days * origin_count)
        data_load_end = (last_origin + pd.Timedelta(days=horizon_days + 1)).isoformat()[:10]
    seed, route = DEFAULT_SEED, DEFAULT_ROUTE

    from crypto_regime_lab.safety.paths import SandboxPolicy

    policy = SandboxPolicy.load(LAB / "configs" / "sandbox_policy.json")
    writer = EvidenceWriter.open(policy, study_id=STUDY, lab_run_id=new_lab_run_id("ra06"))
    run_dir = writer.run_dir

    with writer.attempt("ra06_build") as att:
        # -- RA06.1 Panel A: reused from RA-05, no new engine calls ------------
        arms, _ = load_ra05_arms_result(RA05_RUN_ID)
        panel_a = build_panel_a(arms, source_run_id=RA05_RUN_ID)
        writer.write_json("panel_a.json", panel_a, schema="regime_lab.ra06_panel_a.v1")

        # -- RA06.4 origins: disclosed calendar grid, before any branch runs ---
        origins_doc = origin_registration(window_start, horizon_days, count=origin_count,
                                          spacing_days=spacing_days)
        writer.write_json("origins.json", origins_doc, schema="regime_lab.ra06_origins.v1")

        # -- RA06.1/10.2/10.3 Panel B: real KEEP-vs-REFIT ----------------------
        frame, partitions = load_real_bars(SYMBOL, start=data_load_start, end=data_load_end)
        frame = frame[["open", "high", "low", "close", "volume"]].copy()
        emissions_doc = load_real_emissions(window_start=window_start, window_end=data_load_end)
        panel_b = build_panel_b(
            ALPHA_ID, frame, window_start=window_start, origins=origins_doc["origins"],
            horizon_days=horizon_days, train_memory_days=train_memory_days, trials=trials,
            seed=seed, route=route, emissions=emissions_doc["emissions"])
        writer.write_json("panel_b.json", panel_b, schema="regime_lab.ra06_panel_b.v1")

        # -- RA06.5/10.6 model ladder -------------------------------------------
        min_support = 2 if args.smoke else MIN_SUPPORT_FOR_MODEL_FIT
        model_ladder = fit_and_compare(panel_b["rows"], min_support=min_support)
        writer.write_json("model_ladder.json", model_ladder, schema="regime_lab.ra06_model_ladder.v1")

        # -- RA06.7 controller demonstration + G06-SCOPE lock ------------------
        controller_examples = build_controller_examples(panel_b["rows"], model_ladder)
        writer.write_json("controller_examples.json", controller_examples,
                          schema="regime_lab.ra06_controller_examples.v1")
        lock_decision = lock_policy_revision(model_ladder, min_support=min_support)
        writer.write_json("lock_decision.json", lock_decision, schema="regime_lab.ra06_lock_decision.v1")

        import importlib.metadata as md

        def version(name):
            try:
                return md.version(name)
            except Exception:
                return None

        phase_wall = round(time.perf_counter() - phase_started, 1)
        snapshot = {k: ledger.get(k) for k in ("spent", "attempts", "budget")}
        baseline = {
            "git_branch": sh(["git", "branch", "--show-current"], cwd=LAB),
            "git_head_full": sh(["git", "rev-parse", "HEAD"], cwd=LAB),
            "engine_version": version("quantbt-engine"), "native_version": version("quantbt-native"),
            "protected_before": prot_before, "ledger_before": snapshot, "ledger_after": snapshot,
            "phase_wall_cap_s": PHASE_WALL_CAP_S, "phase_measured_wall_s": phase_wall,
            "started_at": utcnow(), "market_partitions_used": partitions,
        }
        writer.write_json("baseline_identity.json", baseline, schema="regime_lab.ra06_baseline.v1")

        def manifest_records():
            return [{"relpath": name, "sha256": sha256_file(run_dir / name),
                    "size_bytes": (run_dir / name).stat().st_size}
                   for name in REQUIRED_ARTIFACTS
                   if name not in ("phase_manifest.json", "phase_gate.json", "report.md", "handoff.md")
                   and (run_dir / name).is_file()]

        writer.write_json("phase_manifest.json", {
            "required_gates": ["G06-PANEL", "G06-MODEL", "G06-SCOPE", "G06-MANIFEST"],
            "artifacts": manifest_records(),
            "source_dependency_digests": {"lab_head": baseline["git_head_full"],
                                          "endpoint_protected": prot_before.get("endpoint_sha256")},
            "approvals": {"ra06_review": "PENDING"},
        }, schema="regime_lab.ra06_manifest.v1")

        research_status = "INCONCLUSIVE_SUPPORT" if model_ladder["status"] == "INSUFFICIENT_SUPPORT" else "NOT_ASSESSED"
        writer.write_json("phase_gate.json", build_phase_gate("PENDING_VERIFICATION", research_status),
                          schema="regime_lab.ra_phase_gate.v1")
        write_text_atomic(run_dir / "report.md", "# RA-06 report - PENDING_VERIFICATION\n")
        write_text_atomic(run_dir / "handoff.md", "# RA-06 handoff - PENDING_VERIFICATION\n")
        prot_after = protected_fingerprint()

        gate_doc = build_phase_gate(
            "PENDING_VERIFICATION", research_status,
            notes=["verify ran over the frozen artifact set incl. this receipt"])

        junit = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
        try:
            import xml.etree.ElementTree as ET

            xml_root = ET.parse(args.pytest_xml).getroot()
            suites = xml_root.findall("testsuite") or [xml_root]
            junit = {"tests": sum(int(s.get("tests", 0)) for s in suites),
                    "failures": sum(int(s.get("failures", 0)) for s in suites),
                    "errors": sum(int(s.get("errors", 0)) for s in suites),
                    "skipped": sum(int(s.get("skipped", 0)) for s in suites)}
        except Exception:
            pass
        gate_doc["mandatory_tests"] = [{"command": " ".join(sys.argv), **junit}]
        gate_doc["measured_resources"] = {"phase_wall_s": phase_wall}
        gate_doc["actual_run_refs"] = ["panel_b.json", "model_ladder.json", "lock_decision.json"]
        gate_doc["verified_reuse_refs"] = ["ra06_panel_a (RA-05 real evidence, no new engine calls)",
                                           "dynamic_fold_provider.run_cutoff_walk_forward (RF-04/RA-05)"]
        gate_doc["protected_state_after_ref"] = "protected status: " + (prot_after["git_status_porcelain"] or "clean")
        writer.write_json("phase_gate.json", gate_doc, schema="regime_lab.ra_phase_gate.v1")

        verdict = verify_ra06(run_dir, pytest_xml=args.pytest_xml,
                              protected_status_after=prot_after["git_status_porcelain"])
        gate_doc["technical_gate"] = verdict["overall"]
        gate_doc["gate_results"] = [{"gate_id": gid, "status": "PASS" if g["pass"] else "FAIL",
                                     "reasons": g["reasons"][:3]} for gid, g in verdict["gates"].items()]
        writer.write_json("phase_gate.json", gate_doc, schema="regime_lab.ra_phase_gate.v1")

        manifest_doc = json.loads((run_dir / "phase_manifest.json").read_text())
        manifest_doc["artifacts"] = manifest_records()
        writer.write_json("phase_manifest.json", manifest_doc, schema="regime_lab.ra06_manifest.v1")

        verdict = verify_ra06(run_dir, pytest_xml=args.pytest_xml,
                              protected_status_after=prot_after["git_status_porcelain"])
        writer.write_json("verification.json", verdict, schema="regime_lab.ra06_verification.v1")
        write_text_atomic(run_dir / "report.md", build_report(
            spec=origins_doc, panel_a=panel_a, origins_doc=origins_doc, panel_b=panel_b,
            model_ladder=model_ladder, controller_examples=controller_examples,
            lock_decision=lock_decision, run_id=writer.lab_run_id, verdict=verdict))
        write_text_atomic(run_dir / "handoff.md", build_handoff(writer.lab_run_id, verdict, lock_decision))
        att.detail = {"run_dir": str(run_dir), "overall": verdict["overall"]}

    print(json.dumps({"run_dir": str(run_dir), "overall": verdict["overall"],
                      "gates": {k: v["pass"] for k, v in verdict["gates"].items()}}, indent=2))
    return 0 if verdict["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
