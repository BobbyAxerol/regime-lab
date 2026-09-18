"""The branches that only run when something is WRONG.

A runtime trace of the whole suite found six assert lines that never execute.
One was a genuine vacuity (fixed at its own site). The other five are
contingency guards: correct, but the current data never reaches them — a
`cohort_runs_invalidated` loop over an empty list, an `else` for a drift state
that is not happening, a stronger conclusion level that was not claimed, an
audit branch for a design that does match.

Each of those is a check whose FAILING path has never been run, so nobody knows
whether it works. Here they are driven with constructed inputs. The point is not
coverage; it is that a guard which has never been seen to fire is a guard nobody
has tested.
"""

from __future__ import annotations

import json

import pytest

from crypto_regime_lab.data.snapshot import classify_source_drift, verify_snapshot


# --- LAB-03: the read-lock's two unexercised branches ---------------------


def _manifest(tmp_path, records):
    return {"snapshot_id": "test_snap", "files": records,
            "ingest_finished_utc": "2026-01-01T00:00:00+00:00", "total_rows": 0}


def _partition(tmp_path, name, frame, *, product="crypto_binance_futures_metrics_5m",
               closed=True, symbol="BTCUSDT"):
    import hashlib

    lab = tmp_path / f"lab_{name}.parquet"
    src = tmp_path / f"src_{name}.parquet"
    frame.to_parquet(lab)
    frame.to_parquet(src)
    digest = hashlib.sha256(lab.read_bytes()).hexdigest()
    return {"product_id": product, "symbol": symbol, "partition": "2021-01",
            "snapshot_path": str(lab), "source_path": str(src), "sha256": digest,
            "closed": closed, "rows": len(frame)}


def test_the_no_drift_branch_reports_unchanged(tmp_path):
    """The `else` at test_lab03_pipeline.py:127 — never taken while drift exists upstream."""
    import pandas as pd

    frame = pd.DataFrame({"time": pd.to_datetime(["2021-01-01"]), "v": [1.0],
                          "ingested_at": pd.to_datetime(["2026-01-01"])})
    manifest = _manifest(tmp_path, [_partition(tmp_path, "clean", frame)])
    verification = verify_snapshot(manifest)
    assert verification["status"] == "UNCHANGED"
    assert verification["closed_partition_drift"] == []
    assert verification["cohort_runs_invalidated"] == []
    assert verification["primary_run_valid"] is True


def test_a_content_revision_actually_invalidates_its_cohort(tmp_path):
    """The loop at test_lab03_pipeline.py:672 — empty while every drift is a re-stamp.

    This is the read-lock's whole purpose, and until now nothing had ever seen it
    invalidate anything.
    """
    import pandas as pd

    original = pd.DataFrame({"time": pd.to_datetime(["2021-01-01 00:00", "2021-01-01 00:05"]),
                             "sum_open_interest": [10.0, 11.0],
                             "ingested_at": pd.to_datetime(["2026-01-01"] * 2)})
    record = _partition(tmp_path, "revised", original)
    # rewrite the SOURCE with a changed measurement
    revised = original.copy()
    revised.loc[1, "sum_open_interest"] = 99.0
    revised.to_parquet(record["source_path"])

    shallow = verify_snapshot(_manifest(tmp_path, [record]))
    assert shallow["status"] == "EXTERNAL_DATA_DRIFT"
    assert shallow["cohort_runs_invalidated"] == ["crypto_binance_futures_metrics_5m"]

    deep = verify_snapshot(_manifest(tmp_path, [record]), deep=True)
    assert deep["status"] == "EXTERNAL_DATA_DRIFT", (
        "a changed measurement must survive the deep classification, not be cleared by it")
    assert len(deep["closed_partition_content_revisions"]) == 1
    assert deep["closed_partition_vintage_restamps"] == []
    for product in deep["cohort_runs_invalidated"]:
        assert any(v["product_id"] == product
                   for v in deep["closed_partition_content_revisions"])
    verdict = classify_source_drift(record)
    assert verdict["classification"] == "CONTENT_REVISION"
    assert verdict["changed_columns"]["sum_open_interest"]["rows_differing"] == 1


