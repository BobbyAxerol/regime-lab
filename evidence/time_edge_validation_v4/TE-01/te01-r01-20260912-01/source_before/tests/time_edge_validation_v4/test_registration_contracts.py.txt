"""TE-01 arithmetic, protocol mutation and closed-runtime-gate checks.

Synthetic reported-equity fixtures are arithmetic oracles, not engine results.
"""
import copy
from datetime import datetime, timedelta, timezone
import math
import json
import hashlib
from pathlib import Path
import random
import shutil

import pytest

from crypto_regime_lab.experiments import time_edge_contracts as c


ROOT = Path(__file__).resolve().parents[2]
REGISTER = ROOT / "configs/time_edge_validation_v4/r01"


def test_first_fee_is_retained_and_partition_compounds():
    rows = [("2021-01-01", 99.0), ("2021-01-02", 108.9), ("2021-01-03", 98.01)]
    common = dict(initial_equity=100.0)
    whole = c.daily_returns(rows, start="2021-01-01T00:00:00Z", end="2021-01-04T00:00:00Z", **common)
    first = c.daily_returns(rows, start="2021-01-01T00:00:00Z", end="2021-01-02T00:00:00Z", **common)
    rest = c.daily_returns(rows, start="2021-01-02T00:00:00Z", end="2021-01-04T00:00:00Z", **common)
    assert [v for _, v in whole] == pytest.approx([-0.01, 0.1, -0.1])
    assert whole == first + rest
    assert math.prod(1+r for _, r in whole) - 1 == pytest.approx(98.01/100-1)
    assert (99-100) + (98.01-99) == pytest.approx(98.01-100)


def test_warmup_prefix_does_not_change_scored_returns():
    a = [("2020-12-31", 100), ("2021-01-01", 102), ("2021-01-02", 101)]
    b = [("2020-12-30", 95), *a]
    kw = dict(start="2021-01-01T00:00:00Z", end="2021-01-03T00:00:00Z")
    assert c.daily_returns(a, initial_equity=90, **kw) == c.daily_returns(b, initial_equity=80, **kw)


def test_random_capital_scaling_and_half_open_partitions():
    rng = random.Random(20260912)
    date = datetime(2021, 1, 1, tzinfo=timezone.utc)
    prices, equity = [], 100.0
    for i in range(90):
        equity *= 1+rng.uniform(-0.02, 0.02)
        prices.append(((date+timedelta(days=i)).date().isoformat(), equity))
    kw = dict(start=date.isoformat(), end=(date+timedelta(days=90)).isoformat())
    base = c.daily_returns(prices, initial_equity=100, **kw)
    scaled = c.daily_returns([(d, v*37) for d, v in prices], initial_equity=3700, **kw)
    assert [r for _, r in base] == pytest.approx([r for _, r in scaled], abs=1e-14)
    pieces = []
    for lo, hi in ((0, 19), (19, 45), (45, 90)):
        pieces += c.daily_returns(prices, initial_equity=100,
                                  start=(date+timedelta(days=lo)).isoformat(),
                                  end=(date+timedelta(days=hi)).isoformat())
    assert pieces == base


@pytest.mark.parametrize("rows", [[], [("2021-01-01", 100)],
    [("2021-01-01", 100), ("2021-01-01", 101)],
    [("2021-01-01", 100), ("2021-01-03", 101)],
    [("2021-01-02", 101), ("2021-01-01", 100)],
    [("2021-01-01", 100), ("2021-01-02", float("nan"))]])
def test_bad_daily_coverage_or_nonfinite_is_not_cash(rows):
    with pytest.raises(c.ContractError):
        c.daily_returns(rows, initial_equity=100, start="2021-01-01T00:00:00Z", end="2021-01-03T00:00:00Z")


@pytest.mark.parametrize("value", ["2021-01-01", "2021-01-01T00:00:00", "2021-01-01T00:00:00+07:00"])
def test_registration_requires_explicit_utc(value):
    with pytest.raises(c.ContractError):
        c.utc(value)


