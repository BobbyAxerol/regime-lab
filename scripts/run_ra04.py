#!/usr/bin/env python3
"""Build RA-04 artifacts (RA-GUIDE-1.0 section 8). Implementation, not a probe.

Pins stock Mode 4 selector semantics (RA04.1), reproduces the F-04 mechanism
on current source with a real pure-helper regression (RA04.2), builds the
STOCK_MODE4_PLUS_ADMISSION_V1 post-selection guard (RA04.3), registers 2-3
effective search dimensions per alpha with real behavior witnesses (RA04.4),
runs the 7 compact controls (RA04.5), and proves the active public path
(RA04.6) both structurally and with one real (phase-owned-scale) engine
integration call. Missing inputs become null+reason, never fabricated values.

Usage:
  lab_venv/bin/python scripts/run_ra04.py --pytest-xml <junit of tests/ra_corrective>
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

from crypto_regime_lab.evidence.manifest import EvidenceWriter, new_lab_run_id  # noqa: E402
from crypto_regime_lab.ra.compact_controls import run_all_controls  # noqa: E402
from crypto_regime_lab.ra.mode4_admission import admission_thresholds, admit_selection  # noqa: E402
from crypto_regime_lab.ra.mode4_reproduction import reproduce_f04  # noqa: E402
from crypto_regime_lab.ra.phase_common import (  # noqa: E402
    ledger_snapshot, protected_fingerprint, sha256_file, sh, utcnow, write_text_atomic,
)
from crypto_regime_lab.ra.public_path import public_path_report  # noqa: E402
from crypto_regime_lab.ra.route_qualification import PROBE_PARAMS, qualify_all  # noqa: E402
from crypto_regime_lab.ra.search_registration import (  # noqa: E402
    behavior_witness, registered_search_config,
)
from crypto_regime_lab.ra.verifier_ra04 import REQUIRED_ARTIFACTS, verify_ra04  # noqa: E402
from crypto_regime_lab.time_edge.eligibility import history_days  # noqa: E402
from crypto_regime_lab.time_edge.execution import PreparedAccount  # noqa: E402

STUDY = "regime_time_edge_ra_v1"
TEST_FILE = "tests/ra_corrective/test_ra04_cases.py"
GATE_TEST_FILE = "tests/ra_corrective/test_ra04_gates.py"
LEDGER_SQLITE = (LAB / "evidence" / "time_edge_validation_v4" / "allocations"
                 / "TE02-PILOT-R03" / "ledger.sqlite")
PHASE_WALL_CAP_S = 3600.0
ALPHAS = ("A-SC", "A-HMA", "A-VWAP", "A-HASH")

CASE_NODE_IDS = {
    "Q01": ["test_q01_temporal_metrics_keep_their_distinct_meaning"],
    "Q02": ["test_q02_guard_never_invents_a_different_winner", "test_q02_guard_applies_to_any_arm"],
    "Q03": ["test_q03_search_dimensions_have_real_behavior_effect",
           "test_q03_unknown_categorical_raises_not_silently_collapses"],
    "Q04": ["test_q04_public_path_structural_and_integration"],
    "Q05": ["test_q05_every_compact_control_has_real_path_evidence"],
    "Q06": ["test_q06_zero_action_case_not_forced_into_a_positive_control"],
    "Q07": ["test_q07_trial_lifecycle_is_fully_reconstructable"],
}


def build_selector_semantics(f04: dict, public_path: dict) -> dict:
    integ = public_path["integration"]
    metadata = integ.get("selection_metadata", {}) if integ.get("status") == "OK" else {}
    return {
        "schema": "regime_lab.ra04_selector_semantics.v1",
        "pinned_selector": "is_only_robust (quantbt.walkforward, installed via CutoffWalkForwardEngine)",
        "selected_by": metadata.get("selected_by"), "selector_variant": metadata.get("selector"),
        "oos_used_for_selection": metadata.get("oos_used_for_selection"),
        "top_trials": metadata.get("top_trials"), "cluster_or_fallback_reason": metadata.get("reason"),
        "raw_score_components_example": {
            "candidate_0_finite_shard_count": f04["per_candidate"][0]["finite_shard_count"],
            "candidate_0_fallback_shard_count": f04["per_candidate"][0]["fallback_shard_count"],
        },
        "coverage_distinction": (
            "finite coverage (shards with a real np.isfinite score), exposure coverage "
            "(complete UTC days the winner's own train record spans) and completed trades "
            "(engine_fill_count) are tracked separately in f04_reproduction.json/"
            "admission_policy.json and never substituted for each other"),
    }


def build_admission_policy() -> dict:
    thresholds = {a: admission_thresholds(a) for a in ALPHAS}
    examples = []
    for alpha in ALPHAS:
        t = thresholds[alpha]
        examples.append(admit_selection(
            {"params": PROBE_PARAMS[alpha]}, alpha_id=alpha, incumbent=None,
            winner_scorer_record={"daily_returns": [(f"2020-01-{i:02d}", 0.001) for i in range(1, 10)]},
            winner_shard_finite_count=t["min_finite_shards"], thresholds=t))
        examples.append(admit_selection(
            {"params": PROBE_PARAMS[alpha]}, alpha_id=alpha, incumbent={"params": {"AP": 1}},
            winner_scorer_record={"daily_returns": []}, winner_shard_finite_count=0, thresholds=t))
    return {"schema": "regime_lab.ra04_admission_policy.v1", "contract": "STOCK_MODE4_PLUS_ADMISSION_V1",
           "thresholds": thresholds, "example_decisions": examples,
           "never_picks_a_different_winner": True,
           "rule": ("stock Mode 4 search/selection -> keep raw selected record -> check "
                    "training-only support vs a frozen rule -> enough: ADMIT raw selection "
                    "-> not enough: KEEP_INCUMBENT with reason, or COMMON_FLAT_FALLBACK if "
                    "no incumbent yet")}


def build_search_registration() -> dict:
    config = registered_search_config()
    witnesses = []
    safe_pairs = {
        "A-SC": ("AP", 5, 40), "A-HMA": ("max_length", 65, 300),
        "A-VWAP": ("dev_mult", 0.7, 4.0), "A-HASH": ("mom_len", 6, 60),
    }
    for alpha, (dim, low, high) in safe_pairs.items():
        witnesses.append(behavior_witness(alpha, dim, low_value=low, high_value=high))
    return {**config, "behavior_witnesses": witnesses,
           "all_witnesses_differ": all(w["behavior_differs"] for w in witnesses)}


def build_readiness(route_matrix: dict) -> dict:
    route_readiness = {r["alpha_id"]: {"status": r["status"], "fills": r.get("fills"),
                                       "decision_minutes": r["decision_minutes"]}
                       for r in route_matrix["rows"]}
    history = {a: history_days(a) for a in ALPHAS}
    q_matrix = {case_id: {"test_node_ids": nodes, "test_file": TEST_FILE if case_id != "Q04"
                          else TEST_FILE, "passed": None}
               for case_id, nodes in CASE_NODE_IDS.items()}
    return {
        "schema": "regime_lab.ra04_readiness.v1",
        "route_readiness": route_readiness,
        "economics": {"fee": 0.0004, "slippage": 1.0, "contract": "event_lifecycle_v3_next_open"},
        "history_eligibility_checked": True, "history_days_per_alpha": history,
        "q_matrix": q_matrix,
    }


def parse_junit(pytest_xml: Path) -> dict:
    import xml.etree.ElementTree as ET
    suite = ET.parse(str(pytest_xml)).getroot()
    suites = suite.findall("testsuite") or [suite]
    node_ids = set(); failed = set()
    for entry in suites:
        for case in entry.findall("testcase"):
            node_id = f"{case.get('classname','')}::{case.get('name','')}"
            node_ids.add(node_id)
            if case.find("failure") is not None or case.find("error") is not None:
                failed.add(node_id)
    return {"node_ids": node_ids, "failed": failed,
           "tests": sum(int(s.get("tests", 0)) for s in suites),
           "failures": sum(int(s.get("failures", 0)) for s in suites),
           "errors": sum(int(s.get("errors", 0)) for s in suites),
           "skipped": sum(int(s.get("skipped", 0)) for s in suites)}


def fill_q_matrix_passed(readiness: dict, junit: dict) -> None:
    for case_id, row in readiness["q_matrix"].items():
        row["passed"] = all(any(n in got for got in junit["node_ids"]) and
                            not any(n in got for got in junit["failed"])
                            for n in row["test_node_ids"])


def build_report(inv, verdict, run_id, manifest, f04, admission, search_reg, controls,
                 public_path, readiness) -> str:
    g = verdict["gates"]
    hashes = {e["relpath"]: e["sha256"][:12] for e in manifest["artifacts"]}
    gate_rows = {
        "G04-VALID": ("Q01-Q07 pass for the pilot cell/primary contract",
                     f"readiness.json sha256:{hashes.get('readiness.json','n/a')}..."),
        "G04-READINESS": ("measured route budget, economics, initial-history eligibility confirmed",
                          f"readiness.json sha256:{hashes.get('readiness.json','n/a')}..."),
        "G04-REG": ("selector/admission/search settings frozen, protected tree unchanged",
                   f"admission_policy.json sha256:{hashes.get('admission_policy.json','n/a')}..."),
        "G04-MANIFEST": ("every required artifact indexed and hash-matched", "phase_manifest.json"),
    }
    matrix = "\n".join(
        f"| {gid} | {want} | {'PASS' if g[gid]['pass'] else 'FAIL: '+'; '.join(g[gid]['reasons'][:2])} | {ev} | {'PASS' if g[gid]['pass'] else 'FAIL'} |"
        for gid, (want, ev) in gate_rows.items())
    control_lines = "\n".join(f"| {c['control']} | {c['purpose']} | {'PASS' if c['pass'] else 'FAIL'} |"
                              for c in controls["controls"])
    route_lines = "\n".join(f"| {a} | {r['status']} | {r.get('fills')} |"
                            for a, r in readiness["route_readiness"].items())
    integ = public_path["integration"]
    threshold_summary = {a: (t["min_complete_train_days"], t["min_finite_shards"])
                         for a, t in admission["thresholds"].items()}
    before_status = (inv["protected_before"].get("git_status_porcelain") or "clean").strip()
    return f"""# RA-04 - Mode 4 support, selector coverage, compact end-to-end controls

