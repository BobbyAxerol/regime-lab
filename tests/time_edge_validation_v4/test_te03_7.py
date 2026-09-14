"""TE03.7 guards: real calibration denominators, recovered positive control,
non-false-positive null, and a funnel that is null with reasons when bounded."""
import sqlite3

from crypto_regime_lab.time_edge.storage import digest, read

EVIDENCE = "evidence/time_edge_validation_v4"


def load(lab_root, relative):
    return read(lab_root / relative)


def test_power_artifact_has_measured_denominators_and_recovers_2delta(lab_root):
    power = load(lab_root, EVIDENCE + "/te03/te03_7_power.json")
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
    power = load(lab_root, EVIDENCE + "/te03/te03_7_power.json")
    null = power["null_control"]
    assert null["false_positive"] is False
    assert null["maximum_family_wilson_upper"] <= null["tolerance"]
    for row in null["worlds"]:
        assert row["denominator"] == row["worlds"] > 0
        assert row["wilson95"][1] <= null["tolerance"] + 1e-12 or row["rate"] == 0.


def test_controls_funnel_is_null_with_reasons_when_budget_stops_it(lab_root):
    controls = load(lab_root, EVIDENCE + "/te03/te03_7_controls.json")
    assert controls["schema"] == "regime_lab.te03_full_path_controls.v1"
    funnel = controls["full_path_funnel"]
    assert funnel["schema"] == "regime_lab.te03_activation_funnel.v1"
    steps = {row["step"] for row in funnel["steps"]}
    assert steps == {"valid_observations", "triggers", "searches", "different_params", "activated", "different_orders"}
    if controls["status"] == "NOT_RUN_BUDGET":
        assert funnel["status"] == "NOT_RUN_BUDGET"
        assert all(row["count"] is None and row["reason"] for row in funnel["steps"])
        assert controls["fabricated_fills"] is False
        assert controls["boundary_power_qualification"] == "NOT_EVALUABLE_FROM_STRUCTURAL_WORLD_ALONE"
    else:
        assert funnel["status"] == "MEASURED"
        counts = {row["step"]: row["count"] for row in funnel["steps"]}
        assert counts["valid_observations"] is not None and counts["triggers"] is not None


def test_controls_task_statuses_match_the_run_ledger(lab_root):
    controls = load(lab_root, EVIDENCE + "/te03/te03_7_controls.json")
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


def test_delayed_and_risk_controls_are_not_misreported(lab_root):
    power = load(lab_root, EVIDENCE + "/te03/te03_7_power.json")
    assert power["delayed_risk_controls"]["status"] == "TE04_SCOPE_NOT_STARTED"
    assert "TE-04" in power["delayed_risk_controls"]["reason"]


def test_allocation_revisions_keep_prior_charges(lab_root):
    directory = lab_root / EVIDENCE / "allocations/TE02-PILOT-R03"
    con = sqlite3.connect(directory / "ledger.sqlite")
    revisions = con.execute("SELECT id,old_budget,new_budget,prior_charged FROM budget_revision ORDER BY applied_at").fetchall()
    con.close()
    ids = [row[0] for row in revisions]
    assert "TE02-PILOT-R03-REV04" in ids and "TE02-PILOT-R03-REV05" in ids
    for old, new, charged in [(row[1], row[2], row[3]) for row in revisions]:
        assert new > old and charged >= 0