def test_a_primary_core_revision_invalidates_the_whole_run(tmp_path):
    """The strongest failure the read-lock can report, and it had never been seen."""
    import pandas as pd

    original = pd.DataFrame({"time": pd.to_datetime(["2021-01-01 00:00", "2021-01-01 00:01"]),
                             "close": [30000.0, 30010.0],
                             "ingested_at": pd.to_datetime(["2026-01-01"] * 2)})
    record = _partition(tmp_path, "core", original,
                        product="crypto_binance_futures_1m")
    revised = original.copy()
    revised.loc[1, "close"] = 40000.0
    revised.to_parquet(record["source_path"])

    deep = verify_snapshot(_manifest(tmp_path, [record]), deep=True)
    assert deep["primary_run_valid"] is False, (
        "a changed close in the perpetual bars must invalidate the primary run")
    assert deep["primary_core_closed_drift"]


def test_a_corrupt_snapshot_copy_is_reported_as_corrupt(tmp_path):
    """SNAPSHOT_CORRUPT — the lab's own bytes moving — had also never been exercised."""
    import pandas as pd

    frame = pd.DataFrame({"time": pd.to_datetime(["2021-01-01"]), "v": [1.0],
                          "ingested_at": pd.to_datetime(["2026-01-01"])})
    record = _partition(tmp_path, "corrupt", frame)
    record["sha256"] = "0" * 64          # the manifest says something else entirely
    verification = verify_snapshot(_manifest(tmp_path, [record]), check_sources=False)
    assert verification["status"] == "SNAPSHOT_CORRUPT"
    assert verification["primary_run_valid"] is False


# --- LAB-04: the audit's and the conclusion's unexercised guards ----------


def test_a_stronger_conclusion_requires_no_blockers_and_a_real_effect(lab_root):
    """test_lab04_legacy_labelling.py:164 — LAB-04 concluded INCONCLUSIVE_SAMPLE, so never ran.

    The guard is what stops a phase from labelling itself with an edge while
    blockers stand. Driven here on constructed records so the rule is known to
    work before a phase ever reaches for the stronger label.
    """
    registry = json.loads((lab_root / "configs" / "hypothesis_registry.json").read_text())
    levels = registry["conclusion_levels"]
    assert "NET_PARAMETER_SELECTION_EDGE" in levels

    def admissible(hypothesis: dict) -> bool:
        if hypothesis["conclusion_level"] != "NET_PARAMETER_SELECTION_EDGE":
            return True
        return (not hypothesis["blockers_preventing_a_stronger_claim"]
                and abs(hypothesis["mean_daily_net_return_difference"])
                >= hypothesis["minimum_economic_effect_per_day"])

    edge_with_blockers = {"conclusion_level": "NET_PARAMETER_SELECTION_EDGE",
                          "blockers_preventing_a_stronger_claim": ["sign reversal in A-VWAP"],
                          "mean_daily_net_return_difference": 1e-3,
                          "minimum_economic_effect_per_day": 6.4e-5}
    assert admissible(edge_with_blockers) is False

    edge_below_threshold = {**edge_with_blockers,
                            "blockers_preventing_a_stronger_claim": [],
                            "mean_daily_net_return_difference": 1e-6}
    assert admissible(edge_below_threshold) is False

    clean_edge = {**edge_with_blockers, "blockers_preventing_a_stronger_claim": [],
                  "mean_daily_net_return_difference": 1e-3}
    assert admissible(clean_edge) is True


def test_a_spec_deviating_design_must_block_the_l045_rows():
    """test_lab04_legacy_labelling.py:350 — never ran because the design does match.

    This is the guard that stopped LAB-04 the first time: a complete matrix built
    with the wrong probe design is not a completed phase. If it silently passed
    when the design deviated, the audit would certify the wrong run.
    """
    def blocked_rows(audit: dict) -> list[str]:
        if audit["primary_matrix_design_matches_spec"]:
            return []
        return [row["task_id"] for row in audit["tasks"] if row["status"] != "DONE"]

    deviating = {
        "primary_matrix_design_matches_spec": False,
        "design_rule": "2 TPE anchors + 1 space-filling + 1 incumbent",
        "tasks": [{"task_id": "L04.5.1", "status": "BLOCKED_DESIGN_MISMATCH"},
                  {"task_id": "L04.6.1", "status": "DONE"}],
    }
    blocked = blocked_rows(deviating)
    assert any(t.startswith("L04.5") for t in blocked), (
        "a spec-deviating design must block the L04.5 rows")

    matching = {**deviating, "primary_matrix_design_matches_spec": True}
    assert blocked_rows(matching) == []