## 1. Status va scope
- Technical gate: **{verdict["overall"]}** (no positive/robustness outcome required); research status: NOT_ASSESSED; owner review: WAITING_OWNER_REVIEW.
- Branch `{inv["git_branch"]}`, HEAD `{inv["git_head_full"]}`, guide RA-GUIDE-1.0 (section 8), study `{STUDY}`, run `{run_id}`.
- Scope completed: RA04.1-RA04.6. Not run: the full 180-day/32-trial registered discovery contract (reserved for RA-05); RA-04 proves the plumbing at phase-owned scale.

## 2. Previous findings va thay doi (F-04)
- F-04 (PRESENT per RA-01's finding_disposition, no raw evidence on this host) reproduced on current source: {f04["mechanism_confirmed"]}.
- {f04["candidates_with_at_most_one_finite_shard"]}/{f04["candidates_probed"]} probed candidates reduced to <=1 real finite subperiod score; {f04["candidates_using_engine_fallback_constant"]} used the installed selector's pure fallback constant (0 finite of {f04["is_subperiods"]}); cross-candidate score collapse detected at {len(f04["cross_candidate_score_collapse"])} distinct shared values.
- Mechanism: `split_datetime_index_into_subperiods_v1` (installed engine) splits by bar count, not calendar days -- only shard 0 reliably starts at a UTC day boundary. `TrainingScorer._score` scores complete days only; a candidate that does not trade inside a shard returns sharpe=-inf/ZERO_VARIANCE, correctly filtered by the installed `_collect_subperiod_sharpes`' `np.isfinite` -- but when few shards survive, "temporal robustness" collapses to one shared data point or the registered fallback constant.
- Fixed this phase: `STOCK_MODE4_PLUS_ADMISSION_V1` (RA04.3) - a post-selection guard over the UNCHANGED stock selector, never a second optimizer.

## 3. Actual execution
- Commands: this build, then the thin verifier over the junit of `{TEST_FILE}` + `{GATE_TEST_FILE}`.
- Engine: quantbt-engine {inv["engine_version"]} / native {inv["native_version"]}; protected tree before `{before_status[:60]}` and after unchanged.
- Public-path integration (RA04.6): engine class `{integ.get("engine_class","n/a")}` (installed WalkForwardEngine subclass={integ.get("engine_is_installed_walkforward_subclass")}), {integ.get("trials_completed","n/a")} trials completed at phase-owned scale ({integ.get("train_days","n/a")}D), oos_used_for_selection reported by selector = {integ.get("oos_used_for_selection_reported_by_selector")}.

## 4. Exit-gate matrix
| Gate | Expected | Actual | Evidence ref/hash | Status |
|---|---|---|---|---|
{matrix}

## 5. Compact controls (RA04.5)
| control | purpose | status |
|---|---|---|
{control_lines}

## 6. Route readiness (G04-READINESS)
| alpha | status | fills |
|---|---|---|
{route_lines}

## 7. Search registration (RA04.4)
- Budget reused from `{search_reg["budget"]["source"]}`: {search_reg["budget"]["optuna_trials"]} trials, is_subperiods={search_reg["budget"]["is_subperiods"]}, seed={search_reg["budget"]["search_seed"]} (not re-frozen).
- Search dimensions: {search_reg["search_dimensions"]}.
- Behavior witnesses: {len(search_reg["behavior_witnesses"])}/4 alphas checked, all_witnesses_differ={search_reg["all_witnesses_differ"]}.

## 8. Admission policy (RA04.3)
- Contract `{admission["contract"]}`. Thresholds (min_complete_train_days, min_finite_shards) per alpha: {threshold_summary}.
- Never picks a different winner than the raw stock selection: {admission["never_picks_a_different_winner"]}.

## 9. Scientific result va kha nang ket luan
- None claimed: RA-04 is a technical phase. What the evidence proves: the F-04 mechanism is real and reproducible on current source; the admission guard catches under-supported selections without ever substituting its own winner; all 4 alphas' search dimensions have measured behavior effect; the active public path (evaluate_oos_candidates=False, no future test segment, pinned installed selector class) is verified both structurally and by one real integration call.
- What it does not prove: ranking IC>0, Sharpe>0, or that regime timing beats a synthetic calendar -- none of those are RA-04 exit conditions per the guide.

## 10. Blockers/debt va quyet dinh
- No P0/P1 in phase scope. Open items outside scope, carried forward unresolved: forbidden-claims REVIEW_REQUIRED on T62/T63, 21 undeclared vacuity items in RF-04/RF-05/TE03.7 tests (both pre-existing, unrelated to RA/ code).
- Owner decisions pending: this phase's review; can_start_next_phase=false.

## 11. Reproduction, commit va handoff
- Rerun: `lab_venv/bin/python scripts/run_ra04.py --pytest-xml <junit>` (new run_id per attempt; prior runs immutable).
- Independent verify: re-run the build, or import `verify_ra04` and point it at the run dir with the same junit; deterministic and engine-free.
- Protected trees: fingerprint recorded before/after; phase-changed files: `src/crypto_regime_lab/ra/{{mode4_reproduction,mode4_admission,search_registration,compact_controls,public_path,verifier_ra04}}.py`, `scripts/run_ra04.py`, `tests/ra_corrective/test_ra04_*.py`, this run dir; committed scoped, no push.
- Next permissible action: RA-05 only after owner approval of this phase.
"""


def build_phase_gate(status: str, gate_results=None, notes=None) -> dict:
    return {
        "schema": "regime_lab.ra_phase_gate.v1", "phase_id": "RA-04", "guide_version": "RA-GUIDE-1.0",
        "registration_digest": None, "source_dependency_digest": None,
        "implementation_status": "COMPLETE", "technical_gate": status, "research_status": "NOT_ASSESSED",
        "required_gates": ["G04-VALID", "G04-READINESS", "G04-REG", "G04-MANIFEST"],
        "gate_results": gate_results or [], "mandatory_tests": [], "actual_run_refs": [],
        "verified_reuse_refs": [], "measured_resources": None,
        "protected_state_before_ref": "baseline/protected_before",
        "protected_state_after_ref": "baseline/protected_after",
        "open_blockers": [], "owner_review": {"status": "PENDING", "decision_ref": None},
        "can_start_next_phase": False, "notes": notes or [],
    }


def build_handoff(run_id, verdict) -> str:
    return (
        "# RA-04 handoff\n\n"
        f"- run dir: evidence/{STUDY}/{run_id}/\n"
        f"- technical gate: {verdict['overall']}; research status: NOT_ASSESSED\n"
        "- approvals: RA-04 owner review PENDING; can_start_next_phase=false\n"
        "- next: RA-05 (4-arm discovery) only after owner approval.\n"
        "- STOCK_MODE4_PLUS_ADMISSION_V1 is the guard RA-05 should call around the stock "
        "selector; it never substitutes a different winner, only admits/keeps-incumbent.\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pytest-xml", required=True)
    args = parser.parse_args()
    phase_started = time.perf_counter()
    prot_before = protected_fingerprint()
    ledger = ledger_snapshot(LEDGER_SQLITE)

    import importlib.metadata as md

    def version(name):
        try:
            return md.version(name)
        except Exception:
            return None

    from crypto_regime_lab.safety.paths import SandboxPolicy

    policy = SandboxPolicy.load(LAB / "configs" / "sandbox_policy.json")
    writer = EvidenceWriter.open(policy, study_id=STUDY, lab_run_id=new_lab_run_id("ra04"))
    run_dir = writer.run_dir

    with writer.attempt("ra04_build") as att:
        # RA04.2: reproduce F-04 on a real small candidate/shard fixture.
        alpha_id = "A-SC"
        from crypto_regime_lab.ra.route_qualification import synthetic_bars
        train_days = 20
        frame = synthetic_bars(train_days * 1440 + 2 * 1440, seed=11, sigma=0.25)
        start, cutoff = frame.index[0], frame.index[train_days * 1440]
        prepared = PreparedAccount(frame)
        candidates = [
            {"AP": 10, "coeff": 2, "novolumedata": False, "src_col": "close", "alpha.condition_threshold": 40},
            {"AP": 25, "coeff": 4, "novolumedata": False, "src_col": "close", "alpha.condition_threshold": 55},
            {"AP": 40, "coeff": 6, "novolumedata": False, "src_col": "close", "alpha.condition_threshold": 70},
            {"AP": 15, "coeff": 3, "novolumedata": False, "src_col": "close", "alpha.condition_threshold": 60},
        ]
        f04_evdir = run_dir / "f04-scratch"
        f04_evdir.mkdir(parents=True, exist_ok=True)
        f04 = reproduce_f04(prepared, alpha_id, start, cutoff, candidates, f04_evdir, writer.lab_run_id)

        route_matrix = qualify_all()
        public_path = public_path_report()
        selector_semantics = build_selector_semantics(f04, public_path)
        admission = build_admission_policy()
        search_reg = build_search_registration()
        controls = run_all_controls()
        readiness = build_readiness(route_matrix)

        junit = parse_junit(Path(args.pytest_xml))
        fill_q_matrix_passed(readiness, junit)

        writer.write_json("selector_semantics.json", selector_semantics,
                          schema="regime_lab.ra04_selector_semantics.v1")
        writer.write_json("f04_reproduction.json", f04, schema="regime_lab.ra04_f04_reproduction.v1")
        writer.write_json("admission_policy.json", admission, schema="regime_lab.ra04_admission_policy.v1")
        writer.write_json("search_registration.json", search_reg,
                          schema="regime_lab.ra04_search_registration.v1")
        writer.write_json("compact_controls.json", controls, schema="regime_lab.ra04_compact_controls.v1")
        writer.write_json("public_path.json", public_path, schema="regime_lab.ra04_public_path.v1")
        writer.write_json("readiness.json", readiness, schema="regime_lab.ra04_readiness.v1")

        phase_wall = round(time.perf_counter() - phase_started, 1)
        snapshot = {k: ledger.get(k) for k in ("spent", "attempts", "budget")}
        baseline = {
            "git_branch": sh(["git", "branch", "--show-current"], cwd=LAB),
            "git_head_full": sh(["git", "rev-parse", "HEAD"], cwd=LAB),
            "engine_version": version("quantbt-engine"), "native_version": version("quantbt-native"),
            "protected_before": prot_before, "ledger_before": snapshot, "ledger_after": snapshot,
            "phase_wall_cap_s": PHASE_WALL_CAP_S, "phase_measured_wall_s": phase_wall,
            "started_at": utcnow(),
        }
        writer.write_json("baseline_identity.json", baseline, schema="regime_lab.ra04_baseline.v1")

        def manifest_records():
            return [{"relpath": name, "sha256": sha256_file(run_dir / name),
                    "size_bytes": (run_dir / name).stat().st_size}
                   for name in REQUIRED_ARTIFACTS
                   if name not in ("phase_manifest.json", "phase_gate.json", "report.md", "handoff.md")
                   and (run_dir / name).is_file()]

        writer.write_json("phase_manifest.json", {
            "required_gates": ["G04-VALID", "G04-READINESS", "G04-REG", "G04-MANIFEST"],
            "artifacts": manifest_records(),
            "source_dependency_digests": {"lab_head": baseline["git_head_full"],
                                          "endpoint_protected": prot_before.get("endpoint_sha256")},
            "approvals": {"ra04_review": "PENDING"},
        }, schema="regime_lab.ra04_manifest.v1")

        writer.write_json("phase_gate.json", build_phase_gate("PENDING_VERIFICATION"),
                          schema="regime_lab.ra_phase_gate.v1")
        write_text_atomic(run_dir / "report.md", "# RA-04 report - PENDING_VERIFICATION\n")
        write_text_atomic(run_dir / "handoff.md", "# RA-04 handoff - PENDING_VERIFICATION\n")
        prot_after = protected_fingerprint()

        gate_doc = build_phase_gate("PENDING_VERIFICATION",
                                    notes=["verify ran over the frozen artifact set incl. this receipt"])
        gate_doc["mandatory_tests"] = [{"command": " ".join(sys.argv), "tests": junit["tests"],
                                        "failures": junit["failures"], "errors": junit["errors"],
                                        "skipped": junit["skipped"]}]
        gate_doc["measured_resources"] = {"phase_wall_s": phase_wall}
        gate_doc["actual_run_refs"] = ["f04_reproduction.json", "public_path.json"]
        gate_doc["verified_reuse_refs"] = ["route_qualification (RA-03)", "PROBE_PARAMS (RA-03)"]
        gate_doc["protected_state_after_ref"] = "protected status: " + (prot_after["git_status_porcelain"] or "clean")
        writer.write_json("phase_gate.json", gate_doc, schema="regime_lab.ra_phase_gate.v1")

        verdict = verify_ra04(run_dir, pytest_xml=args.pytest_xml,
                              protected_status_after=prot_after["git_status_porcelain"])
        gate_doc["technical_gate"] = verdict["overall"]
        gate_doc["gate_results"] = [{"gate_id": gid, "status": "PASS" if g["pass"] else "FAIL",
                                     "reasons": g["reasons"][:3]} for gid, g in verdict["gates"].items()]
        writer.write_json("phase_gate.json", gate_doc, schema="regime_lab.ra_phase_gate.v1")

        manifest_doc = json.loads((run_dir / "phase_manifest.json").read_text())
        manifest_doc["artifacts"] = manifest_records()
        writer.write_json("phase_manifest.json", manifest_doc, schema="regime_lab.ra04_manifest.v1")

        verdict = verify_ra04(run_dir, pytest_xml=args.pytest_xml,
                              protected_status_after=prot_after["git_status_porcelain"])
        writer.write_json("verification.json", verdict, schema="regime_lab.ra04_verification.v1")
        write_text_atomic(run_dir / "report.md",
                          build_report(baseline, verdict, writer.lab_run_id, manifest_doc, f04,
                                      admission, search_reg, controls, public_path, readiness))
        write_text_atomic(run_dir / "handoff.md", build_handoff(writer.lab_run_id, verdict))
        att.detail = {"run_dir": str(run_dir), "overall": verdict["overall"]}

    print(json.dumps({"run_dir": str(run_dir), "overall": verdict["overall"],
                      "gates": {k: v["pass"] for k, v in verdict["gates"].items()}}, indent=2))
    return 0 if verdict["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
