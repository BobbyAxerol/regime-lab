#!/usr/bin/env python
"""LAB-09 audit, driven by the checklist written BEFORE the code.

`configs/lab09_checklist.json` was committed before `experiments/uncertainty.py`,
`experiments/stress.py` and every LAB-09 script existed.

This auditor differs from its predecessors in one way that matters. Earlier
phases marked a clause DONE when a STRING naming its evidence was present; a
pointer at a field that had been renamed, or at a test that no longer existed,
looked identical to a real one. Here every pointer is RESOLVED:

  artifact.json:a.b[].c   the path is walked in the committed artifact
  tests/x.py::test_y      the node id is collected by pytest
  src/x.py:symbol         the file exists and defines the symbol
  reports/x.md            the file exists

A clause is DONE only when every pointer it carries resolves. An unresolvable
pointer is reported with the reason, not silently counted.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"
PYTHON = LAB_ROOT / "environments" / "lab_venv" / "bin" / "python"

U = "lab09_confirmation_spec.json"
R = "lab09_confirmation_results.json"
S = "lab09_stress.json"
P = "lab09_support.json"
C = "lab09_uncertainty.json"
K = "lab09_reconciliation.json"
M = "lab09_claim_report.json"
V = "lab09_development_replay.json"
B = "cost_binding_verification.json"
T = "tests/test_lab09_confirmation.py::"
TU = "tests/test_lab09_uncertainty.py::"
TS = "tests/test_lab09_stress.py::"

EVIDENCE: dict[str, tuple[str, str]] = {
    # ---- L09.1 lock data roles
    "L09.1.1": (f"{U}:prior_access_audit.checked[].inside_development + {U}:unused_by_this_lab",
                "every completed phase's declared window is checked against the boundary"),
    "L09.1.2": (f"{U}:holdout_status + {U}:why_not_a_clean_holdout",
                "NESTED_RETROSPECTIVE, stated rather than implied"),
    "L09.1.3": (f"{U}:prospective_protocol.status + {U}:prospective_protocol.not_self_executed",
                "specified, not executed; the lab has no market execution path"),
    "L09.1.4": (f"{U}:access_log + {R}:stamp_ordering",
                "every access carries a lab_run_id in evidence/**/attempts.jsonl"),
    "L09.1.5": (f"{U}:no_retuning_after_unlock + {U}:retuning_rule", ""),
    "L09.1.6": (f"{R}:stamp_ordering.unlock_precedes_run + "
                f"{T}test_the_unlock_precedes_the_confirmation_run", ""),
    # ---- L09.2 run the frozen protocol
    "L09.2.1": (f"{R}:cells_planned + {R}:cells + {T}test_the_confirmation_runs_the_same_matrix",
                "20 planned, the same NOT_READY rows carrying null metrics"),
    "L09.2.2": (f"{R}:seeds", "carried from the frozen protocol, not re-chosen"),
    "L09.2.3": (f"{R}:economics + {K}:financial_identity.cost_binding",
                "the contract is carried unchanged; the binding defect is measured and reported"),
    "L09.2.4": (f"{R}:engine_untouched + {R}:no_human_adjustment.unchanged_during_run", ""),
    "L09.2.5": (f"{R}:cells[].notes.regime_schedule + {R}:cells[].arms[].switch_delays",
                "the stateful part adapts through the frozen policy's own gates"),
    "L09.2.6": (f"{R}:no_human_adjustment + {T}test_a_mid_run_edit_is_detected",
                "every module hashed before the first cell and after the last"),
    "L09.2.7": (f"{R}:protocol_frozen_at_utc + {R}:stamp_ordering.freeze_precedes_unlock", ""),
    # ---- L09.3 paired uncertainty
    "L09.3.1": (f"{C}:contrasts.B-A.not_a_portfolio + "
                f"{TU}test_pairing_excludes_days_a_cell_was_not_live",
                "a macro-average across cells, named as one: guide 11.3 forbids implying a "
                "portfolio without a capital allocation and an account simulator"),
    "L09.3.2": (f"{C}:resampling + "
                f"{TU}test_blocks_widen_the_interval_on_an_autocorrelated_series", ""),
    "L09.3.3": (f"{TU}test_symbols_are_resampled_together_so_common_shocks_survive + "
                f"{C}:contrasts", "one date sequence per draw, applied to every cell"),
    "L09.3.4": (f"{C}:contrasts.B-A.episodes", "per-cell day counts, shared days, min and max"),
    "L09.3.5": (f"{C}:contrasts.B-A.concentration + "
                f"{TU}test_concentration_counts_offsetting_days_as_concentration", ""),
    "L09.3.6": (f"{C}:holm.family + {C}:holm.adjusted",
                "Holm over the family registered in the frozen protocol"),
    "L09.3.7": (f"{C}:exploratory.contrasts + {C}:holm.excluded_from_family", "E-B"),
    "L09.3.8": (f"{V}:block_length_calibration + {C}:contrasts.B-A.block_length_sensitivity",
                "chosen on development, applied unchanged, and varied"),
    # ---- L09.4 cost and latency stress
    "L09.4.1": (f"{S}:cost_stress.multipliers + {S}:cost_stress.pooled", "1x, 1.5x, 2x"),
    "L09.4.2": ("lab07_continuous_trace.json:training_jobs.benchmark.source + "
                f"{R}:cells[].arms[].switch_delays",
                "the refit latency is measured, never taken as zero"),
    "L09.4.3": (f"{S}:information_stress.per_cell[].stresses.MISLABELLED_TRANSITIONS + "
                f"{TS}test_mislabelling_moves_transitions_without_inventing_states", ""),
    "L09.4.4": (f"{S}:information_stress.per_cell[].stresses.STALE_FEED + "
                f"{TS}test_a_stale_feed_holds_a_value_and_keeps_the_tape_length", ""),
    "L09.4.5": (f"{S}:information_stress.per_cell[].stresses.MISSING_ENRICHMENT + "
                f"{TS}test_missing_enrichment_drops_rows_rather_than_zeroing_them", ""),
    "L09.4.6": (f"{S}:no_retuning_after_a_stress", ""),
    # ---- L09.5 support and novelty
    "L09.5.1": (f"{P}:situations.NEW_REGIME_EPISODE.a_new_episode_was_exercised", ""),
    "L09.5.2": (f"{P}:situations.MIXED_AMBIGUOUS_STATES.per_symbol", ""),
    "L09.5.3": (f"{P}:situations.STATE_LABEL_PERMUTATION_AFTER_REFIT + "
                f"{TS}test_a_label_permutation_leaves_the_transition_positions_alone", ""),
    "L09.5.4": (f"{P}:situations.POLICY_ON_THE_CONFIRMATION_INTERVAL", ""),
    "L09.5.5": (f"{P}:situations.POLICY_ON_THE_CONFIRMATION_INTERVAL", ""),
    "L09.5.6": (f"{P}:situations.CAMPAIGN_NOT_FLAT.status + "
                f"{P}:situations.CAMPAIGN_NOT_FLAT.arms_carrying_a_switch_delay_record + "
                f"{P}:situations.CAMPAIGN_NOT_FLAT.switches_that_waited_for_an_open_campaign",
                "bars waited PER REASON, accumulated while waiting; the final-reason histogram "
                "is cleared on activation and cannot answer this"),
    "L09.5.7": (f"{P}:time_edge_attribution + "
                f"{P}:situations.NEW_REGIME_EPISODE.per_symbol", ""),
    # ---- L09.6 reconciliation
    "L09.6.1": (f"{K}:financial_identity + {B}:verdict",
                "the cash identity closes; the fee binding does not, and is reported"),
    "L09.6.2": (f"{K}:parameter_version_lifecycle.every_bar_attributed", ""),
    "L09.6.3": (f"{K}:search_cardinality.all_executions_recorded", ""),
    "L09.6.4": (f"{K}:objective_recomputation.all_match", "R = G - lambda_F * F"),
    "L09.6.5": (f"{K}:replay.development.exact + {K}:replay.confirmation.all_reproduced", ""),
    "L09.6.6": (f"{K}:audits_retained.all_present + {K}:audits_retained.all_clean + "
                f"{K}:audits_retained.evidence_pointers.verdict + "
                f"{K}:audits_retained.fast_profile_used",
                "present AND clean: an audit that is present and failing is a retained failure"),
    # ---- L09.7 the claim
    "L09.7.1": (f"{M}:contributions.DESCRIPTIVE + lab09_group_ablation.json:per_symbol",
                "measured on a window inside the interval, not on the fitter's first cutoff"),
    "L09.7.2": (f"{M}:contributions.PREDICTIVE", ""),
    "L09.7.3": (f"{M}:contributions.SELECTION", ""),
    "L09.7.4": (f"{M}:contributions.TIMING", ""),
    "L09.7.5": (f"{M}:contributions.POLICY", ""),
    "L09.7.6": (f"{M}:net_gain_after_risk_and_cost + {M}:conclusion_level + "
                f"{M}:decision_rule + {C}:contrasts.C-A.ci_lower",
                "an interval, or the word inconclusive; the rule that turns one into the other "
                "was fixed before the intervals were computed"),
    "L09.7.7": (f"{M}:forbidden.fund_grade_alpha_proven + "
                f"{T}test_no_report_claims_a_proven_fund_grade_alpha", ""),
    # ---- guide 11.x
    "G11.1.2": (f"{U}:prior_access_audit.any_phase_read_the_outer_window + "
                f"{U}:no_retuning_after_unlock", ""),
    "G11.2.4": (f"{M}:conclusion_level + {M}:conclusion_vocabulary", ""),
    "G11.4.1": (f"{P}:transition_diagnostics.anchored_on + "
                f"{P}:transition_diagnostics.activation_delay + "
                f"{P}:transition_diagnostics.wrong_switch_loss.status",
                "activation delay, transition turnover, refused switches, stale incumbent, "
                "fallback usage and rank stability, all anchored on DETECTED transitions"),
    "G11.4.2": (f"{M}:scope.statement + {C}:contrasts.C-A.concentration", ""),
    "G11.4.3": (f"{C}:contrasts.C-A.concentration + "
                f"{P}:situations.NEW_REGIME_EPISODE.per_symbol + "
                f"{P}:transition_diagnostics.unknown_and_fallback_usage",
                "losing days and under-observed states are in the panels, not filtered"),
    # ---- acceptance
    "T62.1": (f"{M}:scope + {T}test_no_untested_cell_is_presented_as_evidence", ""),
    "T63.1": (f"{TU}test_symbols_are_resampled_together_so_common_shocks_survive + "
              f"{C}:resampling", ""),
    # ---- outputs
    "OUT.1": (f"{U}:unlocked_at_utc", ""),
    "OUT.2": (f"{R}:cells", ""),
    "OUT.3": (f"{C}:contrasts", ""),
    "OUT.4": (f"{S}:cost_stress.pooled + {S}:information_stress.per_cell", ""),
    "OUT.5": (f"{M}:conclusion_level", ""),
    "OUT.6": ("lab09_leakage_contamination.json:findings", ""),
    "OUT.7": ("lab09_limitations.json:limitations", ""),
    # ---- exit
    "EXIT.1": (f"{M}:scope.statement + {M}:conclusion_level", ""),
    "EXIT.2": (f"{M}:blockers + {M}:forbidden.statement", ""),
    "EXIT.3": (f"{M}:accounting_severity.severity + {M}:accounting_severity.rule + "
               f"{K}:financial_identity.cost_binding_is_a_finding",
               "whether the accounting defect is MAJOR is decided by a rule fixed before the "
               "measurement that settles it"),
    "EXIT.4": ("correction_ledger.json:defects + correction_ledger.json:numeric_history",
               "every defect is recorded with what it invalidated and the test that now guards "
               "it; a numeric one also names the run it superseded"),
}

ARTIFACTS = (U, R, S, P, C, K, M, V, B, "lab09_group_ablation.json",
             "lab09_leakage_contamination.json", "lab09_limitations.json",
             "lab09_checklist.json")

_STEP = re.compile(r"([^.\[]+)(\[\])?")


def _fan(node):
    """`[]` means 'every element'. A JSON collection is a list OR an object.

    An earlier version accepted only lists, so a pointer at
    `cells[].arms[].status` -- where `arms` is keyed by arm name -- was reported
    BROKEN although it resolves. An auditor that manufactures findings is no
    better than one that misses them.
    """
    if isinstance(node, list):
        return list(node), None
    if isinstance(node, dict):
        return list(node.values()), None
    return None, f"{type(node).__name__} is neither a list nor an object"


def walk(document, path: str) -> tuple[bool, str]:
    """Resolve a dotted path, where `[]` means 'every element of this collection'."""
    node = document
    for raw in path.split("."):
        match = _STEP.fullmatch(raw)
        if match is None:
            return False, f"unparsable path step {raw!r}"
        key, listed = match.group(1), bool(match.group(2))
        if isinstance(node, list):
            # already fanned out: the key must resolve in at least one element
            candidates = [n for n in node if isinstance(n, dict) and key in n]
            if not candidates:
                return False, f"no element carries {key!r}"
            node = [n[key] for n in candidates]
            if listed:
                fanned = []
                for sub in node:
                    items, _ = _fan(sub)
                    fanned.extend(items or [])
                if not fanned:
                    return False, f"{key!r} fans out to nothing"
                node = fanned
            continue
        if not isinstance(node, dict) or key not in node:
            available = sorted(node)[:8] if isinstance(node, dict) else type(node).__name__
            return False, f"{key!r} not present; found {available}"
        node = node[key]
        if listed:
            items, problem = _fan(node)
            if problem:
                return False, f"{key!r}: {problem}"
            if not items:
                return False, f"{key!r} is empty, so the pointer proves nothing"
            node = items
    return True, "resolved"


def collected_tests() -> set[str]:
    """Every node id pytest can actually collect, normalised to `tests/...`.

    pytest prints node ids relative to ITS rootdir, which is the parent
    repository here, so the raw lines carry a `lab_regime_model_quantbt/`
    prefix. Matching them verbatim reported every real test as uncollectable --
    an auditor that fails closed, but for the wrong reason.
    """
    proc = subprocess.run([str(PYTHON), "-m", "pytest", "tests", "--collect-only", "-q",
                           "-p", "no:warnings"],
                          capture_output=True, text=True, cwd=str(LAB_ROOT))
    out = set()
    for line in proc.stdout.splitlines():
        line = line.strip()
        if "::" not in line or "tests/" not in line:
            continue
        node = "tests/" + line.split("tests/", 1)[1]
        out.add(node)
        out.add(node.split("[")[0])
    if not out:
        raise RuntimeError(
            "pytest collected nothing; the audit cannot tell a missing test from a broken "
            f"collection. stderr: {proc.stderr.strip()[-500:]}")
    return out


def resolve(pointer: str, tests: set[str]) -> tuple[bool, str]:
    pointer = pointer.strip()
    if "::" in pointer:
        return (pointer in tests, "collected" if pointer in tests
                else "pytest does not collect this node id")
    if pointer.startswith(("reports/", "figures/", "evidence/", "handoff/")):
        head = pointer.split(":")[0].split("**")[0]
        path = LAB_ROOT / head
        if "**" in pointer or "*" in pointer:
            return (bool(list(LAB_ROOT.glob(pointer.split(":")[0]))), "glob")
        return (path.exists(), "exists" if path.exists() else "missing file")
    if pointer.startswith("src/") or pointer.endswith(".py") or ".py:" in pointer:
        head, _, symbol = pointer.partition(":")
        for base in (LAB_ROOT, LAB_ROOT / "src" / "crypto_regime_lab"):
            path = base / head
            if not path.is_file():
                continue
            if not symbol:
                return True, "file exists"
            # a dotted symbol names a class and its member; Python source does not
            # contain the dotted form, so each segment is looked for separately
            text = path.read_text()
            missing = [part for part in symbol.split()[0].split(".") if part not in text]
            return (not missing,
                    "symbol found" if not missing else f"{head} does not define {missing}")
        return False, f"no such source file {head}"
    name, _, path = pointer.partition(":")
    artifact = LAB_ROOT / "configs" / name
    if not artifact.is_file():
        return False, f"configs/{name} does not exist"
    if not path:
        return True, "artifact exists"
    return walk(json.loads(artifact.read_text()), path.split()[0])


def main() -> int:
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    checklist = json.loads((LAB_ROOT / "configs" / "lab09_checklist.json").read_text())
    tests = collected_tests()
    tasks = []
    for clause_id, requirement in checklist["clauses"]:
        pointer_text, note = EVIDENCE.get(clause_id, ("", ""))
        if not pointer_text:
            tasks.append({"clause_id": clause_id, "requirement": requirement, "evidence": "",
                          "note": note, "status": "MISSING",
                          "unresolved": ["no evidence pointer"]})
            continue
        checks = []
        for pointer in pointer_text.split(" + "):
            ok, detail = resolve(pointer, tests)
            checks.append({"pointer": pointer.strip(), "resolved": ok, "detail": detail})
        unresolved = [c["pointer"] + " — " + c["detail"] for c in checks if not c["resolved"]]
        tasks.append({"clause_id": clause_id, "requirement": requirement,
                      "evidence": pointer_text, "note": note,
                      "pointers": checks,
                      "status": "DONE" if not unresolved else "UNRESOLVED_EVIDENCE",
                      "unresolved": unresolved})

    missing = [a for a in ARTIFACTS if not (LAB_ROOT / "configs" / a).is_file()]
    proc = subprocess.run(
        [str(PYTHON), "-m", "pytest", str(LAB_ROOT / "tests" / "test_lab09_confirmation.py"),
         str(LAB_ROOT / "tests" / "test_lab09_uncertainty.py"),
         str(LAB_ROOT / "tests" / "test_lab09_stress.py"), "-q", "-p", "no:warnings"],
        capture_output=True, text=True, cwd=str(LAB_ROOT))
    summary = [ln for ln in proc.stdout.splitlines() if "passed" in ln or "failed" in ln]

    document = {
        "schema": "crypto_regime_lab.lab09_task_audit.v1",
        "guide_section": "LAB-09",
        "checklist_written_before_code": checklist["written_before_code"],
        "checklist_source": "configs/lab09_checklist.json",
        "evidence_pointers_are_resolved": True,
        "resolution_rule": ("every pointer is walked in the artifact, collected by pytest, or "
                            "found in the source. A clause whose pointer names a field that does "
                            "not exist is UNRESOLVED_EVIDENCE, not DONE -- earlier phases counted "
                            "the presence of the string"),
        "tasks_total": len(tasks),
        "tasks_done": sum(1 for t in tasks if t["status"] == "DONE"),
        "tasks_blocked": sum(1 for t in tasks if t["status"] != "DONE"),
        "clauses_without_resolved_evidence": [t["clause_id"] for t in tasks
                                              if t["status"] != "DONE"],
        "artifacts_present": [a for a in ARTIFACTS if a not in missing],
        "artifacts_missing": missing,
        "acceptance_tests": summary[-1] if summary else "not run",
        "acceptance_tests_passed": proc.returncode == 0,
        "acceptance_ids_covered": ["T62", "T63"],
        "tasks": tasks,
    }
    with writer.attempt("L09.audit") as att:
        att.detail = {"done": document["tasks_done"], "total": document["tasks_total"]}
    writer.write_config("lab09_task_audit.json", document)
    writer.write_json("lab09_task_audit.json", document, schema=document["schema"])

    print(f"LAB-09 audit: {document['tasks_done']}/{document['tasks_total']} DONE")
    for task in tasks:
        if task["status"] == "DONE":
            continue
        print(f"  {task['clause_id']:<12} {task['status']}")
        for line in task["unresolved"]:
            print(f"      {line}")
    print(f"artifacts missing: {missing or 'none'}")
    print(f"acceptance tests : {document['acceptance_tests']}")
    print(f"evidence -> {writer.run_dir}")
    return 0 if document["tasks_blocked"] == 0 and proc.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
