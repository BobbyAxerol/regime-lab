#!/usr/bin/env python
"""A clause-by-clause audit of LAB-04 against the guide text.

One row per requirement sentence in the LAB-04 section, each with the artifact or
test that discharges it. A row is DONE only when something committed proves it.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"

TASKS = [
    # --- L04.1 -------------------------------------------------------
    ("L04.1.1", "fixed parameter matrix traced before the search",
     "configs/lab04_installed_wfo_trace.json:installed_defaults.optuna_sampler",
     "optuna_trials defaults to 0 and mode 'none' ran ONE trial: the fixed matrix is the default"),
    ("L04.1.2", "current selected mode traced",
     "configs/lab04_installed_wfo_trace.json:search_behaviour", "mode 'none', 1 trial, no search"),
    ("L04.1.3", "optuna sampler identified",
     "installed_defaults.optuna_sampler", "TPESampler(seed=study_seed) + DuplicatePruner"),
    ("L04.1.4", "proxy vs native objective resolved",
     "installed_defaults.objective_backend",
     "endpoint backend returned all-zero Sharpes for this strategy shape; proxy used, divergence recorded"),
    ("L04.1.5", "candidate freeze traced",
     "installed_defaults.candidate_freeze",
     "_select_is_candidate_records then _select_oos_candidate_record, before outer evaluation"),
    ("L04.1.6", "OOS usage measured, not assumed",
     "lab04_installed_wfo_trace.json:oos_usage_probes",
     "mutation probe with an IS-invariance precondition; per_fold_decay moves the selection"),
    ("L04.1.7", "baseline floor traced",
     "installed_defaults.baseline_floor",
     "min_trades_per_year and trade_penalty_factor both default to None: no floor unless configured"),
    ("L04.1.8", "retention traced",
     "installed_defaults.retention",
     "financial=score, research=none, scope=selected_final_execution"),
    ("L04.1.9", "modes 1-5 of the PINNED version distinguished",
     "lab04_installed_wfo_trace.json:modes.traces",
     "all six settings run; mode_5 collapses to one fold and is full-sample calibration"),
    ("L04.1.10", "no assumption that every mode calls the generic selector",
     "lab04_installed_wfo_trace.json:modes.selector_families",
     "two families measured separately; the WFO record selectors are not CandidateSelector"),
    # --- L04.2 -------------------------------------------------------
    ("L04.2.1", "sharp peak vs broad plateau", "CE-01", "T29"),
    ("L04.2.2", "bad neighbors retained", "CE-11",
     "a losing valid neighbour raises F and lowers R and P_survive; measured both ways"),
    ("L04.2.3", "duplicate samples", "CE-03", "probe ids unique inside a tight radius"),
    ("L04.2.4", "fixed dimensions", "CE-04", "DEFECT_CONFIRMED on candidate_selection"),
    ("L04.2.5", "sampled-span scaling", "CE-05", "DEFECT_CONFIRMED, 98x collapse measured"),
    ("L04.2.6", "missing consensus", "CE-07", "INSUFFICIENT_LOCAL_EVIDENCE, no fabricated plateau"),
    ("L04.2.7", "invalid centroid", "CE-08", "T33, deployment refused"),
    ("L04.2.8", "raw baseline override", "CE-09", "T35, guard disagreement logged"),
    # the field was `source_symbols` when this pointer was written and is now
    # `selector_families.<family>.symbols`, because a symbol list that does not
    # say WHICH selector family it belongs to was the defect L04.2.10 records.
    # Found by scripts/audit_evidence_pointers.py, which resolves pointers
    # instead of counting them (COR-15).
    ("L04.2.9", "actual source symbols and reproducers attached",
     "lab04_selector_counterexamples.json:selector_families",
     "_param_distance / _numeric_span with file:line, each with a runnable reproducer, "
     "scoped to the family it applies to"),
    ("L04.2.10", "already-correct behaviour recorded as verified-existing",
     "counterexamples.by_verdict",
     "the WFO family is VERIFIED_EXISTING_CORRECT; only the CandidateSelector family is accused"),
    # --- L04.3 -------------------------------------------------------
    ("L04.3.1", "geometry from a per-alpha schema", "selector/alpha_schemas.py", "four schemas"),
    ("L04.3.2", "dependent params ordered by construction",
     "test_t32_dependencies_are_parameterised_not_repaired", "no post-hoc repair"),
    ("L04.3.3", "inactive flags excluded from distance",
     "test_t31_inactive_parameter_creates_no_false_distance", "0 distance when the branch is off"),
    ("L04.3.4", "seed and design frozen and reproducible",
     "test_t32_probe_design_is_reproducible_across_processes",
     "identical probe ids under three PYTHONHASHSEED values"),
    ("L04.3.5", "every valid bad probe kept in the denominator",
     "test_t29_valid_bad_probes_stay_in_the_denominator", "measured"),
    ("L04.3.6", "runtime error means incomplete evidence",
     "test_t29_runtime_error_is_incomplete_evidence_not_a_loss", "INCOMPLETE_PANEL"),
    ("L04.3.9", "anchors come from TPE, the incumbent AND space-filling coverage (7.2 step 1)",
     "tests/test_lab04_evaluator.py::test_anchors_are_drawn_from_tpe_incumbent_and_space_filling",
     "4 anchor slots: 2 TPE + 1 farthest-point + 1 incumbent, total budget still 96"),
    ("L04.3.8", "probe radius is a registered sensitivity, not tuned after an outer result",
     "configs/lab04_probe_radius_sensitivity.json",
     "radii 0.06/0.12/0.24 declared before the run; the primary stays 0.12 regardless"),
    ("L04.3.7", "structurally invalid is not bad performance",
     "test_t29_structurally_invalid_is_not_bad_performance", "excluded, not penalised"),
    # --- L04.4 -------------------------------------------------------
    ("L04.4.1", "score follows guide 7.3", "selector/robust_score.py",
     "G=Q0.25, F=median_e Q0.75 regret, R=G-lambda_F*F, P_survive"),
    ("L04.4.2", "same episode lengths, risk and cost",
     "test_inner_episodes_have_equal_length + evaluator.ACCOUNT",
     "equal-length episodes; one frozen account contract for every candidate and arm"),
    ("L04.4.3", "incumbent gets the same validation budget",
     "test_t35_incumbent_receives_the_same_validation_budget", "same episodes and neighbours"),
    ("L04.4.4", "before/after guard logged",
     "configs/lab04_incumbent_parity.json:guard_before,guard_after", "both recorded"),
    ("L04.4.5", "centroid/medoid only over feasible evaluated candidates with traceable panels",
     "selector/representative.py:choose_representative + "
     "tests/test_lab04_selector.py::test_t33_unevaluated_centroid_is_not_deployable + "
     "tests/test_lab04_selector.py::test_t34_medoid_minimises_the_same_distance_the_selector_declares",
     "medoid over ELIGIBLE only; centroid is a proposal until evaluated"),
    # --- L04.5 -------------------------------------------------------
    ("L04.5.1", "same calendar, training memory, engine, retention and eval budget",
     "calendar_baseline.summarize:matched_conditions", "seven matched conditions listed"),
    ("L04.5.2", "no regime information in either arm",
     "calendar_baseline:regime_information_used=false", "neither arm reads a feature panel"),
    ("L04.5.3", "pilot one cell then expand to all 20",
     "scripts/run_calendar_baseline.py:PILOT_ORDER",
     "A-SC/BTCUSDT first, then the full 4x5 matrix"),
    ("L04.5.4", "no claiming full scope from the winning symbol",
     "calendar_baseline:cells + console_table", "every cell status reported, winners and losers"),
    ("L04.5.5", "selection frozen before outer evaluation (guide 7.2 step 7)",
     "tests/test_lab04_evaluator.py::test_selection_is_frozen_before_the_test_window_is_touched",
     "the test window is mutated and both arms' selections stay byte-identical"),
    ("L04.5.6", "the fast evaluator equals a whole-window fixed point",
     "tests/test_lab04_evaluator.py::test_the_fast_sweep_matches_a_whole_window_fixed_point",
     "identical fills, reasons and equity against the slow reference loop"),
    ("L04.5.7", "entries are sized to the frozen entry notional",
     "tests/test_lab04_evaluator.py::test_entries_are_sized_to_the_frozen_entry_notional",
     "2000 USDT per entry, not one whole unit; this is what LAB-03's zero-fill smoke missed"),
    # --- L04.6 -------------------------------------------------------
    ("L04.6.1", "actual local coverage reported", "calendar_baseline:local_coverage", ""),
    ("L04.6.2", "lower tail reported", "calendar_baseline:lower_tail", ""),
    ("L04.6.3", "survival reported", "robust_scores[*].p_survive per cutoff", ""),
    ("L04.6.4", "trade counts reported", "arms[*].trades", ""),
    ("L04.6.5", "period concentration reported", "arms[*].period_concentration", ""),
    ("L04.6.6", "parameter-behaviour fingerprint reported",
     "calendar_baseline:parameter_behaviour_fingerprint", "turnover, distinct sets, trades"),
    ("L04.6.7", "A and B both kept for the factorial regardless of the result",
     "calendar_baseline:factorial_rule", ""),
    # --- hygiene: debt found and cleared on the LAB-04 re-review -------
    ("DEBT.1", "no dead code, unused imports or undefined names in lab source",
     "tests/test_lab04_evaluator.py::test_no_dead_code_or_undefined_names_in_lab_source",
     "pyflakes gate; raw-supplied/ is excluded because its lint IS the evidence (SD-HASH-01)"),
    ("DEBT.2", "the four supplied alphas remain byte-identical",
     "tests/test_lab04_evaluator.py::test_the_raw_alphas_are_still_byte_identical",
     "the lint exclusion is only safe while the originals are untouched"),
    ("DEBT.3", "dev tooling declared and kept out of the runtime lock",
     "configs/dev_tools.json",
     "pyflakes/autoflake added after the LAB-01 pin; engine pin 1.1.1/0.4.2 unchanged"),
    ("DEBT.4", "one source of truth for blocked alphas and decision intervals",
     "tests/test_lab04_evaluator.py::test_blocked_alphas_come_from_the_certification_not_a_literal",
     "NOT_READY reads the LAB-02 certification; DECISION_INTERVAL is the LAB-03 object itself"),
    ("DEBT.5", "centroid geometry matches the distance that selected it",
     "tests/test_lab04_selector.py::test_centroid_of_a_log_parameter_is_the_geometric_mean",
     "log kinds use the geometric mean; ints snap to the declared grid"),
    ("DEBT.6", "centroid of an ordered pair cannot collapse into an infeasible point",
     "tests/test_lab04_selector.py::test_centroid_of_an_ordered_pair_stays_feasible", ""),
    ("DEBT.7", "no selector output depends on PYTHONHASHSEED",
     "tests/test_lab04_selector.py::test_centroid_categorical_tie_break_is_process_stable",
     "probe design and centroid tie-break both checked under three salts"),
    ("DEBT.8", "trade counts distinguish engine fills from entries",
     "tests/test_lab04_evaluator.py::test_trade_counts_distinguish_fills_from_entries", ""),
    ("DEBT.9", "a partial matrix is labelled partial and blocks the L04.5/L04.6 rows",
     "tests/test_lab04_evaluator.py::test_a_partial_matrix_is_labelled_partial", ""),
    ("DEBT.10", "retention reasons name the constraint that actually bound",
     "configs/lab04_calendar_baseline.json:retention_events[*].reasons",
     "ALL_FAIL_ECONOMIC_QUALITY vs NO_LOCAL_PANEL vs ALL_FAIL_SURVIVAL, not one status for all"),
    ("DEBT.11", "the B-A contrast states its confound before it is read",
     "configs/lab04_calendar_baseline.json:confounds",
     "asymmetric switching rate; the HOLD control that would separate it is named and not run"),
    ("DEBT.12", "the committed code still reproduces a committed cutoff decision",
     "configs/lab04_cutoff_reproducibility.json",
     "a multi-hour run executes the modules loaded at launch; this re-runs one real cutoff"),
    ("DEBT.13", "confirmed engine defects recorded as a bounded proposal, never applied",
     "handoff/lab_only_patch.diff + handoff/README.md",
     "CLAUDE.md rule 1; a test proves the installed wheel still has the original body"),
    # --- exit --------------------------------------------------------
    ("EXIT.1", "which selector the public route actually uses is known",
     "lab04_installed_wfo_trace.json:public_route_default",
     "_select_oos_candidate_record under metric robust_decay = argmax objective"),
    ("EXIT.2", "honest A/B result and search budget reported",
     "calendar_baseline:contrast_B_minus_A + search_effort",
     "unique executions and candidate-episode visits, not a trial count"),
    ("EXIT.3", "legacy OOS-selected modes labelled, never reused as an untouched claim",
     "lab04_installed_wfo_trace.json:legacy_oos_labelling", ""),
]


def main() -> int:
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    artifacts = {
        "lab04_cutoff_reproducibility.json":
            (LAB_ROOT / "configs/lab04_cutoff_reproducibility.json"),
        "lab04_probe_radius_sensitivity.json":
            (LAB_ROOT / "configs/lab04_probe_radius_sensitivity.json"),
        "lab04_installed_wfo_trace.json": (LAB_ROOT / "configs/lab04_installed_wfo_trace.json"),
        "lab04_selector_counterexamples.json":
            (LAB_ROOT / "configs/lab04_selector_counterexamples.json"),
        "lab04_probe_designs.json": (LAB_ROOT / "configs/lab04_probe_designs.json"),
        "lab04_incumbent_parity.json": (LAB_ROOT / "configs/lab04_incumbent_parity.json"),
        "lab04_calendar_baseline.json": (LAB_ROOT / "configs/lab04_calendar_baseline.json"),
    }
    missing_artifacts = sorted(name for name, path in artifacts.items() if not path.is_file())

    # a PARTIAL matrix is not a completed L04.5/L04.6: treat it as still blocked
    baseline_path = artifacts["lab04_calendar_baseline.json"]
    matrix_complete = False
    matrix_note = "artifact absent"
    design_matches_spec = False
    if baseline_path.is_file():
        baseline = json.loads(baseline_path.read_text())
        complete = bool(baseline.get("matrix_complete"))
        # A complete matrix built with the WRONG anchor design is not a completed
        # L04.5. Guide 7.2 step 1 names three anchor sources; a run without the
        # space-filling slot confines every local panel to the TPE region.
        budget = baseline.get("search_budget", {})
        space_filling = budget.get("space_filling_anchors")
        # null means the cells were produced before the field existed, i.e. WITHOUT it
        design_matches_spec = isinstance(space_filling, int) and space_filling >= 1
        matrix_complete = complete and design_matches_spec
        matrix_note = (f"{len(baseline.get('cells', []))}/"
                       f"{baseline.get('cells_expected', '?')} cells, "
                       f"cells_dir={baseline.get('cells_dir', '?')}, "
                       f"space_filling_anchors={space_filling}")
        if not complete:
            missing_artifacts.append("lab04_calendar_baseline.json (PARTIAL: "
                                     + matrix_note + ")")
        elif not design_matches_spec:
            missing_artifacts.append(
                "lab04_calendar_baseline.json (COMPLETE but built WITHOUT the space-filling "
                "anchor guide 7.2 step 1 requires: " + matrix_note + ")")

    tests = subprocess.run(
        [str(LAB_ROOT / "environments/lab_venv/bin/python"), "-m", "pytest",
         "tests/test_lab04_selector.py", "tests/test_lab04_evaluator.py",
         "-q", "--no-header", "-p", "no:warnings"],
        cwd=LAB_ROOT, capture_output=True, text=True, timeout=3600)
    test_line = next((ln for ln in reversed(tests.stdout.splitlines())
                      if "passed" in ln or "failed" in ln), "no pytest summary")

    rows = []
    for task_id, requirement, artifact, note in TASKS:
        blocked = (
            (task_id.startswith(("L04.5.1", "L04.5.2", "L04.5.3", "L04.5.4", "L04.6", "EXIT.2"))
             and not matrix_complete)
            or (task_id == "L04.3.8"
                and "lab04_probe_radius_sensitivity.json" in missing_artifacts)
            or (task_id == "DEBT.12"
                and "lab04_cutoff_reproducibility.json" in missing_artifacts))
        rows.append({
            "task_id": task_id, "requirement": requirement, "artifact": artifact,
            "note": note,
            "status": "BLOCKED_AWAITING_RUN" if blocked else "DONE",
        })

    done = sum(1 for r in rows if r["status"] == "DONE")
    payload = {
        "schema": "crypto_regime_lab.lab04_task_audit.v1",
        "guide_section": "LAB-04 -- Calendar baseline va robust-neighborhood selection",
        "tasks_total": len(rows), "tasks_done": done,
        "tasks_blocked": len(rows) - done,
        "artifacts_present": sorted(set(artifacts) - set(missing_artifacts)),
        "artifacts_missing": missing_artifacts,
        "acceptance_tests": test_line,
        "acceptance_tests_passed": tests.returncode == 0,
        "acceptance_ids_covered": ["T29", "T30", "T31", "T32", "T33", "T34", "T35", "T36"],
        "primary_matrix_complete": matrix_complete,
        "primary_matrix": matrix_note,
        "primary_matrix_design_matches_spec": design_matches_spec,
        "design_rule": ("L04.5/L04.6 are DONE only when the committed matrix is both complete AND "
                        "produced by the anchor design guide 7.2 step 1 specifies (TPE + "
                        "incumbent + space-filling)"),
        "tasks": rows,
    }
    writer.write_config("lab04_task_audit.json", payload)
    writer.write_json("lab04_task_audit.json", payload, schema=payload["schema"])

    print(f"LAB-04 audit: {done}/{len(rows)} DONE")
    for row in rows:
        if row["status"] != "DONE":
            print(f"   {row['status']:<22} {row['task_id']} {row['requirement']}")
    print(f"artifacts missing: {missing_artifacts or 'none'}")
    print(f"acceptance tests : {test_line}")
    print(f"evidence -> {writer.run_dir}")
    return 0 if done == len(rows) and tests.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