def test_only_loss_and_no_loss_pf_are_distinct():
    assert c.observation_pf([-0.01, -0.03])["value"] == 0
    assert c.observation_pf([-0.01, -0.03])["status"] == "OK"
    assert c.observation_pf([0.01, 0.03])["status"] == "NO_LOSS_DENOMINATOR"
    assert c.observation_pf([0, 0])["status"] == "NO_LOSS_DENOMINATOR"
    assert c.observation_pf([])["status"] == "INSUFFICIENT_OBSERVATIONS"
    assert c.observation_pf([0.03, -0.02, 0.01])["value"] == pytest.approx(2)


@pytest.mark.parametrize("value", [0, -1, None, float("inf"), float("nan"), True])
def test_pf_log_gap_never_manufactures_finite_result(value):
    assert c.pf_log_gap(value, 2)["value"] is None
    assert c.pf_log_gap(2, value)["value"] is None


def test_pf_log_gap_antisymmetric():
    assert c.pf_log_gap(4, 2)["value"] == pytest.approx(math.log(2))
    assert c.pf_log_gap(2, 4)["value"] == pytest.approx(-math.log(2))


def test_daily_sharpe_sample_variance_and_no_bar_fallback():
    values = [-0.02, 0.01, 0.03]
    mean = sum(values)/3
    expected = math.sqrt(365)*mean/math.sqrt(sum((x-mean)**2 for x in values)/2)
    assert c.daily_sharpe(values)["value"] == pytest.approx(expected)
    assert c.daily_sharpe([0.01, 0.01])["status"] == "ZERO_VARIANCE"
    assert c.daily_sharpe([0.01])["status"] == "INSUFFICIENT_OBSERVATIONS"


def test_pair_by_common_date_not_row_number():
    left = [("2021-01-01", 0.2), ("2021-01-02", 0.1)]
    right = [("2021-01-02", 0.03), ("2021-01-03", 0.04)]
    with pytest.raises(c.ContractError):
        c.paired_difference(left, right)
    result = c.paired_difference(left, right, allow_partial=True)
    assert result["values"] == pytest.approx([0.07])
    assert result["partial"] and len(result["unmatched_dates"]) == 2


def test_allocation_cost_units_a15():
    value = c.economic_uncertainty(round_trip_rate=0.001, round_trips_per_day=0.064, notional_over_equity=0.1)
    assert value == pytest.approx(0.0000064)
    assert value*10000 == pytest.approx(0.064)
    assert c.economic_uncertainty(round_trip_rate=0.001, round_trips_per_day=0.064, notional_over_equity=1) == pytest.approx(10*value)


def test_holm_preserves_family_and_unsorted_mapping():
    assert c.holm_adjust([0.04, 0.001, 0.02, 1]) == pytest.approx([0.08, 0.004, 0.06, 1])
    assert c.holm_adjust([0.01, 0.01, 0.03]) == pytest.approx([0.03, 0.03, 0.03])
    with pytest.raises(c.ContractError):
        c.holm_adjust([])


CHECKS = {k: True for k in ("execution_valid", "data_valid", "treatment_valid", "support_sufficient",
                           "calibration_passed", "family_complete", "threshold_materialized")}


@pytest.mark.parametrize("blocker", list(CHECKS))
def test_any_invalidity_blocks_strong_economic_interval(blocker):
    checks = {**CHECKS, blocker: False}
    assert c.economic_claim(lower=0.02, upper=0.03, delta=0.001, adjusted_p=0.001,
                            checks=checks, risk_pass=True)["status"] == "NOT_EVALUABLE"


@pytest.mark.parametrize("lower,upper,expected", [(0.001,0.002,"INCONCLUSIVE"),
    (0.0011,0.002,"POSITIVE_WITHIN_TESTED_SCOPE"),
    (-0.002,0.0009,"NO_MEANINGFUL_IMPROVEMENT_WITHIN_SCOPE"),
    (-0.002,0.001,"INCONCLUSIVE")])