def test_the_real_lab04_audit_still_satisfies_the_guard(lab_root):
    """And the same rule, applied to the artifact that actually exists."""
    path = lab_root / "configs" / "lab04_task_audit.json"
    if not path.is_file():
        pytest.skip("run scripts/audit_lab04.py")
    audit = json.loads(path.read_text())
    assert audit["primary_matrix_design_matches_spec"] is True
    assert all(row["status"] == "DONE" for row in audit["tasks"])


# --- the vacuity audit itself must stay honest ----------------------------


def test_no_assertion_in_the_suite_is_unreached_without_a_declared_reason(lab_root):
    """Reading tests does not reveal a check that cannot fail; running them does.

    `scripts/audit_assertion_vacuity.py` traces the whole suite and records every
    assert line never reached. An unreached assertion is not automatically wrong
    — a guard for a failure the current data does not produce is correct — but it
    must be DECLARED, with where its rule is exercised instead. This test fails
    when that list grows silently.
    """
    path = lab_root / "configs" / "assertion_vacuity_audit.json"
    if not path.is_file():
        pytest.skip("run scripts/audit_assertion_vacuity.py")
    audit = json.loads(path.read_text())
    assert audit["undeclared"] == [], (
        f"these assertions never run and nobody has said why: {audit['undeclared']}")
    assert audit.get("stale_declarations") == [], (
        f"these declarations match no assert in the suite: {audit.get('stale_declarations')}")
    for record in audit["never_reached"]:
        assert record["why_unreachable_here"], record["location"]
        assert record["rule_exercised_by"], (
            f"{record['location']} is declared unreachable but names nothing that DOES exercise "
            "its rule")
    # a skipped test is a MISSING INPUT, not an unreachable branch, and each one
    # has to say which artifact it is waiting for
    for record in audit.get("unreached_because_the_test_skipped", []):
        assert record["reason"], f"{record['test']} skipped without a reason"
    branch_lines = [r for r in audit["never_reached"] if r["cause"] == "UNREACHED_BRANCH"]
    # Lines owned by SELF_REFERENTIAL_TESTS (this gate's own body) are excluded from
    # `never_reached` because measuring them is circular -- this run only gets past
    # its own earlier asserts once THIS run's artifact already says they pass. The
    # same exclusion belongs in the denominator here, or the ratio penalises the
    # suite for that strange loop instead of measuring the suite.
    self_ref_tracked = audit.get("self_referential_tracked_lines", 0)
    self_ref_reached = audit.get("self_referential_lines_reached", 0)
    reached = ((audit["assertion_lines_reached"] - self_ref_reached)
               / (audit["assertion_lines_tracked"] - self_ref_tracked
                  - len(audit["never_reached"]) + len(branch_lines)))
    assert reached > 0.99, (
        f"only {reached:.1%} of the assertions in tests that actually ran were reached")


def test_a_ledger_verdict_over_an_empty_population_is_labelled_vacuous():
    """`all(...)` over nothing is True and reads like a verified claim.

    LAB-06 reported `every_switch_has_supporting_episodes: True` across a run
    with ZERO switches, and the report quoted it as evidence that every switch
    carried its evidence.
    """
    from crypto_regime_lab.policy.decision import summarize_ledger

    class FakeDecision:
        def __init__(self, decision, reason="because", episodes=(), cutoff="2021-01-01"):
            self.decision = decision
            self.reason = reason
            self.supporting_episodes = list(episodes)
            self.data_cutoff = cutoff
            self.bank_cutoff = cutoff

        def as_record(self):
            return {"decision": self.decision}

    no_switches = summarize_ledger([FakeDecision("KEEP_INCUMBENT") for _ in range(5)])
    verdict = no_switches["verdicts"]["every_switch_has_supporting_episodes"]
    assert verdict["holds"] is True
    assert verdict["vacuous"] is True and verdict["checked"] == 0
    assert "verifies nothing" in verdict["reading"]
    assert no_switches["vacuous_verdicts"] == ["every_switch_has_supporting_episodes"]
    # the verdicts that DID have a population must not be labelled vacuous
    assert no_switches["verdicts"]["every_decision_has_a_reason"]["checked"] == 5
    assert no_switches["verdicts"]["every_decision_has_a_reason"]["vacuous"] is False

    with_switch = summarize_ledger([FakeDecision("KEEP_INCUMBENT"),
                                    FakeDecision("SWITCH_READY", episodes=["e1", "e2"])])
    supported = with_switch["verdicts"]["every_switch_has_supporting_episodes"]
    assert supported["vacuous"] is False and supported["checked"] == 1
    assert with_switch["vacuous_verdicts"] == []

    unsupported = summarize_ledger([FakeDecision("SWITCH_READY", episodes=[])])
    assert unsupported["verdicts"]["every_switch_has_supporting_episodes"]["holds"] is False, (
        "a switch with no supporting episodes must fail the verdict, not pass it vacuously")


