"""TE03.7 guards: measured positive/null denominators, recovered +2-delta
control, non-false-positive null, the sharded full-path funnel with real
denominators and reasons, and the complete 32-trial shard selection result."""
import sqlite3

from crypto_regime_lab.time_edge.planning import explode_worlds
from crypto_regime_lab.time_edge.storage import digest, file_digest, read

EVIDENCE = "evidence/time_edge_validation_v4"
POWER = EVIDENCE + "/te03/te03_7_power.json"
CONTROLS = EVIDENCE + "/te03/te03_7_controls_r2.json"
CONTROLS_OLD = EVIDENCE + "/te03/te03_7_controls.json"
BLOCKER = EVIDENCE + "/te03/controls_06_blocker.json"
SPEC = "handoff/te_specs/te03-controls.local.json"
PLAN = EVIDENCE + "/plans/te-host-controls-06/job.json"
FUNNEL_STEPS = {"valid_observations", "triggers", "searches", "different_params", "activated", "different_orders"}
CONTROL_STATUSES = {"FULL_PATH_STRUCTURAL_CONTROL_COMPLETED", "FULL_PATH_STRUCTURAL_CONTROL_PARTIAL", "NOT_RUN_BUDGET"}


def load(lab_root, relative):
    return read(lab_root / relative)


def test_power_artifact_has_measured_denominators_and_recovers_2delta(lab_root):
    power = load(lab_root, POWER)
    assert power["schema"] == "regime_lab.te03_power_null_calibration.v1"
    assert len(power["conditions"]) == 4
    effects = {row["true_effect_delta_units"] for row in power["conditions"]}
    assert effects == {0., 1., 2., 4.}
    for row in power["conditions"]:
        assert row["worlds"] > 0 and 0. <= row["rate"] <= 1.
        assert row["wilson95"][0] <= row["rate"] + 1e-12 and row["wilson95"][1] >= row["rate"] - 1e-12
    positive = power["positive_control"]
    assert positive["worlds"] > 0 and positive["denominator"] == positive["worlds"]
    assert len(positive["per_hypothesis_power"]) == 4
    assert positive["recovered"] is True
    assert min(positive["per_hypothesis_power"]) >= .8
    assert power["engine_runs"] == 0
    assert power["source"]["full_pipeline_calibration"] == "NOT_EXECUTED_BY_THIS_TASK"


def test_null_control_is_not_a_false_positive(lab_root):
    power = load(lab_root, POWER)
    null = power["null_control"]
    assert null["false_positive"] is False
    assert null["maximum_family_wilson_upper"] <= null["tolerance"]
    for row in null["worlds"]:
        assert row["denominator"] == row["worlds"] > 0
        assert row["wilson95"][1] <= null["tolerance"] + 1e-12 or row["rate"] == 0.


def test_power_results_are_unchanged_from_the_earlier_run(lab_root):
    power = load(lab_root, POWER)
    positive = power["positive_control"]
    assert positive["family_rate"] == 1.0
    assert positive["per_hypothesis_power"] == [1.0, 1.0, 1.0, 0.944]
    by_effect = {row["true_effect_delta_units"]: row for row in power["conditions"]}
    assert by_effect[0.0]["family_rejections"] == 0 and by_effect[0.0]["rate"] == 0.0
    assert by_effect[1.0]["family_rejections"] == 36 and by_effect[1.0]["rate"] == 0.036
    assert by_effect[2.0]["family_rejections"] == 1000
    assert power["null_control"]["maximum_family_wilson_upper"] == 0.049435660467207834


def test_controls_artifact_supersedes_the_not_run_budget_state(lab_root):
    controls = load(lab_root, CONTROLS)
    old = load(lab_root, CONTROLS_OLD)
    assert controls["schema"] == "regime_lab.te03_full_path_controls.v1"
    assert old["status"] == "NOT_RUN_BUDGET"
    assert controls["supersedes"]["path"] == CONTROLS_OLD
    assert controls["supersedes"]["sha256"] == file_digest(lab_root / CONTROLS_OLD)
    assert controls["full_path_funnel"]["schema"] == "regime_lab.te03_activation_funnel.v1"


