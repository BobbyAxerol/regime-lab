"""RF-04 Outputs closure — cell coverage, profiling/budget and the transparency ledger.

Each guard has a denominator and can go red:

* all 20 planned cells are present, unique, classified with the registered
  vocabulary, and the RF-02 route matrix / RF-04 full paired artifact merge
  exactly; the RF-04.1 pilot-era report is checked against the superseded pilot
  scope so the coverage supersession stays explicit;
* a non-executed cell carries null metrics with a reason, never a zero, and an
  executed cell's numbers equal the committed full-artifact values;
* profiling has positive denominators, measured wall values equal the pilot
  artifact, the truly unmeasured fields are null + reason, and engine counters
  equal the committed evaluator traces;
* the transparency ledger covers both cells and both primary arms, the selected
  digests recompute and cross-check the decay panel, and the schema hash
  recomputes from the declared schema object;
* the report references all three artifacts and its coverage counts agree with
  the pilot scope the full-cohort artifact supersedes.
"""

from __future__ import annotations

import hashlib
import json

from crypto_regime_lab.integration.activation import parameter_digest
from crypto_regime_lab.selector.alpha_schemas import SCHEMAS

RF04 = ("evidence", "corrective_mode4_v3", "RF-04")
RF02 = ("evidence", "corrective_mode4_v3", "RF-02")
GAP_CLOSE_ARTIFACTS = ("cell_coverage.json", "profiling_and_budget.json",
                       "mode4_transparency_ledger.json")
STATUS_VOCABULARY = {"RUN_VALID", "RUN_NOT_EVALUABLE", "BLOCKED_CAPABILITY",
                     "NOT_RUN", "NOT_RUN_BUDGET", "INSUFFICIENT_DATA"}


def _read(lab_root, parts, name: str) -> str:
    return lab_root.joinpath(*parts, name).read_text(encoding="utf-8")


def _load(lab_root, parts, name: str) -> dict:
    return json.loads(_read(lab_root, parts, name))


def _canonical_sha256(payload) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def test_rf04_cell_coverage_all_20_cells_unique_classified_and_merged(lab_root):
    coverage = _load(lab_root, RF04, "cell_coverage.json")
    route = _load(lab_root, RF02, "pilot_and_route_matrix.json")
    full = _load(lab_root, RF04, "paired_discovery_full.json")
    cells = coverage["cells"]
    assert len(cells) == 20, "the registered cohort is 4 alphas x 5 symbols"
    ids = [cell["cell"] for cell in cells]
    assert len(set(ids)) == 20, f"duplicate cell id in coverage: {ids}"
    assert set(coverage["status_vocabulary"]) == STATUS_VOCABULARY
    for cell in cells:
        assert cell["coverage_status"] in STATUS_VOCABULARY
        assert cell["reason"].strip(), f"{cell['cell']} has no reason"
        assert cell["evidence_ref"].strip(), f"{cell['cell']} has no evidence ref"
        assert cell["evidence_refs"], f"{cell['cell']} has no evidence refs"
    route_blocked = {row["cell"] for row in route["route_matrix"]["cells"]
                     if row["route_status"] == "BLOCKED_CAPABILITY"}
    coverage_blocked = {cell["cell"] for cell in cells
                        if cell["coverage_status"] == "BLOCKED_CAPABILITY"}
    assert route_blocked == coverage_blocked, (
        f"route/coverage blocked mismatch: {route_blocked ^ coverage_blocked}")
    executed = {cell["cell"] for cell in full["cells"]}
    assert {cell["cell"] for cell in cells if cell["executed"]} == executed, (
        "the executed set does not match the committed full paired artifact")
    counts = coverage["counts"]
    assert counts["planned_cells"] == 20 and counts["total_classified"] == 20
    for status in STATUS_VOCABULARY:
        assert counts[status] == sum(1 for cell in cells
                                     if cell["coverage_status"] == status)
    assert sum(counts[status] for status in STATUS_VOCABULARY) == 20
    assert counts["RUN_VALID"] == 10 and counts["RUN_NOT_EVALUABLE"] == 0
    assert counts["NOT_RUN"] == 0 and counts["NOT_RUN_BUDGET"] == 0
    assert "paired_discovery_full.json" in {
        source["artifact"].rsplit("/", 1)[-1] for source in coverage["sources"]}
    by_cell = {cell["cell"]: cell for cell in cells}
    sc = by_cell["A-SC/BTCUSDT"]
    assert sc["coverage_status"] == "RUN_VALID"
    assert sc["route"] == "event"
    assert sc["run_result"]["implementation_fidelity"] == "AS_SPECIFIED"
    assert [deviation["route"] for deviation in sc["run_result"]["route_deviations"]] == [
        "endpoint"], "the registered endpoint deviation was not retained"
    assert sc["run_result"]["route_deviations"][0]["implementation_fidelity"] == "DEVIATED"
    hma = by_cell["A-HMA/BTCUSDT"]
    assert hma["coverage_status"] == "RUN_VALID"
    assert hma["route"] == "event"
    assert hma["run_result"]["route"] == "event"