# --- what a mutation test found unguarded ---------------------------------
#
# Breaking each invariant below and re-running the suite produced NO failure,
# which means the claim was recorded and never checked. The exit-gate claims
# were the worst: an audit could report every clause DONE with empty evidence,
# and a coverage file could mark a requirement COVERED with no tests.


@pytest.fixture(scope="module")
def trace(lab_root):
    path = lab_root / "configs" / "lab07_continuous_trace.json"
    if not path.is_file():
        pytest.skip("run scripts/run_lab07.py")
    return json.loads(path.read_text())


def test_the_recorded_account_never_reset_and_was_never_spliced(trace):
    """T56 was verified on a fresh run but never on the artifact the report quotes."""
    account = trace["continuous_account"]
    assert account["account_resets"] == 0
    assert account["spliced_from_independent_runs"] is False
    assert account["single_engine_pass"] is True
    assert account["bars"] == len(account["version_by_bar"]) if "version_by_bar" in account \
        else account["bars"] > 0


def test_the_recorded_exit_fixed_point_converged(trace):
    """An unconverged run means the adapter was driven by exits the account never got."""
    account = trace["continuous_account"]
    assert account["exit_fixed_point_converged"] is True
    assert account["protective_exits"] == account["applied_exit_count"]


@pytest.mark.parametrize("phase", ["04", "05", "06", "07"])
def test_no_audit_clause_is_done_without_evidence(lab_root, phase):
    """A phase audit could report every clause DONE with an empty evidence string.

    That is the single most load-bearing claim in the lab — every phase report
    quotes its audit — and nothing checked it.
    """
    path = lab_root / "configs" / f"lab{phase}_task_audit.json"
    if not path.is_file():
        pytest.skip(f"run scripts/audit_lab{phase}.py")
    audit = json.loads(path.read_text())
    rows = audit["tasks"]
    assert rows, "an audit with no rows passes trivially"
    for row in rows:
        identifier = row.get("clause_id") or row.get("task_id") or row.get("id")
        if row["status"] == "DONE":
            evidence = row.get("evidence") or row.get("artifact") or ""
            assert evidence.strip(), (
                f"lab{phase} clause {identifier} is DONE with no evidence pointer")
    assert audit["tasks_done"] == sum(1 for r in rows if r["status"] == "DONE"), (
        "the headline count disagrees with the rows it summarises")


def test_no_requirement_is_covered_without_tests(lab_root):
    """The coverage file could mark a requirement COVERED with an empty test list."""
    path = lab_root / "configs" / "acceptance_test_coverage.json"
    if not path.is_file():
        pytest.skip("run scripts/update_coverage_lab07.py")
    coverage = json.loads(path.read_text())
    for record in coverage["requirements"]:
        if record["status"] in ("COVERED", "PARTIAL"):
            assert record.get("tests"), (
                f"{record['id']} is {record['status']} with no tests listed")
            for node in record["tests"]:
                assert "::" in node, f"{record['id']} lists {node!r}, which is not a test node"
    counted = {}
    for record in coverage["requirements"]:
        counted[record["status"]] = counted.get(record["status"], 0) + 1
    assert counted == coverage["counts"], "the headline counts disagree with the rows"


