#!/usr/bin/env python
"""Which assertions in the suite never actually execute?

Every defect found in LAB-06 and LAB-07 was a check that could not fail: an
`assert all(...)` over an empty list, a loop whose body never ran, a probe handed
its own answer. Reading the tests does not reveal those -- they look like checks.
Running them and recording which assert lines were reached does.

This runs the whole suite under `sys.monitoring` and records every assert line,
and every statement inside a loop containing an assert, that was never reached.
An unreached assertion is not automatically a defect: a guard for a failure the
current data does not produce is correct and should stay. What is not acceptable
is an unreached assertion nobody has looked at, so each one must be declared in
`ACCEPTED` with the reason and with where its logic IS exercised.
"""

from __future__ import annotations

import ast
import json
import pathlib
import sys

LAB_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

#: `file::test::asserted-text` -> (why it cannot run here, where the rule IS exercised).
#: Keyed by the TEST and the assertion TEXT rather than by a line number, because a
#: line number expires on any edit above it -- and a stale one can land on a
#: different assert, which then reads as declared although nobody reviewed it.
#: The gate that reads THIS audit's output cannot be audited by it. When the gate
#: fails, pytest stops at its first assertion, so its later assertions go
#: unreached -- which makes the next run report them as undeclared, which keeps
#: the gate failing. A strange loop with no fixed point, and the same shape as
#: `audit_identities.py` reporting 12/12 by grepping its own output. The
#: exclusion is NAMED here rather than left implicit, exactly as that one is.
SELF_REFERENTIAL_TESTS = {
    "test_no_assertion_in_the_suite_is_unreached_without_a_declared_reason":
        "reads configs/assertion_vacuity_audit.json, so its own unreached lines are an artefact "
        "of it having failed on the previous run's artifact, not evidence about the suite",
}

