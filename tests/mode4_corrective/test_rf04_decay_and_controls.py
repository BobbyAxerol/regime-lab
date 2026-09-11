"""RF-04.3/RF-04.4 acceptance — decay panels, matched control, funnel and report.

Artifact guards with a denominator and a way to go red:

* the panels exist with nonzero denominators and strict (finite) JSON numbers;
* D1 keeps the raw and penalized IS flavors on separate rows;
* D2 rows belong to the registered anchor subset and use H1-vs-Hj deltas;
* the mandatory M4_CAL_MATCHED arm is present with the registered budget;
* funnel counts agree with the committed pilot artifacts;
* the report carries all twelve sections and the A16 claim vocabulary, and no
  contrast is allowed to read ``POSITIVE`` from the bounded pilot.
"""

from __future__ import annotations

import json
import math
import re

RF04 = ("evidence", "corrective_mode4_v3", "RF-04")


def _read(lab_root, name: str) -> str:
    return (lab_root.joinpath(*RF04) / name).read_text(encoding="utf-8")


def _load(lab_root, name: str) -> dict:
    return json.loads(_read(lab_root, name))


def _assert_finite(node, path: str = "root") -> None:
    if isinstance(node, float):
        assert math.isfinite(node), f"non-finite number at {path}"
    elif isinstance(node, dict):
        for key, value in node.items():
            _assert_finite(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _assert_finite(value, f"{path}[{index}]")


def test_rf04_decay_panels_have_denominators_and_no_nonfinite(lab_root):
    text = _read(lab_root, "decay_panels.json")
    assert not re.search(r"(?<![\w\"])(NaN|Infinity|-Infinity)(?![\w\"])", text), (
        "the panel contains a non-finite JSON literal")
    panel = json.loads(text)
    _assert_finite(panel)
    denominators = panel["denominators"]
    assert denominators["D1_rows"] > 0
    assert denominators["D2_rows"] > 0
    assert denominators["D3_rows"] > 0
    assert denominators["registered_anchors"] > 0
    assert denominators["anchors_replayed"] == denominators["registered_anchors"], (
        "every registered anchor must either have rows or a recorded null reason")
    for row in panel["D1"]:
        for key in ("selection_id", "parameter_digest", "alpha", "symbol", "arm",
                    "metric_name", "unit", "validity_status", "observed_days"):
            assert key in row, f"D1 row missing {key}: {row.get('selection_id')}"
        assert row["parameter_digest"].startswith("pv-")
    for row in panel["D3"]:
        for key in ("left_length_days", "right_length_days", "left_support", "right_support"):
            assert key in row, f"D3 row missing {key}"
    assert panel["D2"]["status"].startswith("COMPLETE"), panel["D2"]["reason"]


def test_rf04_d1_keeps_raw_and_penalized_separate(lab_root):
    panel = _load(lab_root, "decay_panels.json")
    sharpe = [row for row in panel["D1"] if row["metric_name"] == "sharpe"]
    by_selection: dict[str, dict[str, dict]] = {}
    for row in sharpe:
        by_selection.setdefault(row["selection_id"], {})[row["raw_or_penalized"]] = row
    assert by_selection, "no D1 Sharpe rows"
    for selection_id, flavors in by_selection.items():
        assert set(flavors) == {"raw", "penalized"}, f"{selection_id} lacks raw/penalized rows"
        assert flavors["raw"]["penalty_components"] is None
        assert flavors["penalized"]["penalty_components"] is not None
        assert flavors["raw"]["unit"] == flavors["penalized"]["unit"]
        assert flavors["raw"]["metric_name"] == flavors["penalized"]["metric_name"]
        if flavors["raw"]["left_value"] is not None:
            assert flavors["raw"]["left_value"] == flavors["raw"]["is_trial"]["mean_is_sharpe"]
        assert flavors["raw"]["right_value"] == flavors["penalized"]["right_value"]
    # the penalized objective is the engine's selected_is_objective, never the raw Sharpe
    for flavors in by_selection.values():
        ledger = flavors["penalized"]["is_trial"]
        if flavors["penalized"]["left_value"] is not None:
            assert flavors["penalized"]["left_value"] == ledger["selected_is_objective"]


def test_rf04_d2_rows_are_the_registered_anchors_with_h1_reference(lab_root):
    panel = _load(lab_root, "decay_panels.json")
    registered = {
        (anchor["cell"], anchor["arm"], anchor["fold_id"])
        for anchor in panel["registration"]["decay_anchor"]["anchors"]
    }
    assert registered, "the D2 anchor subset was not registered"
    anchors_seen = set()
    for row in panel["D2"]["rows"]:
        cell, arm, fold = row["selection_id"].split(":")
        assert fold == "fold0", "the registered subset is the FIRST selection only"
        anchors_seen.add((cell, arm, 0))
        assert row["comparison_kind"] == "FIXED_PARAM_AGE"
        assert row["unit"] in ("annualised_daily_return_ratio", "account_bps/day", "ratio")
        assert row["validity_status"]
        assert "trade_count" in row
        if row["age_window_label"] == "H1":
            assert row["signed_delta"] == 0.0 or row["signed_delta"] is None
    assert anchors_seen == registered


def test_rf04_matched_control_present_with_registered_budget(lab_root):
    controls = _load(lab_root, "controls_and_funnel.json")
    registration = _load(lab_root, "paired_discovery_registration.json")
    pilot = _load(lab_root, "paired_discovery_pilot.json")
    matched = controls["matched_control"]
    assert matched["required"] is True
    assert matched["refits"] == 6 and len(matched["cutoffs"]) == 6
    assert len({cutoff[:10] for cutoff in matched["cutoffs"]}) == 6, "cutoffs are not distinct"
    assert matched["cells"], "no matched cell ran"
    for entry in matched["cells"]:
        arm = entry["arm"]
        assert arm["ok"], arm.get("error")
        assert arm["fold_count"] == 6
        assert arm["trial_count"] == 6 * registration["matched"]["optuna_trials_per_cutoff"]
        assert arm["oos_used_for_selection"] is False
        account = arm["account"] or {}
        if entry["route"] == "event":
            assert account["status"] == "EVALUATED"
    # the matched refit count equals the regime arm's, which is why it is mandatory
    assert pilot["arms"]["M4_REGIME"]["count"] == matched["refits"] != pilot["arms"]["M4_CAL"]["count"]


def test_rf04_funnel_counts_consistent_with_the_pilot(lab_root):
    controls = _load(lab_root, "controls_and_funnel.json")
    pilot = _load(lab_root, "paired_discovery_pilot.json")
    cells = {cell["cell"]: cell for cell in pilot["cells"]}
    for cell_name, funnel_cell in controls["funnel"]["cells"].items():
        artifact = cells[cell_name]
        for arm_name in ("M4_CAL", "M4_REGIME"):
            record = artifact["arms"][arm_name]
            searches = funnel_cell["searches"][arm_name]
            assert searches["folds_scored"] == record["fold_count"]
            assert searches["trials_retained"] == record["trial_count"]
            assert searches["cutoffs"] == len(record["cutoffs"])
        matched = controls["matched_control"]["cells"]
        assert funnel_cell["searches"]["M4_CAL_MATCHED"]["cutoffs"] == 6
        assert len(matched) == len(controls["funnel"]["cells"])
        valid = funnel_cell["valid_observations"]
        assert 0 < valid["eligible_quality_ok"] <= valid["total_emissions_in_window"]
        assert valid["semantic_changes_in_window"] >= funnel_cell["triggers"]["M4_REGIME"]
    assert controls["funnel"]["potential_level"] in {
        "LOW_PARAMETER_OPPORTUNITY", "OPPORTUNITY_UNINFORMED", "INFORMATIVE_NOT_ACTIONABLE",
        "ACTIONABLE_UNCONFIRMED", "POSITIVE_WITHIN_SCOPE", "NEGATIVE_WITHIN_SCOPE",
        "INCONCLUSIVE", "UNASSESSED"}
    assert controls["funnel"]["low_parameter_opportunity_cells"], (
        "the rank diagnostic never fired; it proves nothing if it cannot go red")
    # and it CAN go red: the A-HMA cell has genuine objective variation
    assert controls["funnel"]["cells"]["A-HMA/BTCUSDT"]["rank_diagnostic"][
        "rank_signal_present"] is True


def test_rf04_paired_endpoints_fail_closed_on_identical_or_deviated(lab_root):
    controls = _load(lab_root, "controls_and_funnel.json")
    assert controls["paired_endpoints"], "no paired endpoint was computed"
    for entry in controls["paired_endpoints"]:
        difference = entry["paired_daily_difference"]
        assert difference["n_days"] > 0
        assert entry["economic_status"] != "POSITIVE", (
            "the bounded pilot may never record a POSITIVE economic status")
        if difference["zero_variance"]:
            assert entry["economic_status"] == "NOT_EVALUABLE"
        if "A-SC" in entry["contrast"]:
            assert entry["economic_status"] == "NOT_EVALUABLE", (
                "the deviated A-SC cell must fail closed")
    placebo = controls["placebo"]
    assert placebo["status"] in ("RUN", "REGISTERED_NOT_RUN")
    if placebo["status"] == "REGISTERED_NOT_RUN":
        assert placebo["reason"], "a not-run placebo needs a reason"


def test_rf04_report_has_twelve_sections_and_claim_vocabulary(lab_root):
    text = _read(lab_root, "report.md")
    for number in range(1, 13):
        assert re.search(rf"^## {number}\. ", text, flags=re.MULTILINE), (
            f"report.md is missing section {number}")
    report = _load(lab_root, "report.json")
    for key in ("schema", "phase_id", "status", "study_id", "source", "objective",
                "registered_arms", "findings", "tests", "market_runs", "metrics",
                "performance", "proof_capability", "potential", "claim", "limitations",
                "review", "handoff"):
        assert key in report, f"report.json missing {key}"
    claim = report["claim"]
    assert claim["execution_validity"] in ("PASS", "FAIL", "PARTIAL")
    assert claim["implementation_fidelity"] in ("AS_SPECIFIED", "DEVIATED", "NOT_IMPLEMENTED")
    assert claim["statistical_status"] in ("NOT_EVALUABLE", "INCONCLUSIVE",
                                           "NEGATIVE_WITHIN_SCOPE", "POSITIVE_WITHIN_SCOPE")
    assert claim["statistical_status"] != "POSITIVE_WITHIN_SCOPE"
    assert claim["economic_status"] in ("NOT_EVALUABLE", "INCONCLUSIVE",
                                        "NEGATIVE_WITHIN_SCOPE", "POSITIVE_WITHIN_SCOPE")
    assert claim["economic_status"] != "POSITIVE_WITHIN_SCOPE"
    for contrast in report["contrasts"]:
        assert contrast["statistical_status"] in ("NOT_EVALUABLE", "INCONCLUSIVE",
                                                  "NEGATIVE_WITHIN_SCOPE")
        assert contrast["execution_validity"] in ("PASS", "FAIL", "PARTIAL")
        assert "low_parameter_opportunity" in contrast
    assert report["handoff"]["next_phase"] == "RF-05"


def test_rf04_design_freeze_and_artifact_hashes_are_recorded(lab_root):
    freeze = _load(lab_root, "design_freeze.json")
    assert freeze["status"] in ("FROZEN_FOR_RF05", "FROZEN_FOR_RF05_WITH_BLOCKERS")
    assert freeze["no_promising_design"] is True
    assert freeze["primary_design"]["arms"] == ["M4_CAL", "M4_REGIME"]
    assert freeze["primary_design"]["budget_control"] == "M4_CAL_MATCHED"
    assert len(freeze["primary_design"]["primary_contrasts"]) == 2
    report = _load(lab_root, "report.json")
    assert report["artifact_hashes"]["decay_panels.json"]
    assert report["artifact_hashes"]["controls_and_funnel.json"]