def test_a_verdict_cannot_silently_lose_its_population(lab_root):
    """`checked` dropping to 0 turns a verified claim into a vacuous one.

    A verdict that was checked over 6,566 decisions and later reports 0 has
    stopped verifying anything, and `holds: True` would read the same either way.
    """
    path = lab_root / "configs" / "lab06_decision_ledger.json"
    if not path.is_file():
        pytest.skip("run scripts/run_response_policy.py")
    ledger = json.loads(path.read_text())
    verdicts = ledger["verdicts"]
    for name, verdict in verdicts.items():
        assert verdict["vacuous"] == (verdict["checked"] == 0), (
            f"{name} labels itself vacuous={verdict['vacuous']} with checked={verdict['checked']}")
        assert verdict["holds"] is True, f"{name} does not hold: {verdict}"
    # the two decision-wide verdicts must be checked over EVERY decision
    for name in ("every_decision_has_a_reason", "every_decision_records_its_cutoffs"):
        assert verdicts[name]["checked"] == ledger["decisions"], (
            f"{name} checked {verdicts[name]['checked']} of {ledger['decisions']} decisions")
        assert verdicts[name]["vacuous"] is False
    assert ledger["vacuous_verdicts"] == sorted(
        n for n, v in verdicts.items() if v["vacuous"])
    # the headline field and its own detailed verdict must agree. They are two
    # copies of one fact, and a mutation to the headline alone went unnoticed:
    # a report quoting `every_decision_has_a_reason` would print False while the
    # verdict beside it said True.
    for name, verdict in verdicts.items():
        assert ledger[name] == verdict["holds"], (
            f"{name} is {ledger[name]} at the top level and {verdict['holds']} in its verdict")


def test_the_guard_strength_audit_found_no_unguarded_invariant(lab_root):
    """Passing tests say the claims hold; they do not say the claims are CHECKED.

    `scripts/audit_guard_strength.py` breaks each recorded invariant in turn and
    re-runs the whole suite. Its first run caught 6 of 13 — seven claims were
    recorded and never verified, including that a phase audit could report every
    clause DONE with empty evidence.
    """
    path = lab_root / "configs" / "guard_strength_audit.json"
    if not path.is_file():
        pytest.skip("run scripts/audit_guard_strength.py")
    audit = json.loads(path.read_text())
    assert audit["mutations_total"] >= 13, "the mutation set shrank"
    assert audit["unguarded_invariants"] == [], (
        f"these recorded claims survive being falsified: {audit['unguarded_invariants']}")
    assert "ENTIRE suite" in audit["method"], (
        "running a guessed subset is how the first version missed guards that existed")
    for mutation in audit["mutations"]:
        assert mutation["caught"], mutation["invariant"]
        assert mutation["first_failure"], (
            f"{mutation['invariant']} is marked caught but names no failing test")


def test_a_vacuity_declaration_survives_an_edit_above_it():
    """The vacuity audit's accepted branches are keyed by test and text, not by line.

    A line-number key expires on any edit above it, in two directions: a real
    declaration silently becomes UNDECLARED, and — worse — a stale number can
    land on a DIFFERENT assert, which then reads as declared although nobody
    reviewed it. Three of five declarations had drifted off their lines by the
    time this was found.
    """
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import audit_assertion_vacuity as A

    key = A.stable_key("test_x.py", "test_thing", 'assert record["owner"] not in landed')
    assert key == 'test_x.py::test_thing::assert record["owner"] not in landed'
    assert ":LINE" not in key and not any(part.isdigit() for part in key.split("::"))

    # every declaration still matches an assert that exists in the suite
    targets = A.assertion_lines()
    present = {A.stable_key(Path(f).name, owner, snippet)
               for f, table in targets.items()
               for _line, (_kind, owner, snippet) in table.items()}
    stale = sorted(k for k in A.ACCEPTED if k not in present)
    assert stale == [], f"declarations that match no assert in the suite: {stale}"
    assert len(A.ACCEPTED) >= 5, "the declaration set looks truncated"

    # and a declaration carries BOTH a reason and where the rule is exercised
    for declaration, (reason, exercised) in A.ACCEPTED.items():
        assert reason and len(reason) > 20, declaration
        assert exercised and "::" in exercised, declaration