def test_claim_uses_economic_threshold_with_strict_boundaries(lower, upper, expected):
    assert c.economic_claim(lower=lower, upper=upper, delta=0.001, adjusted_p=0.01,
                            checks=CHECKS, risk_pass=True)["status"] == expected


def test_no_positive_claim_without_adjustment_or_risk():
    kw = dict(lower=0.002, upper=0.003, delta=0.001, checks=CHECKS)
    assert c.economic_claim(**kw, adjusted_p=0.2, risk_pass=True)["status"] == "INCONCLUSIVE"
    assert c.economic_claim(**kw, adjusted_p=0.01, risk_pass=False)["status"] == "INCONCLUSIVE"


def test_outcome_end_not_origin_defines_training_eligibility():
    times = ["2021-01-01T00:00:00Z", "2021-01-02T00:00:00Z", "2021-01-03T00:00:00Z"]
    assert c.available_training_origins(times, cutoff="2021-01-02T00:00:00Z") == [0]


def test_resume_counts_failures_and_refuses_missing_or_changed_identity():
    attempts = [{"attempt_id": "a", "status": "FAILED", "wall_seconds": 20},
                {"attempt_id": "b", "status": "SCORED", "wall_seconds": 30}]
    assert c.remaining_budget(60, attempts) == 10
    assert c.remaining_budget(40, attempts) == 0
    with pytest.raises(c.ContractError):
        c.remaining_budget(60, [*attempts, attempts[0]])
    for before, after in (({"source": "old"}, {"source": "new"}), ({}, {})):
        with pytest.raises(c.ContractError):
            c.verify_resume_identity(before, after, ["source"])


def test_registered_protocol_validates_but_never_authorizes_market_execution():
    result = c.validate_registration(c.load_registration(REGISTER))
    assert result["runtime_ready"] is False
    with pytest.raises(c.ContractError):
        c.require_runtime_ready({})


@pytest.mark.parametrize("file,keys,value", [
    ("study_registration.json", ["mode4","oos_used_for_selection"], True),
    ("study_registration.json", ["mode4","optimization_mode"], "mode_1"),
    ("study_registration.json", ["cohort","planned_cells"], 19),
    ("study_registration.json", ["data_role"], "UNTOUCHED"),
    ("evaluation_windows.json", ["warmup","score"], True),
    ("evaluation_windows.json", ["interval_convention"], "[start,end]"),
    ("metric_contract.json", ["sharpe","periods_per_year"], 252),
    ("metric_contract.json", ["sharpe","ddof"], 0),
    ("metric_contract.json", ["decay","age_horizons"], [[0,91],[90,181],[180,270]]),
    ("statistical_analysis_plan.json", ["family","size"], 2),
    ("statistical_analysis_plan.json", ["economic_threshold","unit"], "notional_return/day"),
    ("model_protocol.json", ["full_sample_scaled_z_forbidden"], False),
    ("execution_contract.json", ["engine_source_mutations_allowed"], True),
    ("execution_contract.json", ["primary_execution_resolution"], "1h"),
    ("execution_contract.json", ["calendar_matched","future_regime_refit_count_allowed"], True),
    ("compute_budget.json", ["phase_te01","engine_runs"], 1)])
def test_protocol_mutations_are_rejected(file, keys, value):
    bundle = copy.deepcopy(c.load_registration(REGISTER))
    target = bundle[file]
    for key in keys[:-1]:
        target = target[key]
    target[keys[-1]] = value
    with pytest.raises(c.ContractError):
        c.validate_registration(bundle)