def test_rf04_cell_coverage_nulls_carry_reasons_and_metrics_match_full(lab_root):
    coverage = _load(lab_root, RF04, "cell_coverage.json")
    full = _load(lab_root, RF04, "paired_discovery_full.json")
    controls = _load(lab_root, RF04, "controls_and_funnel.json")
    full_cells = {cell["cell"]: cell for cell in full["cells"]}
    matched = {row["cell"]: row["arm"] for row in controls["matched_control"]["cells"]}
    placebo = {row["cell"]: row["arm"] for row in controls["placebo"]["cells"]}
    for cell in coverage["cells"]:
        if not cell["executed"]:
            assert cell["run_result"] is None
            assert cell["run_result_reason"].strip(), f"{cell['cell']} missing run reason"
            assert cell["account_metrics"] is None, (
                f"{cell['cell']} must not zero-fill account metrics")
            assert cell["account_metrics_reason"].strip(), (
                f"{cell['cell']} missing account-metrics reason")
            assert cell["route_reason"].strip()
            continue
        assert cell["account_metrics"] is not None
        assert cell["account_metrics_reason"] is None
        artifact = full_cells[cell["cell"]]
        primary = next(run for run in artifact["runs"]
                       if run["route"] == artifact["primary_route"])
        for arm, values in cell["account_metrics"].items():
            if arm in primary["arms"]:
                source = primary["arms"][arm]
            elif arm == "M4_CAL_MATCHED":
                source = matched[cell["cell"]]
            else:
                source = placebo[cell["cell"]]
            account = source["account"] or {}
            assert values["equity_last"] == account["equity_last"]
            assert values["num_trades"] == (account.get("engine_report") or {}).get("num_trades")


def test_rf04_profiling_has_denominators_and_unmeasured_nulls_with_reasons(lab_root):
    profiling = _load(lab_root, RF04, "profiling_and_budget.json")
    pilot = _load(lab_root, RF04, "paired_discovery_pilot.json")
    denominators = profiling["denominators"]
    assert denominators["planned_cells"] == 20
    assert denominators["executed_cells"] == 2
    assert denominators["pilot_trial_rows"] > 0
    assert denominators["d1_rows"] > 0
    assert denominators["d2_rows"] > 0
    assert denominators["d3_rows"] > 0
    for key in ("cpu_seconds", "peak_rss_bytes", "candidate_bar_visits"):
        entry = profiling[key]
        assert entry["value"] is None, f"{key} was never measured; a value would be fabricated"
        assert entry["reason"].strip(), f"{key} is null without a reason"
    for cell in pilot["cells"]:
        for arm in ("M4_CAL", "M4_REGIME"):
            wall = profiling["wall_seconds"]["pilot_by_cell_arm"][cell["cell"]][arm]
            assert wall == cell["arms"][arm]["wall_seconds"]
            trace = cell["arms"][arm].get("evaluator_trace") or {}
            if trace.get("event_account_runs") is not None:
                assert (profiling["engine_calls"]["event_account_counters"]
                        ["account_runs_by_cell_arm"][cell["cell"]][arm]
                        == trace["event_account_runs"])
            if trace.get("n_studies") is not None:
                assert (profiling["engine_calls"]["optuna_counters"]
                        ["studies_by_cell_arm"][cell["cell"]][arm] == trace["n_studies"])
    assert profiling["rows"]["account_bars_null_reason"].strip()
    sizes = profiling["bytes"]["artifacts_bytes"]
    assert sizes, "the profiling artifact has no byte denominator"
    assert all(value > 0 for value in sizes.values())
    assert profiling["bytes"]["total_artifacts_bytes"] == sum(sizes.values())
    assert profiling["budget"]["status"] == "BELOW_REGISTERED_MINIMUM"