def test_the_claim_rule_can_reach_every_verdict_it_declares():
    """The branches LAB-09's own result never took.

    The confirmation ruled every contribution OUT below the minimum economic
    effect, so `claim()`'s SUPPORTED and INCONCLUSIVE branches never ran, and nor
    did the NOT_MEASURED one. An untaken branch in a decision rule is exactly
    where a rule can be wrong without anyone noticing, so all three are driven
    here on synthetic intervals.
    """
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import analyse_lab09_confirmation as A

    minimum = 6.4e-05

    def contribution(lower, upper, status="OK"):
        uncertainty = {"contrasts": {"B-A": {
            "status": status, "point_estimate": (lower + upper) / 2,
            "ci_lower": lower, "ci_upper": upper, "p_value": 0.5,
            "holm_adjusted_p": 0.5, "baseline_is_not_untouched": True,
            "baseline_caveat": "test"}}}
        confirmation = {"cells": [], "window": ["2024-01-01", "2026-08-31"],
                        "cells_not_ready": 0, "cells_planned": 20}
        reconciliation = {"financial_identity": {"all_hold": True,
                                                 "cost_binding_is_a_finding": False}}
        unlock = {"holdout_status": "CLEAN"}
        registry = ["DESCRIPTIVE_VALUE", "CONDITIONAL_RESPONSE_EVIDENCE",
                    "NET_PARAMETER_SELECTION_EDGE", "NET_TIMING_EDGE", "NET_POLICY_EDGE",
                    "NO_INCREMENTAL_VALUE", "INCONCLUSIVE_SAMPLE", "FAILED_VALIDITY"]
        report = A.claim(confirmation, uncertainty, reconciliation, None, None, None,
                         unlock, minimum, registry,
                         accounting={"severity": "MATERIAL"})
        return report

    # 1. the whole interval above the minimum -> SUPPORTED, and an edge level
    supported = contribution(minimum * 2, minimum * 3)
    assert supported["contributions"]["SELECTION"]["verdict"] == "SUPPORTED"
    assert supported["conclusion_level"].startswith("NET_"), supported["conclusion_level"]

    # 2. an interval straddling the minimum -> INCONCLUSIVE, never a negative result
    straddling = contribution(-minimum, minimum * 2)
    assert straddling["contributions"]["SELECTION"]["verdict"] == "INCONCLUSIVE"
    assert straddling["conclusion_level"] == "INCONCLUSIVE_SAMPLE"

    # 3. the whole interval below -> RULED_OUT, which IS a negative result
    ruled_out = contribution(-minimum * 2, minimum / 2)
    assert ruled_out["contributions"]["SELECTION"]["verdict"] == "RULED_OUT"

    # 4. a contrast with no interval -> NOT_MEASURED, and it must say why
    missing = contribution(0.0, 0.0, status="NO_PAIRED_SERIES")
    entry = missing["contributions"]["SELECTION"]
    assert entry["verdict"] == "NOT_MEASURED"
    assert entry["reason"], "NOT_MEASURED without a reason reads like a negative result"

    # 5. and a MAJOR accounting error overrides all of it
    uncertainty = {"contrasts": {"B-A": {
        "status": "OK", "point_estimate": minimum * 2, "ci_lower": minimum * 2,
        "ci_upper": minimum * 3, "p_value": 0.01, "holm_adjusted_p": 0.01}}}
    overridden = A.claim(
        {"cells": [], "window": ["2024-01-01", "2026-08-31"], "cells_not_ready": 0,
         "cells_planned": 20},
        uncertainty,
        {"financial_identity": {"all_hold": True, "cost_binding_is_a_finding": True}},
        None, None, None, {"holdout_status": "CLEAN"}, minimum,
        ["NET_PARAMETER_SELECTION_EDGE", "FAILED_VALIDITY"],
        accounting={"severity": "MAJOR"})
    assert overridden["conclusion_level"] == "FAILED_VALIDITY", (
        "a MAJOR accounting error must override an otherwise supported edge")


# --- RF-04/RF-05/TE-03.7: guards this run's real data never had to use ------
#
# All five below were found UNDECLARED by scripts/audit_assertion_vacuity.py
# after RA-04 (2026-09-18): 21 assert/loop-body lines across four phase test
# files, never reached because the real artifacts they check never hit the
# branch. Each is a real guard blocked by real CURRENT data, not dead code --
# driven here with constructed inputs, the same way the LAB-03/04 guards above
# were, rather than merely declared.