@pytest.mark.parametrize("file,keys,value", [
    ("statistical_analysis_plan.json", ["bootstrap","draws"], None),
    ("statistical_analysis_plan.json", ["bootstrap","draws"], float("nan")),
    ("statistical_analysis_plan.json", ["bootstrap","draws"], 3),
    ("statistical_analysis_plan.json", ["bootstrap","primary_block_days"], 0),
    ("statistical_analysis_plan.json", ["support","minimum_common_days"], -1),
    ("execution_contract.json", ["fees","one_way_taker_rate"], -0.1),
    ("study_registration.json", ["market_run_authorized_by_this_phase"], True)])
def test_unresolved_or_invalid_scientific_values_refuse_registration(file, keys, value):
    bundle = c.load_registration(REGISTER)
    target = bundle[file]
    for key in keys[:-1]:
        target = target[key]
    target[keys[-1]] = value
    with pytest.raises(c.ContractError):
        c.validate_registration(bundle)


def test_installed_mode4_config_requires_positive_trials_and_matches_frozen_knobs():
    from quantbt.walkforward import WalkForwardConfig
    from quantbt.core.research_audit import RESEARCH_RETENTION_LEVELS_V1
    binding = json.loads((REGISTER.parent / "mode4_binding_r01.json").read_text())
    config = binding["resolved_config"]
    with pytest.raises(ValueError, match="optuna_trials"):
        WalkForwardConfig(optimization_mode="mode_4_is_only_robust", optimization_schedule="per_fold_causal", optuna_trials=0)
    actual = WalkForwardConfig(**config)
    assert {name: getattr(actual, name) for name in config} == config
    assert "full_trial_ledger" in RESEARCH_RETENTION_LEVELS_V1
    assert binding["search_seed"] == actual.random_seed


def test_empty_or_boolean_only_runtime_readiness_cannot_pass():
    record = {key: True for key in ("fup02_final_handoff", "source_identity_verified", "os_isolation_verified",
        "economic_engine_qualified", "model_and_controls_qualified", "economic_threshold_materialized",
        "total_budget_allocated", "no_affected_p0")}
    with pytest.raises(c.ContractError, match="without evidence"):
        c.require_runtime_ready(record)
    with pytest.raises(c.ContractError, match="proof reference"):
        c.require_runtime_ready(record, evidence_root=ROOT)


def test_registered_file_tamper_is_rejected_before_validation(lab_tmp):
    target = lab_tmp / "registration"
    shutil.copytree(REGISTER, target)
    path = target / "metric_contract.json"
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(c.ContractError, match="hash drift"):
        c.load_registration(target)


@pytest.mark.parametrize("defect", ["hash", "wrong_source", "empty_measurements", "path_escape"])
def test_runtime_proof_cannot_pass_on_stale_or_empty_evidence(lab_tmp, defect):
    keys = ("fup02_final_handoff", "source_identity_verified", "os_isolation_verified",
            "economic_engine_qualified", "model_and_controls_qualified", "economic_threshold_materialized",
            "total_budget_allocated", "no_affected_p0")
    record = {key: True for key in keys}
    record.update(source_manifest_sha256="a"*64, evidence_refs={})
    for key in keys:
        proof = {"study_id": "time_edge_validation_v4", "gate_id": key, "status": "VERIFIED",
                 "source_manifest_sha256": "a"*64, "measurements": {"fixture_only": True}}
        if key == keys[-1]:
            if defect == "wrong_source":
                proof["source_manifest_sha256"] = "b"*64
            if defect == "empty_measurements":
                proof["measurements"] = {}
        data = json.dumps(proof).encode()
        (lab_tmp / (key + ".json")).write_bytes(data)
        record["evidence_refs"][key] = {"path": key + ".json", "sha256": hashlib.sha256(data).hexdigest()}
    if defect == "hash":
        record["evidence_refs"][keys[-1]]["sha256"] = "f"*64
    if defect == "path_escape":
        record["evidence_refs"][keys[-1]]["path"] = "../outside.json"
    with pytest.raises(c.ContractError):
        c.require_runtime_ready(record, evidence_root=lab_tmp)