def test_rf04_transparency_ledger_covers_both_cells_and_arms(lab_root):
    ledger = _load(lab_root, RF04, "mode4_transparency_ledger.json")
    pilot = _load(lab_root, RF04, "paired_discovery_pilot.json")
    panel = _load(lab_root, RF04, "decay_panels.json")
    digest_by_selection = {}
    for row in panel["D1"]:
        digest_by_selection.setdefault(row["selection_id"], row["parameter_digest"])
    assert ledger["coverage"]["cells"] == 2
    assert ledger["coverage"]["arms"] == 2
    assert ledger["coverage"]["cutoffs"] == 18
    assert ledger["coverage"]["cutoffs"] == ledger["coverage"]["cutoffs_expected"]
    assert ledger["digest_verification"]["status"] == "PASS"
    assert ledger["digest_verification"]["mismatches"] == []
    assert ledger["fallback_fraction"]["value"] is None
    assert ledger["fallback_fraction"]["reason"].strip()
    pilot_cells = {cell["cell"]: cell for cell in pilot["cells"]}
    for cell in ledger["cells"]:
        schema = cell["parameter_schema"]
        assert schema["sha256"]
        assert schema["object"]["parameters"], "the schema object is empty"
        artifact = pilot_cells[cell["cell"]]
        for arm in ("M4_CAL", "M4_REGIME"):
            block = cell["arms"][arm]
            record = artifact["arms"][arm]
            assert block["selected_digest"] == record["selected_digest"]
            assert len(block["cutoffs"]) == record["fold_count"]
            assert (sum(cutoff["trials"]["retained"] for cutoff in block["cutoffs"])
                    == record["trial_count"])
            for cutoff in block["cutoffs"]:
                selection_id = f"{cell['cell']}:{arm}:fold{cutoff['fold_id']}"
                assert cutoff["training_range"]["start"]
                assert cutoff["training_range"]["end"]
                assert cutoff["training_range"]["memory_days"] == 180
                assert cutoff["evaluation_range"]["start"] == cutoff["cutoff_utc"]
                assert cutoff["activation"]["time_utc"] == cutoff["cutoff_utc"]
                assert cutoff["seed"] is not None
                assert cutoff["trials"]["configured"] == 8
                assert cutoff["selected_digest"] == digest_by_selection[selection_id]
                assert cutoff["parameter_schema_sha256"] == schema["sha256"]
                selector = cutoff["selector_status"]
                assert selector["stage"] == "is_search"
                if selector["fallback_status"] is None:
                    assert selector["fallback_reason"].strip()
                decomposition = cutoff["selection_decomposition"]
                assert decomposition["trials_in_fold"] == cutoff["trials"]["retained"]
                assert decomposition["finite_objective_values"] >= 1
                assert decomposition["selected_trial"] is not None
                assert decomposition["selected_trial"]["trial_id"] is not None


def test_rf04_transparency_digests_and_schema_hashes_recompute(lab_root):
    ledger = _load(lab_root, RF04, "mode4_transparency_ledger.json")
    for cell in ledger["cells"]:
        schema = SCHEMAS[cell["alpha_id"]].as_record()
        assert cell["parameter_schema"]["sha256"] == _canonical_sha256(schema)
        assert cell["parameter_schema"]["object"] == schema
        for arm in ("M4_CAL", "M4_REGIME"):
            for cutoff in cell["arms"][arm]["cutoffs"]:
                assert cutoff["selected_digest"] == parameter_digest(cutoff["selected_params"])


def test_rf04_report_references_gap_close_artifacts(lab_root):
    text = _read(lab_root, RF04, "report.md")
    for name in GAP_CLOSE_ARTIFACTS:
        assert name in text, f"report.md does not reference {name}"
    report = _load(lab_root, RF04, "report.json")
    coverage = _load(lab_root, RF04, "cell_coverage.json")
    full = _load(lab_root, RF04, "paired_discovery_full.json")
    assert report["coverage_ref"] == "cell_coverage.json"
    assert report["profiling_ref"] == "profiling_and_budget.json"
    assert report["transparency_ref"] == "mode4_transparency_ledger.json"
    for name in GAP_CLOSE_ARTIFACTS:
        assert report["artifact_hashes"][name], f"report.json has no hash for {name}"
    # report.json is the RF-04.1 pilot-era report; the full artifact records its
    # scope explicitly so the supersession is not silently renamed
    pilot_scope = full["superseded_pilot_scope"]["counts"]
    assert report["market_runs"]["planned_cells"] == 20
    assert report["market_runs"]["executed_cells"] == (pilot_scope["RUN_VALID"]
                                                       + pilot_scope["RUN_NOT_EVALUABLE"]) == 2
    assert report["market_runs"]["not_run_cells"] == pilot_scope["NOT_RUN"] == 8
    assert len(report["market_runs"]["blocked_cells"]) == pilot_scope[
        "BLOCKED_CAPABILITY"] == 10
    assert report["market_runs"]["insufficient_data_cells"] == pilot_scope[
        "INSUFFICIENT_DATA"]
    assert report["coverage"]["per_cell"]["A-SC/BTCUSDT"] == "RUN_NOT_EVALUABLE"
    assert report["coverage"]["per_cell"]["A-HMA/BTCUSDT"] == "RUN_VALID"
    assert "2 of 20 planned cells executed" in report["claim"]["scope"]
    assert coverage["counts"]["RUN_VALID"] == 10, (
        "the current coverage is the full-cohort supersession of the pilot scope")
    assert coverage["counts"]["NOT_RUN"] == 0
    assert report["performance"]["profile_ref"] == "profiling_and_budget.json"
    assert report["performance"]["peak_rss_bytes"] is None
    assert report["performance"]["cpu_seconds"] is None