def test_a_not_run_placebo_must_carry_a_reason():
    """test_rf04_decay_and_controls.py:177 -- never taken because RF-04's
    placebo control actually ran (status RUN, not REGISTERED_NOT_RUN); guide
    RA07.3 requires a not-run placebo to be recorded as a missing control
    with a reason, never silently dropped.
    """
    def check(placebo: dict) -> None:
        assert placebo["status"] in ("RUN", "REGISTERED_NOT_RUN")
        if placebo["status"] == "REGISTERED_NOT_RUN":
            assert placebo["reason"], "a not-run placebo needs a reason"

    with pytest.raises(AssertionError):
        check({"status": "REGISTERED_NOT_RUN", "reason": ""})
    check({"status": "REGISTERED_NOT_RUN", "reason": "budget exhausted before the placebo cutoff"})
    check({"status": "RUN", "reason": ""})


def test_a_non_run_coverage_cell_must_name_why():
    """test_rf04_scaling.py:176,179 -- never taken because RF-04's 20 cells
    are only ever RUN_VALID or BLOCKED_CAPABILITY (measured:
    Counter({'RUN_VALID': 10, 'BLOCKED_CAPABILITY': 10}) in cell_coverage.json)
    -- no cell in this pilot ran out of budget mid-attempt or was skipped for
    any other un-run reason.
    """
    def check(cell: dict) -> None:
        if cell["coverage_status"] == "NOT_RUN_BUDGET":
            assert "budget" in cell["reason"].lower(), (
                f"{cell['cell']} is NOT_RUN_BUDGET without a budget reason")
        if cell["coverage_status"] in ("NOT_RUN", "NOT_RUN_BUDGET"):
            assert cell["reason"].strip(), f"{cell['cell']} has no non-run reason"

    with pytest.raises(AssertionError):
        check({"cell": "X/Y", "coverage_status": "NOT_RUN_BUDGET", "reason": "capability gap"})
    check({"cell": "X/Y", "coverage_status": "NOT_RUN_BUDGET", "reason": "ran out of budget"})
    with pytest.raises(AssertionError):
        check({"cell": "X/Y", "coverage_status": "NOT_RUN", "reason": ""})
    check({"cell": "X/Y", "coverage_status": "NOT_RUN", "reason": "insufficient history"})


def test_a_positive_within_scope_status_needs_ci_above_mde_and_holm_significance():
    """test_rf05_claims.py:159,161,167,168 -- never taken because no RF-05
    contrast is ever POSITIVE_WITHIN_SCOPE (guide A16: "the bounded pilot may
    never record a POSITIVE economic status"). The guard exists to catch a
    FUTURE run that tries to report one without clearing both bars; it has
    never been exercised because RF-05's own honest result kept it cold.
    """
    mde_bps = 0.03709428129829986

    def check(entry: dict) -> None:
        if entry["statistical_status"] == "POSITIVE_WITHIN_SCOPE":
            stats = entry.get("paired_daily_difference") or {}
            holm = entry.get("holm_adjusted_p")
            assert stats.get("ci95_low_bps") is not None and stats["ci95_low_bps"] > mde_bps, (
                "claims POSITIVE without a CI above the MDE")
            assert holm is not None and holm < 0.05, (
                "claims POSITIVE without a Holm-adjusted p below 0.05")
            assert entry.get("holm_significant") is True
            assert entry.get("mde_cleared") is True

    # a CI that does not clear the MDE must be refused
    with pytest.raises(AssertionError):
        check({"statistical_status": "POSITIVE_WITHIN_SCOPE",
              "paired_daily_difference": {"ci95_low_bps": -0.1}, "holm_adjusted_p": 0.01,
              "holm_significant": True, "mde_cleared": True})
    # a CI above the MDE but a Holm-adjusted p that fails multiplicity must also be refused
    with pytest.raises(AssertionError):
        check({"statistical_status": "POSITIVE_WITHIN_SCOPE",
              "paired_daily_difference": {"ci95_low_bps": mde_bps + 0.1}, "holm_adjusted_p": 0.20,
              "holm_significant": True, "mde_cleared": True})
    # both bars cleared -> allowed
    check({"statistical_status": "POSITIVE_WITHIN_SCOPE",
          "paired_daily_difference": {"ci95_low_bps": mde_bps + 0.1}, "holm_adjusted_p": 0.01,
          "holm_significant": True, "mde_cleared": True})
    # a non-POSITIVE status is never held to the MDE/Holm bars at all
    check({"statistical_status": "INCONCLUSIVE", "paired_daily_difference": {}, "holm_adjusted_p": None})