ACCEPTED: dict[str, tuple[str, str]] = {
    "test_lab03_pipeline.py::"
    "test_read_lock_distinguishes_expected_drift_from_a_real_invalidation::"
    'assert verification["status"] in ("UNCHANGED", "EXPECTED_MUTABLE_DRIFT': (
        "the `else` for a snapshot with no closed-partition drift; upstream currently HAS drift",
        "tests/test_contingency_paths.py::test_the_no_drift_branch_reports_unchanged"),
    "test_lab03_pipeline.py::"
    "test_measured_metrics_drift_is_a_restamp_and_the_shallow_check_still_fails_closed::"
    'assert any(v["product_id"] == product for v in revisions), (': (
        "the cohort-invalidation loop; every current drift is a vintage re-stamp, so no cohort "
        "is invalidated",
        "tests/test_contingency_paths.py::test_a_content_revision_actually_invalidates_its_cohort"),
    "test_lab04_legacy_labelling.py::"
    "test_the_conclusion_level_comes_from_the_registered_vocabulary::"
    'assert not hyp["blockers_preventing_a_stronger_claim"]': (
        "the guard for a NET_PARAMETER_SELECTION_EDGE conclusion; LAB-04 concluded "
        "INCONCLUSIVE_SAMPLE",
        "tests/test_contingency_paths.py::"
        "test_a_stronger_conclusion_requires_no_blockers_and_a_real_effect"),
    "test_lab04_legacy_labelling.py::"
    "test_the_conclusion_level_comes_from_the_registered_vocabulary::"
    'assert abs(hyp["mean_daily_net_return_difference"]) >= \\': (
        "the same guard's second clause",
        "tests/test_contingency_paths.py::"
        "test_a_stronger_conclusion_requires_no_blockers_and_a_real_effect"),
    "test_lab04_legacy_labelling.py::"
    "test_the_audit_refuses_a_matrix_built_with_the_wrong_design::"
    'assert any(t.startswith("L04.5") for t in blocked), (': (
        "the branch for a probe design that deviates from spec; the real design matches",
        "tests/test_contingency_paths.py::test_a_spec_deviating_design_must_block_the_l045_rows"),
    "test_guide_contracts.py::"
    "test_the_identity_audit_does_not_pass_on_its_own_output::"
    'assert record["owner"] not in landed, (': (
        "the branch for an identity still OWED by a phase that has landed; every owed identity "
        "was discharged when its phase landed, so the population is empty",
        "tests/test_guide_contracts.py::test_the_taxonomy_lists_all_twelve_identities"),
    "test_lab09_confirmation.py::"
    "test_a_missing_measurement_is_never_reported_as_a_negative_result::"
    'assert entry.get("reason"), f"{name} is NOT_MEASURED without saying wh': (
        "the branch for a contribution that could not be measured; all five were measured on "
        "this run, so no contribution is NOT_MEASURED",
        "tests/test_contingency_paths.py::"
        "test_the_claim_rule_can_reach_every_verdict_it_declares"),
    "test_lab09_confirmation.py::"
    "test_the_conclusion_follows_the_registered_decision_rule::"
    'assert expected.startswith("NET_"), expected': (
        "the branch for a SUPPORTED contribution and therefore an edge conclusion; nothing "
        "cleared the minimum economic effect on this run",
        "tests/test_contingency_paths.py::"
        "test_the_claim_rule_can_reach_every_verdict_it_declares"),
    "test_lab09_confirmation.py::"
    "test_the_conclusion_follows_the_registered_decision_rule::"
    'assert entry["verdict"] == "SUPPORTED", name': (
        "the same branch at the per-contribution level: no interval sits entirely above the "
        "minimum",
        "tests/test_contingency_paths.py::"
        "test_the_claim_rule_can_reach_every_verdict_it_declares"),
    "test_lab09_confirmation.py::"
    "test_the_conclusion_follows_the_registered_decision_rule::"
    'assert entry["verdict"] == "INCONCLUSIVE", (': (
        "the branch for an interval that STRADDLES the minimum; every measured contribution was "
        "ruled out entirely BELOW it, which is a stronger negative than inconclusive",
        "tests/test_contingency_paths.py::"
        "test_the_claim_rule_can_reach_every_verdict_it_declares"),
    "test_lab08_factorial.py::"
    "test_risk_only_is_blocked_rather_than_silently_returning_the_baseline::"
    "assert transfer >= 0.5, (": (
        "the branch for a RISK_ONLY control that CAN be computed; state transfer across refits "
        "is 1.64%, so every cell reports BLOCKED_BY_STATE_NAMESPACING instead",
        "tests/test_lab08_factorial.py::"
        "test_risk_only_is_blocked_rather_than_silently_returning_the_baseline"),
    # RA-04 (2026-09-18): 21 lines found UNDECLARED across four phase test files.
    "test_rf04_decay_and_controls.py::"
    "test_rf04_paired_endpoints_fail_closed_on_identical_or_deviated::"
    'assert placebo["reason"], "a not-run placebo needs a reason"': (
        "RF-04's placebo control actually ran (status RUN); the not-run branch is for a future "
        "pilot where compute runs out before the placebo cutoff (guide RA07.3)",
        "tests/test_contingency_paths.py::test_a_not_run_placebo_must_carry_a_reason"),
    "test_rf04_scaling.py::"
    "test_rf04_coverage_20_unique_statuses_with_reasons_and_no_fabricated_equity::"
    'assert "budget" in cell["reason"].lower(), (': (
        "RF-04's 20 cells are only ever RUN_VALID or BLOCKED_CAPABILITY; no cell ran out of "
        "budget mid-attempt",
        "tests/test_contingency_paths.py::test_a_non_run_coverage_cell_must_name_why"),
    "test_rf04_scaling.py::"
    "test_rf04_coverage_20_unique_statuses_with_reasons_and_no_fabricated_equity::"
    'assert cell["reason"].strip(), f"{cell[\'cell\']} has no non-run reason"': (
        "same as the budget branch above: no cell in this pilot is NOT_RUN or NOT_RUN_BUDGET",
        "tests/test_contingency_paths.py::test_a_non_run_coverage_cell_must_name_why"),
    "test_rf05_claims.py::"
    "test_rf05_no_positive_without_ci_clearing_mde::"
    'assert stats.get("ci95_low_bps") is not None and stats["ci95_low_bps"]': (
        "no RF-05 contrast is ever POSITIVE_WITHIN_SCOPE (guide A16: the bounded pilot may never "
        "record one); the guard is for a future run that tries to, without a CI above the MDE",
        "tests/test_contingency_paths.py::"
        "test_a_positive_within_scope_status_needs_ci_above_mde_and_holm_significance"),
    "test_rf05_claims.py::"
    "test_rf05_no_positive_without_ci_clearing_mde::"
    'assert holm is not None and holm < 0.05, (': (
        "same POSITIVE-only branch: no contrast reaches it without an above-MDE CI first",
        "tests/test_contingency_paths.py::"
        "test_a_positive_within_scope_status_needs_ci_above_mde_and_holm_significance"),
    "test_rf05_claims.py::"
    "test_rf05_no_positive_without_ci_clearing_mde::"
    'assert entry["holm_significant"] is True': (
        "the `positives` list this loop walks is always empty -- no RF-05 family entry is "
        "POSITIVE_WITHIN_SCOPE",
        "tests/test_contingency_paths.py::"
        "test_a_positive_within_scope_status_needs_ci_above_mde_and_holm_significance"),
    "test_rf05_claims.py::"
    "test_rf05_no_positive_without_ci_clearing_mde::"
    'assert entry["mde_cleared"] is True': (
        "same empty `positives` loop as the line above",
        "tests/test_contingency_paths.py::"
        "test_a_positive_within_scope_status_needs_ci_above_mde_and_holm_significance"),
    "test_te03_7.py::"
    "test_measured_funnels_carry_denominators_and_reasons::"
    'assert by_condition': (
        "TE-03.7's controls funnel is still NOT_RUN_BUDGET (TE02-PILOT-R03 ledger has ~106442s "
        "left as of 2026-09-18); the MEASURED branch is real code waiting for that run, not dead "
        "code",
        "tests/test_contingency_paths.py::"
        "test_a_measured_te03_7_funnel_carries_full_denominators_and_reasons"),
    "test_te03_7.py::"
    "test_measured_funnels_carry_denominators_and_reasons::"
    'assert funnel["status"] == "MEASURED"': (
        "same NOT_RUN_BUDGET reason as the line above",
        "tests/test_contingency_paths.py::"
        "test_a_measured_te03_7_funnel_carries_full_denominators_and_reasons"),
    "test_te03_7.py::"
    "test_measured_funnels_carry_denominators_and_reasons::"
    'assert {row["step"] for row in funnel["steps"]} == FUNNEL_STEPS': (
        "same NOT_RUN_BUDGET reason",
        "tests/test_contingency_paths.py::"
        "test_a_measured_te03_7_funnel_carries_full_denominators_and_reasons"),
    "test_te03_7.py::"
    "test_measured_funnels_carry_denominators_and_reasons::"
    'for step in funnel["steps"]:': (
        "same NOT_RUN_BUDGET reason; this is the loop body over a MEASURED funnel's steps",
        "tests/test_contingency_paths.py::"
        "test_a_measured_te03_7_funnel_carries_full_denominators_and_reasons"),
    "test_te03_7.py::"
    "test_measured_funnels_carry_denominators_and_reasons::"
    'assert step.get("rule")': (
        "same NOT_RUN_BUDGET reason",
        "tests/test_contingency_paths.py::"
        "test_a_measured_te03_7_funnel_carries_full_denominators_and_reasons"),
    "test_te03_7.py::"
    "test_measured_funnels_carry_denominators_and_reasons::"
    'assert step["count"] is not None, f"{funnel[\'condition\']}/{step[\'step\'': (
        "same NOT_RUN_BUDGET reason",
        "tests/test_contingency_paths.py::"
        "test_a_measured_te03_7_funnel_carries_full_denominators_and_reasons"),
    "test_te03_7.py::"
    "test_measured_funnels_carry_denominators_and_reasons::"
    'assert isinstance(step["count"], int) and step["count"] >= 0': (
        "same NOT_RUN_BUDGET reason",
        "tests/test_contingency_paths.py::"
        "test_a_measured_te03_7_funnel_carries_full_denominators_and_reasons"),
    "test_te03_7.py::"
    "test_measured_funnels_carry_denominators_and_reasons::"
    'assert isinstance(step["denominator"], int)': (
        "same NOT_RUN_BUDGET reason",
        "tests/test_contingency_paths.py::"
        "test_a_measured_te03_7_funnel_carries_full_denominators_and_reasons"),
    "test_te03_7.py::"
    "test_measured_funnels_carry_denominators_and_reasons::"
    'assert step["count"] <= step["denominator"]': (
        "same NOT_RUN_BUDGET reason",
        "tests/test_contingency_paths.py::"
        "test_a_measured_te03_7_funnel_carries_full_denominators_and_reasons"),
    "test_te03_7.py::"
    "test_measured_funnels_carry_denominators_and_reasons::"
    'if step["denominator"] == 0:': (
        "same NOT_RUN_BUDGET reason; guards the zero-denominator escape hatch",
        "tests/test_contingency_paths.py::"
        "test_a_measured_te03_7_funnel_carries_full_denominators_and_reasons"),
    "test_te03_7.py::"
    "test_measured_funnels_carry_denominators_and_reasons::"
    'assert step["denominator_reason"]': (
        "same NOT_RUN_BUDGET reason",
        "tests/test_contingency_paths.py::"
        "test_a_measured_te03_7_funnel_carries_full_denominators_and_reasons"),
    "test_te03_7.py::"
    "test_report_renders_the_revised_controls::"
    'for step in funnel["steps"]:': (
        "controls[\"status\"] is still NOT_RUN_BUDGET, so the report never had a MEASURED funnel "
        "row to render",
        "tests/test_contingency_paths.py::"
        "test_the_te03_7_report_shows_measured_funnel_rows_once_they_exist"),
    "test_te03_7.py::"
    "test_report_renders_the_revised_controls::"
    'if step["count"] is not None:': (
        "same NOT_RUN_BUDGET reason",
        "tests/test_contingency_paths.py::"
        "test_the_te03_7_report_shows_measured_funnel_rows_once_they_exist"),
    "test_te03_7.py::"
    "test_report_renders_the_revised_controls::"
    'assert f"| {step[\'step\']} | {step[\'count\']} | {step[\'denominator\']} |"': (
        "same NOT_RUN_BUDGET reason",
        "tests/test_contingency_paths.py::"
        "test_the_te03_7_report_shows_measured_funnel_rows_once_they_exist"),
}