def test_measured_funnels_carry_denominators_and_reasons(lab_root):
    controls = load(lab_root, CONTROLS)
    assert controls["status"] in CONTROL_STATUSES
    by_condition = controls["full_path_funnels_by_condition"]
    assert set(by_condition) <= {"NULL_STATIONARY", "RECURRING_OPPORTUNITY"}
    if controls["status"] == "NOT_RUN_BUDGET":
        assert not by_condition
        assert {row["step"] for row in controls["full_path_funnel"]["steps"]} == FUNNEL_STEPS
        for step in controls["full_path_funnel"]["steps"]:
            assert step["count"] is None and step["denominator"] is None
            assert step["reason"] and step["denominator_reason"]
        # Partial shards carry their sealed measured counts, never zero-filled.
        assert controls["partial_funnels"], "a timed-out shard must publish its partial funnel"
        for funnel in controls["partial_funnels"]:
            assert funnel["status"] == "NOT_RUN_BUDGET"
            steps = {row["step"]: row for row in funnel["steps"]}
            for row in steps.values():
                assert row["count"] is None and row["reason"]
            partial = funnel["partial_measurements"]
            assert partial["searches_completed"] == steps["searches"]["measured_partial"]
            assert partial["worlds_generated"] == 5
            assert partial["features_built"] is True
            assert partial["targets_completed"] <= partial["targets_planned"]
            assert partial["emissions_emitted"] is False
        return
    assert by_condition
    for funnel in by_condition.values():
        assert funnel["status"] == "MEASURED"
        assert {row["step"] for row in funnel["steps"]} == FUNNEL_STEPS
        for step in funnel["steps"]:
            assert step.get("rule")
            assert step["count"] is not None, f"{funnel['condition']}/{step['step']} lacks a measured count"
            assert isinstance(step["count"], int) and step["count"] >= 0
            assert isinstance(step["denominator"], int)
            assert step["count"] <= step["denominator"]
            if step["denominator"] == 0:
                assert step["denominator_reason"]


def test_selection_results_expose_params_objective_components_fills(lab_root):
    controls = load(lab_root, CONTROLS)
    assert controls["selection_results"], "each attempted shard must export its bank selection"
    assert len(controls["selection_results"]) == controls["sharding"]["shards_attempted"]
    for result in controls["selection_results"]:
        assert result["params"] and result["objective"] is not None
        assert result["trials_configured"] == 32
        assert result["trials_completed"] == 32
        assert len(result["trial_objectives"]) == 32
        assert any(trial["objective"] is not None for trial in result["trial_objectives"])
        assert set(result["components"]) >= {"mean_is_sharpe", "mean_oos_sharpe", "mean_decay", "std_decay"}
        candidate = result["selected_candidate"]
        assert candidate is not None and candidate["status"] == "EVALUATED"
        assert candidate["fill_count"] == len(candidate["fills"])
        for fill in candidate["fills"]:
            assert {"absolute_bar_index", "side", "qty", "price", "fee"} <= set(fill)
        assert result["partial"] is True and result["shard_status"] in ("TIMED_OUT", "FAILED", "BLOCKED")
    assert controls["fabricated_fills"] is False