def test_a_measured_te03_7_funnel_carries_full_denominators_and_reasons():
    """test_te03_7.py:99-110 -- the MEASURED branch of
    test_measured_funnels_carry_denominators_and_reasons never ran: TE-03.7's
    controls funnel is still NOT_RUN_BUDGET (TE02-PILOT-R03 ledger has
    ~106442s left as of 2026-09-18; the 10-shard controls run has not been
    given its remaining budget). Real code waiting for a real future run, not
    dead code -- driven here against the documented step schema so the rule
    is known to work before that run lands.
    """
    funnel_steps = {"valid_observations", "triggers", "searches", "different_params",
                    "activated", "different_orders"}

    def step(name: str, count, denominator, reason=None) -> dict:
        return {"step": name, "rule": "measured", "count": count,
               "denominator": denominator, "denominator_reason": reason}

    def check(by_condition: dict) -> None:
        assert by_condition, "no condition present"
        for funnel in by_condition.values():
            assert funnel["status"] == "MEASURED"
            assert {row["step"] for row in funnel["steps"]} == funnel_steps
            for row in funnel["steps"]:
                assert row.get("rule")
                assert row["count"] is not None, f"{funnel['condition']}/{row['step']} lacks a measured count"
                assert isinstance(row["count"], int) and row["count"] >= 0
                assert isinstance(row["denominator"], int)
                assert row["count"] <= row["denominator"]
                if row["denominator"] == 0:
                    assert row["denominator_reason"]

    valid = {"condition": "NULL_STATIONARY", "status": "MEASURED",
             "steps": [step(name, 3, 10) for name in funnel_steps]}
    check({"NULL_STATIONARY": valid})

    with pytest.raises(AssertionError):  # a missing step must be refused
        check({"NULL_STATIONARY": {**valid,
                                    "steps": [step(n, 3, 10) for n in funnel_steps if n != "triggers"]}})
    with pytest.raises(AssertionError):  # count > denominator must be refused
        check({"NULL_STATIONARY": {**valid,
                                    "steps": [step(n, 99, 10) if n == "searches" else step(n, 3, 10)
                                             for n in funnel_steps]}})
    with pytest.raises(AssertionError):  # a zero denominator with no reason must be refused
        check({"NULL_STATIONARY": {**valid,
                                    "steps": [step(n, 0, 0) if n == "activated" else step(n, 3, 10)
                                             for n in funnel_steps]}})


def test_the_te03_7_report_shows_measured_funnel_rows_once_they_exist():
    """test_te03_7.py:196-198 -- never ran because controls["status"] is
    still NOT_RUN_BUDGET, so the report never had a MEASURED funnel row to
    render. Driven here against the exact markdown-row format the production
    test checks for.
    """
    def check(controls: dict, report: str) -> None:
        assert controls["status"] in report
        if controls["status"] != "NOT_RUN_BUDGET":
            for funnel in controls["full_path_funnels_by_condition"].values():
                for row in funnel["steps"]:
                    if row["count"] is not None:
                        assert f"| {row['step']} | {row['count']} | {row['denominator']} |" in report

    controls = {"status": "FULL_PATH_STRUCTURAL_CONTROL_COMPLETED",
               "full_path_funnels_by_condition": {"NULL_STATIONARY": {"steps": [
                   {"step": "triggers", "count": 7, "denominator": 40},
                   {"step": "searches", "count": None, "denominator": None}]}}}

    check(controls, "FULL_PATH_STRUCTURAL_CONTROL_COMPLETED\n| triggers | 7 | 40 |\n")
    with pytest.raises(AssertionError):  # the MEASURED row is missing from the report
        check(controls, "FULL_PATH_STRUCTURAL_CONTROL_COMPLETED\n")
