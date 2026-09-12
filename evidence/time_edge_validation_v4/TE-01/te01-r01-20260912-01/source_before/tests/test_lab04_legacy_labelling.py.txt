"""LAB-04 exit obligation: legacy OOS-selected modes must be LABELLED.

"Legacy OOS-selected modes duoc label, khong reuse nhu untouched claim."

These read the committed L04.1 artifact rather than re-running the walk-forward
engine: the trace is evidence, and a report that silently reruns the optimizer is
exactly what guide 13.5 forbids.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

LAB_ROOT = Path(__file__).resolve().parent.parent
TRACE = LAB_ROOT / "configs" / "lab04_installed_wfo_trace.json"


@pytest.fixture(scope="module")
def trace():
    if not TRACE.is_file():
        pytest.skip("run scripts/trace_installed_selector.py")
    return json.loads(TRACE.read_text())


def test_every_installed_mode_was_traced(trace):
    traces = trace["modes"]["traces"]
    assert set(traces) == {"none", "mode_1_decay", "mode_2_sbb", "mode_3_flat_minima",
                           "mode_4_is_only_robust", "mode_5_full_robust"}
    for mode, record in traces.items():
        assert record["ok"], f"{mode} failed to run: {record['error']}"


def test_the_engines_own_oos_claim_is_captured_for_every_mode(trace):
    """The engine declares this itself; the lab must read it, not infer it."""
    for mode, record in trace["modes"]["traces"].items():
        claims = record["declared_claims"]
        assert "oos_used_for_selection" in claims, f"{mode} has no declared OOS claim"
        assert "validation_claim" in claims


def test_modes_declaring_oos_selection_are_named_and_labelled(trace):
    labelling = trace["legacy_oos_labelling"]
    declared = {mode for mode, record in trace["modes"]["traces"].items()
                if record["declared_claims"].get("oos_used_for_selection")}
    assert set(labelling["modes_declaring_oos_selection"]) == declared
    assert declared, "at least one installed mode declares OOS-adjusted selection"
    assert "A_legacy_selection_adjusted" in labelling["rule"]
    assert "untouched baseline" in labelling["rule"]
    assert labelling["authoritative_source"].startswith("the engine's own")


def test_a_null_behavioural_probe_never_overrides_the_declaration(trace):
    """A probe that could not see a difference is not proof there is none."""
    limit = trace["legacy_oos_labelling"]["behavioural_probe_limit"]
    assert "bounds rather than refutes" in limit
    assert "the declaration is the label" in limit
    for key, probe in trace["modes"]["oos_usage"].items():
        if probe.get("status") != "MEASURED":
            # an unmeasurable probe must state why and must not carry a verdict
            assert probe.get("uses_oos_for_selection") is None, key
            assert probe.get("detail") or probe.get("error"), key


def test_the_mutation_probe_proves_it_could_have_detected_a_change(trace):
    """A test that cannot fail proves nothing; each MEASURED probe shows its power."""
    measured = [p for p in trace["modes"]["oos_usage"].values()
                if p.get("status") == "MEASURED"]
    assert measured
    for probe in measured:
        assert probe["mutation_effective"] is True
        assert probe["training_data_untouched_by_mutation"] is True
        assert probe["baseline_max_abs_oos_sharpe"] != probe["mutated_max_abs_oos_sharpe"]


def test_full_sample_calibration_is_not_reported_as_walk_forward(trace):
    record = trace["modes"]["traces"]["mode_5_full_robust"]
    assert record["declared_claims"]["full_sample_used_for_selection"] is True
    assert record["declared_claims"]["validation_claim"] == "none_full_sample_calibration"
    assert record["fold_count"] == 1, "full-sample calibration collapses to a single fold"
    probe = trace["modes"]["oos_usage"]["mode_5_full_robust"]
    assert probe["status"] == "NO_OUT_OF_SAMPLE_REGION_EXISTS"


def test_the_public_default_is_recorded_as_performing_no_search(trace):
    search = trace["search_behaviour"]
    assert search["none"]["searched"] is False
    assert search["none"]["trial_count"] == 1
    assert "performs no parameter search" in trace["search_finding"]
    for mode, info in search.items():
        if mode != "none":
            assert info["searched"] is True, f"{mode} should have searched"


def test_arm_A_declares_which_installed_rule_makes_its_decision():
    baseline = LAB_ROOT / "configs" / "lab04_calendar_baseline.json"
    if not baseline.is_file():
        pytest.skip("run scripts/summarize_calendar_baseline.py")
    cells = json.loads(baseline.read_text())["cells"]
    run = [c for c in cells if c["status"] == "RUN"]
    if not run:
        pytest.skip("no completed cells")
    for cell in run:
        for fold in cell["folds"]:
            evidence = fold.get("cutoff_evidence")
            if not evidence:
                continue
            selection = evidence["arm_A"]
            assert selection["selector"] == (
                "quantbt.walkforward._select_oos_candidate_record")
            assert selection["candidate_selection_metric"] == "robust_decay"
            assert selection["optimization_mode"] == "none"


# ---------------------------------------------------------------------------
# hard rule: a phase that tests a registered hypothesis reports it with real numbers
# ---------------------------------------------------------------------------

BASELINE = LAB_ROOT / "configs" / "lab04_calendar_baseline.json"
REPORT = LAB_ROOT / "reports" / "lab04_report.md"


@pytest.fixture(scope="module")
def baseline():
    if not BASELINE.is_file():
        pytest.skip("run scripts/summarize_calendar_baseline.py")
    return json.loads(BASELINE.read_text())


def test_the_phase_names_the_hypothesis_it_registered_before_running(baseline):
    registry = json.loads((LAB_ROOT / "configs" / "hypothesis_registry.json").read_text())
    hyp = baseline["registered_hypothesis"]
    assert hyp["hypothesis_id"] == "H1"
    declared = next(h for h in registry["primary_contrasts"] if h["id"] == "H1")
    assert hyp["contrast"] == declared["contrast"] == "B-A"
    assert hyp["question"] == declared["question"]
    assert hyp["registered_at_utc"] == registry["registered_at_utc"]


def test_the_conclusion_uses_the_registered_endpoint_not_a_convenient_one(baseline):
    study = json.loads((LAB_ROOT / "configs" / "study_registration.json").read_text())
    hyp = baseline["registered_hypothesis"]
    assert hyp["primary_endpoint"] == study["primary_endpoint"]["statistic"]
    assert "daily" in hyp["primary_endpoint"]
    assert hyp["mean_daily_net_return_difference"] is not None
    assert "NOT the registered endpoint" in hyp["endpoint_note"]


def test_the_minimum_effect_was_fixed_before_any_comparison(baseline):
    effect = json.loads((LAB_ROOT / "configs" / "minimum_economic_effect.json").read_text())
    hyp = baseline["registered_hypothesis"]
    assert hyp["minimum_economic_effect_per_day"] == \
        effect["minimum_daily_net_return_difference"]
    assert hyp["minimum_effect_registered_before_any_comparison"] is True


def test_the_conclusion_level_comes_from_the_registered_vocabulary(baseline):
    registry = json.loads((LAB_ROOT / "configs" / "hypothesis_registry.json").read_text())
    hyp = baseline["registered_hypothesis"]
    assert hyp["conclusion_level"] in registry["conclusion_levels"]
    if hyp["conclusion_level"] == "NET_PARAMETER_SELECTION_EDGE":
        assert not hyp["blockers_preventing_a_stronger_claim"]
        assert abs(hyp["mean_daily_net_return_difference"]) >= \
            hyp["minimum_economic_effect_per_day"]


def test_no_adjusted_p_value_is_claimed_before_the_family_exists(baseline):
    hyp = baseline["registered_hypothesis"]
    assert hyp["family_adjustment_applied"] is False
    assert "LAB-09" in hyp["family_adjustment_note"]


def test_the_markdown_report_carries_the_real_numbers():
    """The hard rule: a phase report is markdown WITH the measured figures in it."""
    if not REPORT.is_file():
        pytest.skip("run scripts/write_lab04_report.py")
    text = REPORT.read_text()
    for token in ("Registered hypothesis", "H1 = B-A", "mean daily net-return difference",
                  "Conclusion level", "minimum economic effect"):
        assert token in text, f"the report is missing: {token}"
    if BASELINE.is_file():
        hyp = json.loads(BASELINE.read_text())["registered_hypothesis"]
        assert f"{hyp['mean_daily_net_return_difference']:.3e}" in text, (
            "the measured endpoint value must appear in the markdown, not only in JSON")
        assert hyp["conclusion_level"] in text


def test_a_below_threshold_effect_is_inconclusive_whatever_else_is_true(baseline):
    """A blocker must never promote a difference inside the cost-stress band."""
    hyp = baseline["registered_hypothesis"]
    if hyp["mean_daily_net_return_difference"] is None:
        pytest.skip("no measured endpoint")
    below = abs(hyp["mean_daily_net_return_difference"]) < \
        hyp["minimum_economic_effect_per_day"]
    if below and hyp["conclusion_level"] != "FAILED_VALIDITY":
        assert hyp["conclusion_level"] == "INCONCLUSIVE_SAMPLE", (
            "an effect below the registered minimum may not be reported as anything stronger")
    assert "cost-stress band" in hyp["level_rule"]


def test_cells_where_an_arm_never_selected_are_identified(baseline):
    """Holding the seed point for the whole evaluation is not evidence about a selector."""
    stuck = baseline["cells_where_an_arm_never_used_its_selector"]
    for arm in ("A", "B"):
        record = stuck[arm]
        assert record["cells"] <= record["of_cells"]
        for row in record["detail"]:
            assert row["distinct_parameter_sets"] == 1, (
                "a cell listed as never-switched must have exactly one parameter set")
            assert row["binding_constraint"]
    assert "NOT evidence about the selector" in stuck["reading"]


def test_the_contrast_is_also_reported_without_those_cells(baseline):
    sub = baseline["contrast_where_both_arms_actually_selected"]
    stuck = baseline["cells_where_an_arm_never_used_its_selector"]
    excluded = {row["cell"] for arm in ("A", "B") for row in stuck[arm]["detail"]}
    assert set(sub["cells_excluded"]) == excluded
    assert sub["cells_kept"] == sub["sign_test"]["cells"]
    if excluded:
        assert sub["cells_kept"] < baseline["contrast_B_minus_A"]["net_return"]["cells"]


def test_never_switched_cells_are_a_registered_blocker(baseline):
    stuck = baseline["cells_where_an_arm_never_used_its_selector"]
    total = sum(stuck[arm]["cells"] for arm in ("A", "B"))
    blockers = baseline["registered_hypothesis"]["blockers_preventing_a_stronger_claim"]
    if total:
        assert any("never exercised its selector" in b for b in blockers), (
            "a cell that never tested the selector must cap the claim, not be pooled silently")


def test_the_gate_diagnostic_is_declared_post_hoc_and_cannot_move_the_primary(baseline):
    gate = baseline["gate_bindingness_diagnostic"]
    assert gate["declared_post_hoc"] is True
    assert gate["registered_gate_is_the_primary_and_is_not_revised"] is True
    registered = [row for row in gate["grid"] if row["is_the_registered_gate"]]
    assert len(registered) == 1, "exactly one row must be the registered gate"
    assert registered[0]["min_quality"] == gate["registered_gate"]["min_quality"]
    assert "does NOT simulate the outcome" in gate["what_this_cannot_say"]
    # the registered thresholds in the artifact must equal the ones the code used
    assert baseline["utility_hyperparameters"]["gate_min_return"] == \
        gate["registered_gate"]["min_quality"]


def test_missing_local_panels_are_not_the_hidden_bottleneck(baseline):
    """If panels were often incomplete, the gate numbers would mean something else."""
    gate = baseline["gate_bindingness_diagnostic"]
    assert gate["cutoffs_with_at_least_one_computable_R"] == gate["cutoffs_total"], (
        "some cutoff had no candidate with a computable R; the probe design, not the gate, "
        "would then be the binding constraint")
    assert gate["local_panels_are_not_the_bottleneck"] is True
    assert "undercounted" in gate["status_ordering_note"]


def test_every_term_the_report_uses_is_defined_in_its_glossary():
    """CLAUDE.md rule 10: a term used without its meaning and its context is not a report."""
    if not REPORT.is_file():
        pytest.skip("run scripts/write_lab04_report.py")
    text = REPORT.read_text()
    glossary_start = text.index("## Glossary")
    glossary = text[glossary_start:text.index("\n## ", glossary_start + 10)]
    body = text[:glossary_start] + text[glossary_start + len(glossary):]

    jargon = ["space-filling", "medoid", "P_survive", "inner episode", "local panel",
              "incumbent", "conclusion level", "minimum economic effect", "sign reversal",
              "declared post-hoc", "anchor", "probe", "TPE", "cutoff"]
    for term in jargon:
        if term.lower() in body.lower():
            assert f"**{term}**" in glossary, (
                f"the report uses '{term}' but the glossary does not define it")

    # a glossary row must give BOTH the meaning and where it applies
    rows = [ln for ln in glossary.splitlines()
            if ln.startswith("| **") and ln.count("|") >= 4]
    assert len(rows) >= 15, "the glossary looks truncated"
    for row in rows:
        cells = [c.strip() for c in row.strip("|").split("|")]
        assert len(cells) >= 3, row
        assert len(cells[1]) > 25, f"meaning too thin: {row}"
        import re as _re
        assert _re.search(r"LAB-0\d|L0\d\.\d|guide", cells[2]), (
            f"a glossary row must say WHERE the term applies: {row}")


def test_every_phase_report_carries_a_glossary():
    """CLAUDE.md rule 10 applies to every report, not only the newest one."""
    from crypto_regime_lab.evidence import glossary as G

    heading = "## Glossary — what each term means and where it applies"
    # every phase that has a report, not only the hand-written ones. A generated
    # report inserts its glossary from the same registry, so a term added to a
    # phase and not rendered is caught here rather than at the next read.
    checked = 0
    for phase, name in (("LAB-01", "lab01_report.md"), ("LAB-02", "lab02_report.md"),
                        ("LAB-03", "lab03_report.md"), ("LAB-04", "lab04_report.md"),
                        ("LAB-05", "lab05_report.md"), ("LAB-06", "lab06_report.md"),
                        ("LAB-07", "lab07_report.md"), ("LAB-08", "lab08_report.md"),
                        ("LAB-09", "lab09_report.md")):
        path = LAB_ROOT / "reports" / name
        if not path.is_file():
            continue
        checked += 1
        text = path.read_text()
        assert text.count(heading) == 1, f"{name}: glossary missing or duplicated"
        for term, _, _ in G.BY_PHASE[phase]:
            assert f"| **{term}** |" in text, f"{name} does not define {term}"
    assert checked >= 4, "no phase report was available to check"


def test_the_glossary_lives_in_one_place():
    """A definition duplicated per report is a definition that will drift."""
    from crypto_regime_lab.evidence import glossary as G

    generator = (LAB_ROOT / "scripts" / "write_lab04_report.py").read_text()
    assert "G.BY_PHASE" in generator
    assert "space-filling" not in generator, (
        "the report generator must not hold its own copy of a definition")
    terms = [term for entries in G.BY_PHASE.values() for term, _, _ in entries]
    for term in terms:
        meanings = {meaning for entries in G.BY_PHASE.values()
                    for t, meaning, _ in entries if t == term}
        assert len(meanings) == 1, f"'{term}' has {len(meanings)} different meanings"


def test_opinions_are_written_but_never_mixed_into_results():
    """CLAUDE.md rule 11: opinions are recorded separately and are not implemented."""
    opinions = LAB_ROOT / "reports" / "improvement_opinions.md"
    assert opinions.is_file(), "reports/improvement_opinions.md is missing"
    text = opinions.read_text()
    assert "WRITTEN, NOT RUN" in text
    assert "none of this is implemented, scheduled, or assumed" in text
    entries = [ln for ln in text.splitlines() if ln.startswith("## OP-")]
    assert len(entries) >= 5, "an opinions file with almost nothing in it is not an opinion"
    for marker in ("**Options.**", "**What would settle it.**", "**Measured"):
        assert text.count(marker) >= len(entries) - 1, (
            f"every entry needs {marker}: an opinion without a measurement or a test is a guess")

    # results reports must NOT contain opinions
    for name in ("lab01_report.md", "lab02_report.md", "lab03_report.md", "lab04_report.md"):
        path = LAB_ROOT / "reports" / name
        if path.is_file():
            assert "## OP-" not in path.read_text(), (
                f"{name} contains an opinion entry; opinions live in their own file")


def test_the_audit_refuses_a_matrix_built_with_the_wrong_design():
    """A complete matrix built the wrong way is not a completed phase."""
    audit_path = LAB_ROOT / "configs" / "lab04_task_audit.json"
    if not audit_path.is_file():
        pytest.skip("run scripts/audit_lab04.py")
    audit = json.loads(audit_path.read_text())
    assert "primary_matrix_design_matches_spec" in audit
    assert "space-filling" in audit["design_rule"] or "TPE" in audit["design_rule"]
    if not audit["primary_matrix_design_matches_spec"]:
        blocked = [row["task_id"] for row in audit["tasks"] if row["status"] != "DONE"]
        assert any(t.startswith("L04.5") for t in blocked), (
            "a spec-deviating design must block the L04.5 rows")
