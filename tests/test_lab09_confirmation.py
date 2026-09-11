"""LAB-09 — the frozen confirmation, checked against its own artifacts.

Tests that need a run are skipped until it exists, and the assertion-vacuity
audit reports any assert line that never executed, so a skip cannot quietly
become a pass.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

LAB_ROOT = Path(__file__).resolve().parent.parent
CONFIGS = LAB_ROOT / "configs"
sys.path.insert(0, str(LAB_ROOT / "scripts"))


def load(name: str, hint: str):
    path = CONFIGS / name
    if not path.is_file():
        pytest.skip(f"run {hint}")
    return json.loads(path.read_text())


# ------------------------------------------------------------------ L09.1
def test_the_unlock_is_recorded_before_the_confirmation_run():
    unlock = load("lab09_confirmation_spec.json", "scripts/unlock_lab09_confirmation.py")
    protocol = json.loads((CONFIGS / "lab08_pilot_protocol.json").read_text())
    assert protocol["frozen_at_utc"] < unlock["unlocked_at_utc"], (
        "the protocol has to be frozen before the interval is unlocked, or the design could "
        "still move once a result is visible")


def test_the_unlock_precedes_the_confirmation_run():
    unlock = load("lab09_confirmation_spec.json", "scripts/unlock_lab09_confirmation.py")
    results = load("lab09_confirmation_results.json", "scripts/run_lab09_confirmation.py")
    assert results["stamp_ordering"]["unlock_precedes_run"] is True
    assert unlock["unlocked_at_utc"] < results["stamp_ordering"]["run_started_at_utc"]


def test_the_holdout_status_is_stated_rather_than_implied():
    unlock = load("lab09_confirmation_spec.json", "scripts/unlock_lab09_confirmation.py")
    assert unlock["holdout_status"] == "NESTED_RETROSPECTIVE"
    assert "presets" in unlock["why_not_a_clean_holdout"]
    assert unlock["prospective_protocol"]["not_self_executed"] is True


def test_the_unlock_names_the_phases_it_checked_and_what_it_found():
    """An unlock that says 'unused' without naming what it looked at proves nothing."""
    unlock = load("lab09_confirmation_spec.json", "scripts/unlock_lab09_confirmation.py")
    checked = unlock["prior_access_audit"]["checked"]
    assert len(checked) >= 4
    assert all("artifact" in row for row in checked)
    assert unlock["unused_by_this_lab"] == (
        not unlock["prior_access_audit"]["any_phase_read_the_outer_window"])


# ------------------------------------------------------------------ L09.2
def test_the_confirmation_runs_the_same_matrix():
    results = load("lab09_confirmation_results.json", "scripts/run_lab09_confirmation.py")
    protocol = json.loads((CONFIGS / "lab08_pilot_protocol.json").read_text())
    assert results["cells_planned"] == protocol["primary_matrix"]["total"] == 20
    assert results["registered_contrasts"] == protocol["registered_contrasts"]
    assert results["seeds"] == protocol["seeds"]
    for cell in results["cells"]:
        if cell["status"] != "NOT_READY":
            continue
        for arm in cell["arms"].values():
            assert arm["net_return"] is None, (
                "a blocked cell carries null metrics. A PnL of 0 would bias every aggregate "
                "that averages over cells")


def test_only_the_first_cutoff_moved_between_development_and_confirmation():
    """The calendar is the frozen calendar, relocated -- not a different calendar."""
    from crypto_regime_lab.experiments import calendar_baseline as CB

    results = load("lab09_confirmation_results.json", "scripts/run_lab09_confirmation.py")
    spec = results["calendar_spec"]
    assert spec["changed_from_development"] == ["first_cutoff"]
    assert spec["train_days"] == CB.CALENDAR.train_days
    assert spec["test_days"] == CB.CALENDAR.test_days
    assert spec["folds"] == CB.CALENDAR.folds
    assert spec["inner_episodes"] == CB.CALENDAR.inner_episodes
    assert spec["first_cutoff"] != CB.CALENDAR.first_cutoff


def test_no_module_changed_while_the_run_was_in_flight():
    results = load("lab09_confirmation_results.json", "scripts/run_lab09_confirmation.py")
    guard = results["no_human_adjustment"]
    assert guard["checked"] is True
    assert guard["unchanged_during_run"] is True, guard["changed"]
    assert guard["modules_hashed"] >= 8


def test_a_mid_run_edit_is_detected(tmp_path, monkeypatch):
    """The no-human-adjustment guard has to be able to fire.

    A hash comparison that never sees a difference is indistinguishable from one
    that compares a constant to itself.
    """
    import run_lab09_confirmation as R

    watched = tmp_path / "module.py"
    watched.write_text("x = 1\n")
    monkeypatch.setattr(R, "LAB_ROOT", tmp_path)
    monkeypatch.setattr(R, "WATCHED", ["module.py"])
    before = R.code_state()
    watched.write_text("x = 2\n")
    after = R.code_state()
    assert before != after
    assert sorted(k for k in before if before[k] != after.get(k)) == ["module.py"]


def test_every_watched_module_exists():
    import run_lab09_confirmation as R

    missing = [name for name in R.WATCHED if not (R.LAB_ROOT / name).is_file()]
    assert missing == [], f"the run guard watches files that do not exist: {missing}"


def test_the_account_window_is_declared_as_a_subset_with_its_reason():
    """The interval reaches further than the account does, and that is stated."""
    unlock = load("lab09_confirmation_spec.json", "scripts/unlock_lab09_confirmation.py")
    results = load("lab09_confirmation_results.json", "scripts/run_lab09_confirmation.py")
    assert results["window"][0] == unlock["interval"]["start"]
    assert results["window"][1] <= unlock["interval"]["end"]
    if results["window"][1] < unlock["interval"]["end"]:
        assert "panel" in results["window_note"]


# ------------------------------------------------------------------ L09.3
def test_the_contrast_family_is_the_registered_one():
    uncertainty = load("lab09_uncertainty.json", "scripts/analyse_lab09_confirmation.py")
    protocol = json.loads((CONFIGS / "lab08_pilot_protocol.json").read_text())
    assert uncertainty["holm"]["family"] == protocol["registered_contrasts"]
    assert "E-B" in uncertainty["holm"]["excluded_from_family"]
    assert "E-B" in uncertainty["exploratory"]["contrasts"]


def test_every_interval_reports_its_episode_counts_and_concentration():
    uncertainty = load("lab09_uncertainty.json", "scripts/analyse_lab09_confirmation.py")
    measured = [r for r in uncertainty["contrasts"].values() if r.get("status") == "OK"]
    assert measured, "no contrast produced an interval"
    for record in measured:
        assert record["episodes"]["union_days"] > 0
        assert record["concentration"]["days"] > 0
        assert record["block_length_sensitivity"]


def test_the_block_length_came_from_development():
    uncertainty = load("lab09_uncertainty.json", "scripts/analyse_lab09_confirmation.py")
    replay = load("lab09_development_replay.json", "scripts/replay_lab08_development.py")
    assert uncertainty["block_length_days"] == replay["block_length_calibration"]["block_length"]
    assert replay["window"] == ["2021-01-01", "2023-12-31"]


# ------------------------------------------------------------------ L09.6
def test_the_cash_identity_closes_on_every_arm():
    reconciliation = load("lab09_reconciliation.json", "scripts/analyse_lab09_confirmation.py")
    identity = reconciliation["financial_identity"]
    assert identity["arms_checked"] > 0
    assert identity["all_hold"] is True, identity["per_arm"]


def test_the_fee_binding_defect_is_reported_not_absorbed():
    """The measured one-way rate is compared to the registered one, and disclosed."""
    binding = load("cost_binding_verification.json", "scripts/verify_cost_binding.py")
    assert binding["measurement"]["status"] == "MEASURED"
    assert binding["measurement"]["cash_identity"]["holds"] is True
    if not binding["verdict"]["binding_charges_the_registered_rate"]:
        assert binding["verdict"]["finding"]
        assert binding["verdict"]["direction"]
        reconciliation = load("lab09_reconciliation.json",
                              "scripts/analyse_lab09_confirmation.py")
        assert reconciliation["financial_identity"]["cost_binding_is_a_finding"] is True
        claim = load("lab09_claim_report.json", "scripts/analyse_lab09_confirmation.py")
        assert any(b.startswith("ACCOUNTING") for b in claim["blockers"]), (
            "a measured accounting defect has to reach the claim, not stop at the "
            "reconciliation artifact")


def test_the_objective_recomputes_from_its_components():
    reconciliation = load("lab09_reconciliation.json", "scripts/analyse_lab09_confirmation.py")
    objective = reconciliation["objective_recomputation"]
    assert objective["scores_checked"] > 0
    assert objective["all_match"] is True, objective["max_difference"]


def test_every_bar_is_attributed_to_a_parameter_version():
    reconciliation = load("lab09_reconciliation.json", "scripts/analyse_lab09_confirmation.py")
    lifecycle = reconciliation["parameter_version_lifecycle"]
    assert lifecycle["arms_checked"] > 0
    assert lifecycle["every_bar_attributed"] is True


def test_the_audits_are_still_there():
    reconciliation = load("lab09_reconciliation.json", "scripts/analyse_lab09_confirmation.py")
    audits = reconciliation["audits_retained"]
    assert audits["all_present"] is True
    assert audits["fast_profile_used"] is False


# ------------------------------------------------------------------ L09.7
def test_the_conclusion_level_is_in_the_registered_vocabulary():
    claim = load("lab09_claim_report.json", "scripts/analyse_lab09_confirmation.py")
    registry = json.loads((CONFIGS / "hypothesis_registry.json").read_text())
    assert claim["conclusion_level"] in registry["conclusion_levels"]
    assert claim["conclusion_vocabulary"] == registry["conclusion_levels"]


def test_the_five_contributions_are_judged_separately():
    claim = load("lab09_claim_report.json", "scripts/analyse_lab09_confirmation.py")
    assert set(claim["contributions"]) == {"DESCRIPTIVE", "PREDICTIVE", "SELECTION",
                                           "TIMING", "POLICY"}
    for name, entry in claim["contributions"].items():
        assert entry.get("verdict"), f"{name} carries no verdict"
        assert entry.get("question"), f"{name} does not say what it was asking"


def test_a_missing_measurement_is_never_reported_as_a_negative_result():
    """NOT_MEASURED and NOT_SUPPORTED are different answers.

    Collapsing them is the defect this lab has found in every phase: a check that
    could not run looking exactly like a check that ran and found nothing.
    """
    claim = load("lab09_claim_report.json", "scripts/analyse_lab09_confirmation.py")
    for name, entry in claim["contributions"].items():
        if entry["verdict"] == "NOT_MEASURED":
            assert entry.get("reason"), f"{name} is NOT_MEASURED without saying why"


def test_no_report_claims_a_proven_fund_grade_alpha():
    claim = load("lab09_claim_report.json", "scripts/analyse_lab09_confirmation.py")
    assert claim["forbidden"]["fund_grade_alpha_proven"] is False
    report = LAB_ROOT / "reports" / "lab09_report.md"
    if report.is_file():
        text = report.read_text().lower()
        for phrase in ("fund-grade alpha proven", "proven fund-grade",
                       "production ready", "guaranteed"):
            assert phrase not in text, f"the report contains {phrase!r}"


def test_no_untested_cell_is_presented_as_evidence():
    """T62 — a cell that never ran is masked, never shown as a result."""
    results = load("lab09_confirmation_results.json", "scripts/run_lab09_confirmation.py")
    for cell in results["cells"]:
        if cell["status"] == "RUN":
            continue
        assert cell.get("reason"), f"{cell['alpha_id']}/{cell['symbol']} is blocked without a reason"
        for arm in cell["arms"].values():
            assert arm["net_return"] is None
            assert arm["status"] != "RUN"


def test_the_scope_of_the_conclusion_is_explicit():
    claim = load("lab09_claim_report.json", "scripts/analyse_lab09_confirmation.py")
    scope = claim["scope"]
    assert scope["symbols"] >= 1 and scope["alphas_run"] >= 1
    assert scope["interval"] == claim.get("scope", {})["interval"]
    for token in ("no-funding", "not about crypto"):
        assert token in scope["statement"]


def test_the_descriptive_claim_rests_on_an_in_interval_window():
    """The fitter's own ablation for this role is computed on development data.

    `fit_regime_model.py` runs guide 8.3's ablation on the FIRST cutoff's
    training window, because that is where LAB-05 chose K. For the confirmation
    role the first cutoff is 2024-01-01 and its training memory is the 365 days
    BEFORE it -- development. A descriptive claim about the confirmation interval
    cannot rest on that artifact, so it rests on this one.
    """
    ablation = load("lab09_group_ablation.json", "scripts/ablate_lab09_states.py")
    assert ablation["symbols_measured"] > 0
    for symbol, record in ablation["per_symbol"].items():
        if record["status"] != "MEASURED":
            continue
        assert record["window_is_inside_the_confirmation_interval"] is True
        assert record["training_window"][0] >= "2024-01-01", (
            f"{symbol}: the ablation window starts before the confirmation interval")
    claim = load("lab09_claim_report.json", "scripts/analyse_lab09_confirmation.py")
    assert claim["contributions"]["DESCRIPTIVE"]["where"] == "configs/lab09_group_ablation.json"


def test_the_audit_resolves_its_evidence_pointers():
    """A clause is DONE only when its pointer actually resolves.

    Earlier phases marked a clause DONE when a STRING naming its evidence was
    present, so a pointer at a renamed field looked identical to a real one.
    """
    audit = load("lab09_task_audit.json", "scripts/audit_lab09.py")
    assert audit["evidence_pointers_are_resolved"] is True
    for task in audit["tasks"]:
        if task["status"] != "DONE":
            continue
        assert task["pointers"], f"{task['clause_id']} is DONE with no pointer"
        assert all(p["resolved"] for p in task["pointers"]), task["clause_id"]


# ------------------------------------------------------------------ the report
REPORT = LAB_ROOT / "reports" / "lab09_report.md"


def test_the_lab09_report_carries_the_real_numbers():
    """CLAUDE.md rule 9: a report cannot drift from the artifact it came from.

    The contrast values are compared NUMERICALLY by parsing the table, so the
    test is about whether the number is right rather than about how it was
    formatted.
    """
    import re

    if not REPORT.is_file():
        pytest.skip("run scripts/write_lab09_report.py")
    text = REPORT.read_text()
    claim = load("lab09_claim_report.json", "scripts/analyse_lab09_confirmation.py")
    uncertainty = load("lab09_uncertainty.json", "scripts/analyse_lab09_confirmation.py")
    effect = json.loads((CONFIGS / "minimum_economic_effect.json").read_text())
    binding = load("cost_binding_verification.json", "scripts/verify_cost_binding.py")

    assert claim["conclusion_level"] in text
    assert f"{effect['minimum_daily_net_return_difference']:.2e}" in text
    assert f"{uncertainty['block_length_days']} days" in text
    assert str(binding["measurement"]["measured_one_way_fee_rate"]) in text

    measured = [(n, r) for n, r in uncertainty["contrasts"].items() if r.get("status") == "OK"]
    assert measured, "no contrast produced an interval"
    number = re.compile(r"[-+]?\d*\.?\d+(?:e[-+]?\d+)?")
    for name, record in measured:
        rows = [ln for ln in text.splitlines()
                if ln.startswith("|") and f"`{name}`" in ln and "CI" not in ln]
        assert rows, f"the report does not show contrast {name}"
        values = []
        for row in rows:
            for cell in (c.strip() for c in row.strip("|").split("|")):
                if number.fullmatch(cell):
                    values.append(float(cell))
        assert any(v == pytest.approx(record["point_estimate"], abs=5e-9) for v in values), (
            f"{name}: the report shows {values} and the artifact says "
            f"{record['point_estimate']}")


def test_the_lab09_report_states_every_blocker_it_has():
    if not REPORT.is_file():
        pytest.skip("run scripts/write_lab09_report.py")
    text = REPORT.read_text()
    claim = load("lab09_claim_report.json", "scripts/analyse_lab09_confirmation.py")
    for blocker in claim["blockers"]:
        head = blocker.split(":")[0]
        assert head in text, f"the report omits the blocker {head}"


def test_the_lab09_report_defines_its_own_terms():
    """CLAUDE.md rule 10, for the terms this phase introduces."""
    if not REPORT.is_file():
        pytest.skip("run scripts/write_lab09_report.py")
    text = REPORT.read_text()
    glossary = text[text.index("## Glossary"):text.index("\n## ", text.index("## Glossary") + 10)]
    body = text.replace(glossary, "")
    jargon = ["block bootstrap", "nested retrospective", "paired daily difference",
              "concentration", "Holm step-down", "cost stress", "one-way fee",
              "AS_DECLARED", "stale feed", "missing enrichment", "label permutation",
              "cash identity", "parameter-version lifecycle", "search cardinality",
              "prospective protocol", "second-best gap", "frozen confirmation",
              "conclusion level", "minimum economic effect", "common shock"]
    for term in jargon:
        if term.lower() in body.lower():
            assert f"**{term}**" in glossary, (
                f"the report uses '{term}' but the glossary does not define it")


def test_the_conclusion_follows_the_registered_decision_rule():
    """The level is derived, not chosen.

    Re-deriving it here from the artifact's own numbers means a hand-edited
    conclusion, or a rule that drifted away from what the report says it is,
    fails rather than reads plausibly.
    """
    claim = load("lab09_claim_report.json", "scripts/analyse_lab09_confirmation.py")
    uncertainty = load("lab09_uncertainty.json", "scripts/analyse_lab09_confirmation.py")
    minimum = json.loads((CONFIGS / "minimum_economic_effect.json").read_text())[
        "minimum_daily_net_return_difference"]

    measured = [e for e in claim["contributions"].values() if e.get("ci")]
    supported = [e for e in measured if e["verdict"] == "SUPPORTED"]
    ruled_out = [e for e in measured if e["verdict"] == "RULED_OUT"]
    severity = (claim.get("accounting_severity") or {}).get("severity")

    if severity == "MAJOR":
        expected = "FAILED_VALIDITY"
    elif supported:
        expected = claim["conclusion_level"]      # which edge depends on which contribution
        assert expected.startswith("NET_"), expected
    elif measured and len(ruled_out) == len(measured):
        expected = "NO_INCREMENTAL_VALUE"
    else:
        expected = "INCONCLUSIVE_SAMPLE"
    assert claim["conclusion_level"] == expected, (
        f"the rule gives {expected} and the artifact says {claim['conclusion_level']}")

    # and each contribution's own verdict follows from its interval
    for name, entry in claim["contributions"].items():
        if not entry.get("ci"):
            continue
        lower, upper = entry["ci"]
        if lower > minimum:
            assert entry["verdict"] == "SUPPORTED", name
        elif upper < minimum:
            assert entry["verdict"] == "RULED_OUT", name
        else:
            assert entry["verdict"] == "INCONCLUSIVE", (
                f"{name}: the interval straddles the minimum, which is not a negative result")
    assert uncertainty["contrasts"]  # the intervals the rule read really exist


def test_the_severity_of_the_accounting_defect_was_decided_by_a_prior_rule():
    claim = load("lab09_claim_report.json", "scripts/analyse_lab09_confirmation.py")
    severity = claim.get("accounting_severity") or {}
    if severity.get("severity") in (None, "NONE", "NOT_MEASURED"):
        pytest.skip("no accounting defect was measured")
    assert severity["rule"]["fixed_before"] == "the fee-sensitivity probe was run"
    assert severity["severity"] in ("MAJOR", "MATERIAL",
                                    "UNDECIDED_PENDING_SELECTION_PROBE")
    if severity["severity"] != "UNDECIDED_PENDING_SELECTION_PROBE":
        assert severity["selection_changed_at_the_registered_fee"] is not None, (
            "the severity cannot be settled without the selection probe")


def test_the_campaign_panel_reports_its_denominator():
    """"0 arms waited" and "no arm reported waiting" are different answers.

    Every vacuity this lab has found has the same shape: a verdict over a
    population nobody counted. The panel therefore carries how many arms ran, how
    many carried the field, and how many switches were requested at all.
    """
    support = load("lab09_support.json", "scripts/run_lab09_support.py")
    panel = support["situations"]["CAMPAIGN_NOT_FLAT"]
    assert panel["status"] in ("MEASURED", "MEASURED_NO_SWITCH_EVER_WAITED",
                               "NO_SWITCH_WAS_EVER_REQUESTED", "NOT_MEASURED", "NO_ARM_RAN")
    assert panel["arms_run"] > 0
    if panel["status"].startswith("MEASURED"):
        assert panel["arms_carrying_a_switch_delay_record"] > 0
    if panel["a_switch_waited_for_an_open_campaign"]:
        assert panel["blocked_bars_by_reason_across_every_arm"].get(
            "TRANSITION_BLOCKED_OPEN_CAMPAIGN", 0) > 0


def test_the_transition_diagnostics_cover_every_metric_guide_11_4_names():
    """Guide 11.4 lists seven, and the one that cannot be measured says so."""
    support = load("lab09_support.json", "scripts/run_lab09_support.py")
    diagnostics = support["transition_diagnostics"]
    assert "DETECTED" in diagnostics["anchored_on"]
    for field in ("activation_delay", "transition_turnover", "avoided_or_refused_switches",
                  "stale_incumbent", "unknown_and_fallback_usage", "parameter_rank_stability",
                  "wrong_switch_loss"):
        assert field in diagnostics, f"guide 11.4 names {field} and the panel omits it"
    assert diagnostics["wrong_switch_loss"]["status"] == "NOT_MEASURED_AT_SWITCH_LEVEL"
    assert diagnostics["wrong_switch_loss"]["not_reported_as_zero"] is True
    assert diagnostics["wrong_switch_loss"]["what_stands_in"]
    assert diagnostics["unknown_and_fallback_usage"]["emissions"] > 0


def test_the_seeds_are_read_back_from_what_the_run_stamped():
    """L09.2.2 — copying the frozen seeds into the results proves nothing.

    The confirmation document carries `seeds: protocol["seeds"]`, which says the
    document was written, not that the run used them. What the run used is
    stamped by the code that used it: every selector cutoff records the base seed
    it was handed, and every regime refit records its multi-start list.
    """
    reconciliation = load("lab09_reconciliation.json", "scripts/analyse_lab09_confirmation.py")
    seeds = reconciliation["seeds"]
    protocol = json.loads((CONFIGS / "lab08_pilot_protocol.json").read_text())

    probe = seeds["probe_design"]
    assert probe["cutoffs_stamped"] > 0, "no cutoff stamped a seed, so nothing was measured"
    assert probe["registered_base"] == protocol["seeds"]["probe_design"]
    assert probe["seeds_that_are_not_the_registered_base"] == []
    assert probe["matches"] is True

    model = seeds["model_multi_start"]
    assert model["refits_stamped"] > 0
    assert model["registered"] == protocol["seeds"]["model_multi_start"]
    assert model["distinct_seed_lists"] == [protocol["seeds"]["model_multi_start"]], (
        "a refit ran with a seed list the freeze does not name")
    assert seeds["all_measured_sources_match"] is True


def test_the_engine_is_rehashed_rather_than_declared_untouched():
    """L09.2.4 — 'untouched' written into an artifact is a sentence."""
    reconciliation = load("lab09_reconciliation.json", "scripts/analyse_lab09_confirmation.py")
    engine = reconciliation["engine"]
    assert engine["installed_versions"] == engine["expected_versions"]
    assert engine["wheels"], "no quantbt wheel was found to hash"
    for wheel in engine["wheels"]:
        assert wheel.get("matches") is True, (
            f"{wheel['wheel']} no longer matches the digest LAB-01 pinned")
        assert wheel["measured_sha256"] != "", "a digest was recorded empty"
    assert engine["lockfile_sha256"]["matches"] is True
    assert engine["untouched"] is True
    assert engine["pin_source"], "the pin this was compared against is not named"


def test_nothing_the_confirmation_deploys_was_registered_after_the_unlock():
    """L09.1.5 — `no_retuning_after_unlock: true` is a boolean an author typed.

    What can be measured is that every threshold, seed, contrast and economic
    assumption the confirmation deploys carries a stamp that PRECEDES the unlock.
    One stamped after it would be a choice made with the interval in view.
    """
    reconciliation = load("lab09_reconciliation.json", "scripts/analyse_lab09_confirmation.py")
    unlock = load("lab09_confirmation_spec.json", "scripts/unlock_lab09_confirmation.py")
    check = reconciliation["provenance"]["no_retuning_after_unlock"]
    assert check["unlocked_at_utc"] == unlock["unlocked_at_utc"]
    assert len(check["registrations"]) >= 5, "too few registrations were checked to mean anything"
    for row in check["registrations"]:
        assert row["stamped_at"], f"{row['artifact']} carries no stamp at all"
        assert row["stamped_at"] < unlock["unlocked_at_utc"], (
            f"{row['artifact']} was registered AFTER the interval was unlocked")
    assert check["all_precede_the_unlock"] is True


def test_the_lab_cannot_execute_rather_than_merely_choosing_not_to():
    """L09.1.3 — a prospective protocol that is 'not self-executed' by choice is weaker."""
    reconciliation = load("lab09_reconciliation.json", "scripts/analyse_lab09_confirmation.py")
    check = reconciliation["provenance"]["prospective_protocol_not_self_executed"]
    gates = check["execution_gates_in_the_registration"]
    assert set(gates) == {"live_execution_allowed", "market_experiments_allowed",
                          "production_mutations_allowed"}
    assert all(value is False for value in gates.values()), gates
    assert check["no_execution_path_exists"] is True


def test_the_costs_did_not_move_between_discovery_and_confirmation():
    """L09.2.3 — read off the confirmation's own fills, not copied from the protocol.

    'Untouched' has to mean the economics did not move BETWEEN the two phases,
    because the binding itself is known to be wrong (COR-13). The caveat has to
    say so, or the check reads as a clean bill of health.
    """
    reconciliation = load("lab09_reconciliation.json", "scripts/analyse_lab09_confirmation.py")
    check = reconciliation["provenance"]["costs_untouched_between_discovery_and_confirmation"]
    charged = check["one_way_fee_rate_charged_in_the_confirmation"]
    assert charged, "no arm reported the rate it was charged"
    assert check["single_rate_across_every_arm"] is True, (
        f"the arms were charged different rates: {charged}")
    assert check["matches_the_discovery_rate"] is True
    assert "half the registered" in check["caveat"]


def test_the_confirmation_contrasts_carry_the_baseline_caveat_too():
    """T54, on this phase's own contrasts and on the contributions built from them."""
    uncertainty = load("lab09_uncertainty.json", "scripts/analyse_lab09_confirmation.py")
    for name, record in uncertainty["contrasts"].items():
        if record.get("status") != "OK":
            continue
        involves_a = "A" in name.replace("(", "").replace(")", "").split("-")
        assert record.get("baseline_is_not_untouched", False) is involves_a, (
            f"{name}: baseline caveat present={record.get('baseline_is_not_untouched')} "
            f"but involves arm A={involves_a}")
        if involves_a:
            assert record["baseline_caveat"]

    claim = load("lab09_claim_report.json", "scripts/analyse_lab09_confirmation.py")
    for name in ("SELECTION", "TIMING"):
        entry = claim["contributions"][name]
        if entry["verdict"] == "NOT_MEASURED":
            continue
        assert entry["baseline_is_not_untouched"] is True, (
            f"the {name} contribution is measured against arm A and does not say so")
        assert entry["baseline_caveat"]