def assertion_lines() -> dict[str, dict[int, str]]:
    targets: dict[str, dict[int, str]] = {}
    for path in sorted((LAB_ROOT / "tests").rglob("test_*.py")):
        lines: dict[int, str] = {}
        source = path.read_text().splitlines()
        tree = ast.parse("\n".join(source))
        owner = _owners(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assert):
                lines[node.lineno] = ("assert", owner.get(node.lineno, "?"),
                                      _snippet(source, node.lineno))
            if isinstance(node, (ast.For, ast.While)) and any(
                    isinstance(n, ast.Assert) for n in ast.walk(node)):
                for stmt in node.body:
                    lines.setdefault(stmt.lineno,
                                     ("loop_body", owner.get(stmt.lineno, "?"),
                                      _snippet(source, stmt.lineno)))
        targets[str(path)] = lines
    return targets


def _owners(tree: ast.AST) -> dict[int, str]:
    """line -> enclosing def name, so a declaration can be keyed by the TEST it is in."""
    out: dict[int, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for line in range(node.lineno, (node.end_lineno or node.lineno) + 1):
                out[line] = node.name
    return out


def _snippet(source: list[str], line: int) -> str:
    """The asserted expression, normalised, as the stable half of the key."""
    text = source[line - 1].strip() if 0 < line <= len(source) else ""
    return " ".join(text.split())[:70]


def stable_key(name: str, owner: str, snippet: str) -> str:
    """`file::test::snippet`.

    The key used to be `file:LINE`, and a line number expires the moment anything
    above it is edited. That fails in two directions: a real declaration silently
    becomes UNDECLARED, and -- worse -- a stale number can land on a DIFFERENT
    assert, which then reads as declared although nobody has looked at it. The
    test name and the asserted text both survive an edit elsewhere in the file.
    """
    return f"{name}::{owner}::{snippet}"


def main() -> int:
    targets = assertion_lines()
    hit: set[tuple[str, int]] = set()
    monitoring = sys.monitoring
    tool = monitoring.PROFILER_ID
    monitoring.use_tool_id(tool, "assertion-vacuity")

    def on_line(code, line_number):
        table = targets.get(code.co_filename)
        if table is None:
            return monitoring.DISABLE
        if line_number in table:
            hit.add((code.co_filename, line_number))
        return None

    monitoring.register_callback(tool, monitoring.events.LINE, on_line)
    monitoring.set_events(tool, monitoring.events.LINE)
    import pytest

    class _Skips:
        """Which tests SKIPPED, and why.

        An assert inside a skipped test did not run because its INPUT is missing,
        not because its branch is impossible. Counting the two together makes a
        phase that has not finished running look like a suite full of checks
        nobody has looked at -- and buries the real ones among them.
        """

        def __init__(self):
            self.reasons: dict[str, str] = {}

        def pytest_runtest_logreport(self, report):
            # ANY phase, not just setup. `pytest.skip()` called inside a test body
            # -- which is how every artifact-dependent test here skips -- reports
            # at `call`, so filtering on `setup` saw zero skips and filed all 107
            # of their assertions as unreachable branches.
            if not report.skipped:
                return
            name = report.nodeid.split("::")[-1].split("[")[0]
            reason = ""
            if isinstance(report.longrepr, tuple) and len(report.longrepr) == 3:
                reason = str(report.longrepr[2])
            self.reasons.setdefault(name, reason.replace("Skipped: ", "") or "skipped")

    skips = _Skips()
    exit_code = pytest.main([str(LAB_ROOT / "tests"), "-q", "--no-header",
                             "-p", "no:cacheprovider"], plugins=[skips])
    monitoring.set_events(tool, 0)
    monitoring.free_tool_id(tool)

    never = []
    self_referential_tracked = 0
    self_referential_reached = 0
    for filename, table in targets.items():
        name = pathlib.Path(filename).name
        for line, (kind, owner, snippet) in sorted(table.items()):
            if owner in SELF_REFERENTIAL_TESTS:
                self_referential_tracked += 1
                if (filename, line) in hit:
                    self_referential_reached += 1
            if (filename, line) not in hit:
                if owner in SELF_REFERENTIAL_TESTS:
                    continue
                key = stable_key(name, owner, snippet)
                reason, exercised = ACCEPTED.get(key, (None, None))
                skipped = owner in skips.reasons
                never.append({"location": f"{name}:{line}", "key": key, "kind": kind,
                              "test": owner, "snippet": snippet,
                              "cause": "SKIPPED_TEST" if skipped else "UNREACHED_BRANCH",
                              "skip_reason": skips.reasons.get(owner),
                              "accepted": reason is not None or skipped,
                              "why_unreachable_here": reason or (
                                  f"the whole test skipped: {skips.reasons.get(owner)}"
                                  if skipped else None),
                              "rule_exercised_by": exercised or (
                                  "the test itself, once its input exists" if skipped else None)})

    undeclared = [n["key"] for n in never if not n["accepted"]]
    skipped_tests = sorted({n["test"]: n["skip_reason"] for n in never
                            if n["cause"] == "SKIPPED_TEST"}.items())
    # A declaration that matches no assert in the suite is itself stale: the test
    # was renamed, the assertion reworded, or the guard deleted. Left unchecked it
    # accumulates silently, which is how the line-number keys rotted.
    every_key = {stable_key(pathlib.Path(f).name, owner, snippet)
                 for f, table in targets.items()
                 for _line, (_kind, owner, snippet) in table.items()}
    stale_declarations = sorted(k for k in ACCEPTED if k not in every_key)
    document = {
        "schema": "crypto_regime_lab.assertion_vacuity_audit.v1",
        "tests_passed": exit_code == 0,
        "assertion_lines_tracked": sum(len(t) for t in targets.values()),
        "assertion_lines_reached": len(hit),
        "self_referential_tracked_lines": self_referential_tracked,
        "self_referential_lines_reached": self_referential_reached,
        "self_referential_ratio_note": ("lines owned by SELF_REFERENTIAL_TESTS are excluded from "
                                        "`never_reached` because measuring them is circular (this "
                                        "audit's own gate reading its own prior output); the same "
                                        "exclusion must apply to any reached-ratio computed over "
                                        "this document, or that ratio silently penalises the suite "
                                        "for the strange loop instead of measuring the suite"),
        "never_reached": never,
        "never_reached_count": len(never),
        "undeclared": undeclared,
        "unreached_because_the_test_skipped": [
            {"test": test, "reason": reason} for test, reason in skipped_tests],
        "skipped_tests": len(skipped_tests),
        "cause_rule": ("an assert inside a SKIPPED test did not run because its input is "
                       "missing, not because its branch is impossible. The two are reported "
                       "separately: counting them together makes a phase mid-run look like a "
                       "suite full of checks nobody has looked at, and buries the real ones"),
        "stale_declarations": stale_declarations,
        "self_referential_exclusions": SELF_REFERENTIAL_TESTS,
        "stale_declaration_rule": ("a declaration that matches no assert in the suite is stale: "
                                   "the test was renamed, the assertion reworded, or the guard "
                                   "deleted. It is reported rather than ignored"),
        "rule": ("an assertion that never runs cannot fail. A guard for a failure the current "
                 "data does not produce is legitimate and stays, but it must be DECLARED with "
                 "where its rule is exercised instead. An undeclared one is a check nobody has "
                 "looked at"),
        "method": ("sys.monitoring LINE events over tests/, recording every assert statement and "
                   "every statement inside a loop that contains one"),
        "declaration_key": ("file::test::asserted-text. A line number expires on any edit above "
                            "it, and a stale one can land on a different assert that then reads "
                            "as declared although nobody reviewed it"),
    }
    (LAB_ROOT / "configs" / "assertion_vacuity_audit.json").write_text(
        json.dumps(document, indent=2) + "\n")

    print(f"\n\nassertion lines tracked : {document['assertion_lines_tracked']}")
    print(f"reached                 : {document['assertion_lines_reached']}")
    print(f"never reached           : {document['never_reached_count']} "
          f"({sum(1 for n in never if n['cause'] == 'SKIPPED_TEST')} inside skipped tests)")
    for record in never:
        if record["cause"] == "SKIPPED_TEST":
            continue
        mark = "declared" if record["accepted"] else "UNDECLARED"
        print(f"   {record['location']:<44} {mark}")
    if skipped_tests:
        print(f"skipped tests           : {len(skipped_tests)}")
        for test, reason in skipped_tests[:8]:
            print(f"   {test:<62} {str(reason)[:40]}")
    print(f"undeclared              : {undeclared or 'none'}")
    print(f"stale declarations      : {stale_declarations or 'none'}")
    return 0 if exit_code == 0 and not undeclared and not stale_declarations else 1


if __name__ == "__main__":
    raise SystemExit(main())