def test_shards_are_exploded_one_registered_world_per_task(lab_root):
    spec = load(lab_root, SPEC)
    expanded = explode_worlds(spec["tasks"])
    assert len(expanded) == 10
    assert len({task["task_id"] for task in expanded}) == 10
    assert {task["world"] for task in expanded} == {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT"}
    for task in expanded:
        assert task["kind"] == "full_control"
        assert task["wall_seconds"] <= 18000, "REV10 registered an 18000s/pass shard cap at the measured lower bound"
    job = load(lab_root, PLAN)
    assert job["stage"] == "controls"
    assert len(job["tasks"]) == 10
    for task in job["tasks"]:
        assert task["kind"] == "full_control" and task["world"] in spec["worlds"]
        assert task["wall_seconds"] <= 2700
    assert job["budget_revision"]["revision_id"] == "TE02-PILOT-R03-REV09"


def test_controls_blocker_records_real_numbers(lab_root):
    controls = load(lab_root, CONTROLS)
    blocker = load(lab_root, BLOCKER)
    if controls["status"] != "NOT_RUN_BUDGET":
        return
    assert blocker["schema"] == "regime_lab.te_controls_blocker.v1"
    assert blocker["status"] == "NOT_RUN_BUDGET" and blocker["reason"]
    measured = blocker["measured"]
    assert measured["shards_planned"] == 10
    assert measured["shards_attempted"] >= 1 and measured["shards_completed"] == 0
    assert measured["attempt_wall_seconds"]
    assert measured["bank_selection_32_trials"]["complete"] is True
    for funnel in [blocker["funnel"]]:
        for step in funnel["steps"]:
            assert step["count"] is None and step["reason"]
    assert blocker["claim_limits"]["te04"] == "LOCKED"


def test_controls_task_statuses_match_the_run_ledger(lab_root):
    controls = load(lab_root, CONTROLS)
    directory = lab_root / EVIDENCE / "runs" / controls["run_id"]
    job = read(directory / "job.json")
    con = sqlite3.connect(directory / "ledger.sqlite")
    rows = con.execute("SELECT task,status FROM attempt ORDER BY started").fetchall()
    con.close()
    by_task = {}
    for task, status in rows:
        by_task.setdefault(task, []).append(status)
    for row in controls["tasks"]:
        task = next(item for item in job["tasks"] if item["task_id"] == row["task_id"])
        key = digest({"identity": {"job_hash": digest(job)}, "task": task})
        statuses = by_task.get(key, [])
        if row["status"] == "NOT_RUN_BUDGET":
            assert not statuses
        else:
            assert statuses and statuses[-1] == row["status"]


def test_report_renders_the_revised_controls(lab_root):
    controls = load(lab_root, CONTROLS)
    report = (lab_root / "reports/time_edge_validation_v4/te03-7-report.md").read_text()
    assert controls["status"] in report
    assert "TE-04" in report
    if controls["status"] != "NOT_RUN_BUDGET":
        for funnel in controls["full_path_funnels_by_condition"].values():
            for step in funnel["steps"]:
                if step["count"] is not None:
                    assert f"| {step['step']} | {step['count']} | {step['denominator']} |" in report


def test_delayed_and_risk_controls_are_not_misreported(lab_root):
    power = load(lab_root, POWER)
    assert power["delayed_risk_controls"]["status"] == "TE04_SCOPE_NOT_STARTED"
    assert "TE-04" in power["delayed_risk_controls"]["reason"]


def test_allocation_revisions_keep_prior_charges(lab_root):
    directory = lab_root / EVIDENCE / "allocations/TE02-PILOT-R03"
    con = sqlite3.connect(directory / "ledger.sqlite")
    revisions = con.execute("SELECT id,old_budget,new_budget,prior_charged FROM budget_revision ORDER BY applied_at").fetchall()
    con.close()
    ids = [row[0] for row in revisions]
    assert "TE02-PILOT-R03-REV05" in ids and "TE02-PILOT-R03-REV09" in ids
    for old, new, charged in [(row[1], row[2], row[3]) for row in revisions]:
        assert new > old and charged >= 0
    rev09 = read(lab_root / EVIDENCE / "allocations/revisions/TE02-PILOT-R03-REV09.json")
    assert rev09["total_wall_seconds"] == 105400.0 and rev09["reserved_future_wall_seconds"] == 5400.0
    assert rev09["task_wall_seconds"] == 600.0 and rev09["selection_task_wall_seconds"] == 2700.0
    assert rev09["per_arm_compute_is_unchanged"] is True
