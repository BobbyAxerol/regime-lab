"""TE-01 analysis/registration contracts; never an execution or accounting engine.

Arithmetic consumes already reported daily equity/returns. No orders, fills,
cash updates, strategy calls, optimization, or market loading occur here.
Existing RF/FUP callers are intentionally not redirected during their run.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
from statistics import fmean, stdev


class ContractError(ValueError):
    """A required definition, input or prerequisite is not satisfied."""


def finite(value, name="value"):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ContractError(f"{name} must be a finite number")
    return float(value)


def utc(value, *, day_label=False):
    if not isinstance(value, str):
        raise ContractError("timestamp must be a string")
    if day_label and len(value) == 10:
        value += "T00:00:00+00:00"
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError("invalid timestamp") from exc
    if result.tzinfo is None or result.utcoffset() != timedelta(0):
        raise ContractError("explicit UTC timestamp required")
    return result.astimezone(timezone.utc)


def daily_returns(rows, *, initial_equity, start, end):
    """UTC day-labelled close marks, with first fee retained before window masking.

``initial_equity`` is the pre-fee balance before the FIRST supplied account mark,
not a replacement denominator at each evaluation/fold boundary.
"""
    lo, hi = utc(start), utc(end)
    if lo >= hi or any(t.time() != datetime.min.time() for t in (lo, hi)):
        raise ContractError("daily score window must be nonempty UTC midnights")
    previous_equity = finite(initial_equity, "initial equity")
    if previous_equity <= 0:
        raise ContractError("initial equity must be positive")
    previous_time = None
    result = []
    for date, equity in rows:
        date = utc(date, day_label=True)
        equity = finite(equity, "reported equity")
        if date.time() != datetime.min.time():
            raise ContractError("equity observations must carry UTC day labels")
        if previous_time is not None and date != previous_time + timedelta(days=1):
            raise ContractError("missing, duplicate or unordered daily marks")
        if previous_equity <= 0:
            raise ContractError("nonpositive preceding equity; retain bankruptcy evidence, do not clip returns")
        value = equity / previous_equity - 1.0
        if lo <= date < hi:
            result.append((date.date().isoformat(), value))
        previous_time, previous_equity = date, equity
    expected = int((hi - lo).days)
    if len(result) != expected:
        raise ContractError(f"score coverage missing: {len(result)}/{expected} days")
    return result


def observation_pf(values):
    values = [finite(x, "return") for x in values]
    if not values:
        return {"value": None, "status": "INSUFFICIENT_OBSERVATIONS", "observations": 0}
    gains = math.fsum(x for x in values if x > 0)
    losses = -math.fsum(x for x in values if x < 0)
    return {"value": gains / losses if losses > 0 else None,
            "status": "OK" if losses > 0 else "NO_LOSS_DENOMINATOR",
            "observations": len(values), "gain_sum": gains, "loss_sum": losses,
            "definition": "daily_return_observation_pf_not_trade_pf"}


def daily_sharpe(values, *, risk_free_daily=0.0):
    rf = finite(risk_free_daily)
    values = [finite(x, "return") - rf for x in values]
    if len(values) < 2:
        return {"value": None, "status": "INSUFFICIENT_OBSERVATIONS"}
    deviation = stdev(values)
    if deviation == 0:
        return {"value": None, "status": "ZERO_VARIANCE"}
    return {"value": math.sqrt(365) * fmean(values) / deviation, "status": "OK"}


def pf_log_gap(left, right):
    for value in (left, right):
        if value is None or not isinstance(value, (int, float)) or isinstance(value, bool):
            return {"value": None, "status": "PF_LOG_DOMAIN_INVALID"}
        if not math.isfinite(value) or value <= 0:
            return {"value": None, "status": "PF_LOG_DOMAIN_INVALID"}
    return {"value": math.log(left) - math.log(right), "status": "OK"}


def paired_difference(left, right, *, allow_partial=False):
    """Join date-labelled RETURNS, never ordinal folds; disclose omitted dates."""
    def index(rows):
        result = {}
        for date, value in rows:
            key = utc(date, day_label=True).isoformat()
            if key in result:
                raise ContractError("duplicate paired date")
            result[key] = finite(value, "paired return")
        return result
    left, right = index(left), index(right)
    common = sorted(left.keys() & right.keys())
    unmatched = sorted(left.keys() ^ right.keys())
    if not common or (unmatched and not allow_partial):
        raise ContractError("paired dates lack registered common coverage")
    return {"dates": common, "values": [left[d] - right[d] for d in common],
            "unmatched_dates": unmatched, "partial": bool(unmatched)}


def economic_uncertainty(*, round_trip_rate, round_trips_per_day, notional_over_equity):
    inputs = [finite(x) for x in (round_trip_rate, round_trips_per_day, notional_over_equity)]
    if any(x < 0 for x in inputs):
        raise ContractError("uncertainty rate, turnover and allocation cannot be negative")
    return math.prod(inputs)


def holm_adjust(pvalues):
    pvalues = [finite(x, "p-value") for x in pvalues]
    if not pvalues or any(x < 0 or x > 1 for x in pvalues):
        raise ContractError("nonempty p-values in [0,1] required")
    order = sorted(range(len(pvalues)), key=pvalues.__getitem__)
    result, previous = [0.0] * len(order), 0.0
    for rank, index in enumerate(order):
        previous = max(previous, min(1.0, (len(order) - rank) * pvalues[index]))
        result[index] = previous
    return result


def economic_claim(*, lower, upper, delta, adjusted_p, checks, risk_pass, alpha=0.05):
    required = ("execution_valid", "data_valid", "treatment_valid", "support_sufficient",
                "calibration_passed", "family_complete", "threshold_materialized")
    blockers = [key for key in required if checks.get(key) is not True]
    if blockers:
        return {"status": "NOT_EVALUABLE", "blockers": blockers}
    lower, upper, delta, p, alpha = [finite(x) for x in (lower, upper, delta, adjusted_p, alpha)]
    if lower > upper or delta < 0 or not 0 <= p <= 1 or not 0 < alpha < 1:
        raise ContractError("invalid interval, threshold or significance level")
    if lower > delta and p <= alpha and risk_pass is True:
        status = "POSITIVE_WITHIN_TESTED_SCOPE"
    elif upper < delta:
        status = "NO_MEANINGFUL_IMPROVEMENT_WITHIN_SCOPE"
    else:
        status = "INCONCLUSIVE"
    return {"status": status, "underperformed": upper < 0,
            "risk_pass": risk_pass is True, "deployment_eligibility": "NOT_ASSESSED"}


def available_training_origins(outcome_times, *, cutoff):
    cutoff = utc(cutoff)
    return [i for i, timestamp in enumerate(outcome_times) if utc(timestamp) < cutoff]


def remaining_budget(allocated, attempts):
    allocated = finite(allocated, "allocated budget")
    costs = [finite(row["wall_seconds"], "attempt wall seconds") for row in attempts]
    if allocated < 0 or any(cost < 0 for cost in costs):
        raise ContractError("budget and measured costs must be nonnegative")
    ids = [row["attempt_id"] for row in attempts]
    if len(set(ids)) != len(ids):
        raise ContractError("duplicate attempt ID")
    return max(0.0, allocated - math.fsum(costs))


def verify_resume_identity(previous, current, required_fields):
    if not required_fields or any(k not in previous or k not in current for k in required_fields):
        raise ContractError("missing resume identity")
    if any(previous[k] != current[k] for k in required_fields):
        raise ContractError("resume identity changed")


def load_registration(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "registration_manifest.json").read_text())
    bundle = {}
    for entry in manifest["artifacts"]:
        name = entry["path"]
        if Path(name).name != name:
            raise ContractError("registration path must be local filename")
        data = (directory / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise ContractError(f"registration hash drift: {name}")
        bundle[name] = json.loads(data)
    return bundle


def validate_registration(bundle):
    def complete(value, path="registration"):
        if value is None:
            raise ContractError(f"unresolved required field: {path}")
        if isinstance(value, float) and not math.isfinite(value):
            raise ContractError(f"nonfinite registration field: {path}")
        if isinstance(value, dict):
            for key, item in value.items():
                complete(item, path + "." + key)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                complete(item, f"{path}[{index}]")
    complete(bundle)
    required = {"study_registration.json", "metric_contract.json", "evaluation_windows.json",
                "statistical_analysis_plan.json", "model_protocol.json", "execution_contract.json",
                "compute_budget.json", "reuse_policy.json", "case_registry.json",
                "te01_execution_checklist.json"}
    if set(bundle) != required:
        raise ContractError("registration file set differs from required protocol")
    for payload in bundle.values():
        if payload.get("study_id") != "time_edge_validation_v4" or payload.get("registration_id") != "TE01-R01":
            raise ContractError("registration identity mismatch")
        utc(payload["registered_at_utc"])
    study = bundle["study_registration.json"]
    if study["primary_arms"] != ["M4_CAL", "M4_REGIME"]:
        raise ContractError("primary arms changed")
    mode = study["mode4"]
    for key, value in {"optimization_mode": "mode_4_is_only_robust",
                       "optimization_schedule": "per_fold_causal",
                       "candidate_selection_metric": "is_only_robust",
                       "scoring_backend": "endpoint", "research_retention": "full_trial_ledger",
                       "oos_used_for_selection": False}.items():
        if key not in mode or type(mode[key]) is not type(value) or mode[key] != value:
            raise ContractError(f"Mode 4 contract mismatch: {key}")
    cohort = study["cohort"]
    if (set(cohort["alphas"]) != {"A-SC", "A-HMA", "A-VWAP", "A-HASH"}
            or set(cohort["symbols"]) != {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT"}
            or len(cohort["alphas"]) != 4 or len(cohort["symbols"]) != 5
            or cohort["planned_cells"] != 20):
        raise ContractError("cohort must retain four alphas times five symbols")
    windows = bundle["evaluation_windows.json"]
    if windows["interval_convention"] != "[start,end)" or windows["warmup"]["score"] is not False:
        raise ContractError("invalid scoring boundary or warmup treatment")
    development = windows["development"]
    if utc(development["start"]) >= utc(development["end_exclusive"]):
        raise ContractError("empty development window")
    if study["data_role"] != "NESTED_RETROSPECTIVE" or windows["prospective"]["enabled"] is not False:
        raise ContractError("consumed history cannot become prospective")
    metrics = bundle["metric_contract.json"]
    if (metrics["return"]["bps_multiplier"] != 10000 or metrics["sharpe"]["ddof"] != 1
            or metrics["sharpe"]["periods_per_year"] != 365 or metrics["sharpe"]["bar_fallback"] is not False):
        raise ContractError("metric units or daily sampling changed")
    age = metrics["decay"]["age_horizons"]
    h = metrics["decay"]["age_window_days"]
    if h <= 0 or age != [[0, h], [h, 2*h], [2*h, 3*h]]:
        raise ContractError("age windows must partition three equal horizons")
    sap = bundle["statistical_analysis_plan.json"]
    ids = [x["id"] for x in sap["hypotheses"]]
    if set(ids) != {"H-TIMING", "H-BUDGET", "H-DECAY", "H-MODEL-INFO"} or len(ids) != 4:
        raise ContractError("hypothesis family incomplete or duplicated")
    if sap["family"]["size"] != len(ids) or sap["family"]["alpha"] != 0.05:
        raise ContractError("family error budget inconsistent")
    bootstrap = sap["bootstrap"]
    if (type(bootstrap["draws"]) is not int or bootstrap["draws"] < 999
            or type(bootstrap["primary_block_days"]) is not int or bootstrap["primary_block_days"] <= 0
            or type(bootstrap["seed"]) is not int):
        raise ContractError("bootstrap budget, block length or seed invalid")
    if any(type(v) is not int or v <= 0 for v in sap["support"].values() if not isinstance(v, str)):
        raise ContractError("support floors must be positive integers")
    threshold = sap["economic_threshold"]
    if (threshold["kind"] != "PREREGISTERED_COST_FUNCTION"
            or threshold["unit"] != "account_return/day"
            or finite(threshold["delta_one_way_cost"]) <= 0 or not threshold["materialization"]):
        raise ContractError("economic threshold lacks a valid preregistered derivation")
    execution = bundle["execution_contract.json"]
    if execution["engine_source_mutations_allowed"] is not False or execution["primary_execution_resolution"] != "1m":
        raise ContractError("protected engine or resolution contract changed")
    if not 0 < finite(execution["account"]["allocation_fraction"]) <= 1:
        raise ContractError("invalid allocation")
    if finite(execution["account"]["initial_equity"]) <= 0:
        raise ContractError("initial equity must be positive")
    if any(not 0 <= finite(execution["fees"][key]) < 1
           for key in ("one_way_taker_rate", "one_way_slippage_rate")):
        raise ContractError("fee/slippage rate invalid")
    if windows["initial"]["account_equity"] != execution["account"]["initial_equity"]:
        raise ContractError("initial equity mismatch")
    if execution["calendar_matched"]["future_regime_refit_count_allowed"] is not False:
        raise ContractError("calendar comparator cannot read realized future regime count")
    model = bundle["model_protocol.json"]
    if len(model["features"]) != len(set(model["features"])) or not model["features"]:
        raise ContractError("model features missing or duplicate")
    weights = model["group_weights"]
    if set(weights) != set(model["features"]) or any(finite(v) < 0 for v in weights.values()):
        raise ContractError("model weights mismatch")
    if not math.isclose(math.fsum(weights.values()), 1.0, abs_tol=1e-12):
        raise ContractError("model weights must sum to one")
    if model["full_sample_scaled_z_forbidden"] is not True:
        raise ContractError("inner model must fit raw features causally")
    budget = bundle["compute_budget.json"]
    if (budget["allocation_status"] != "TE01_ONLY_ACTIVE" or budget["phase_te01"]["engine_runs"] != 0
            or budget["phase_te01"]["optimizer_runs"] != 0 or budget["workers"] != 1):
        raise ContractError("TE-01 does not allocate engine work")
    if (study["market_run_authorized_by_this_phase"] is not False
            or any(type(v) is not int or v <= 0 for v in budget["tier_caps_seconds"].values())):
        raise ContractError("market permission or tier caps invalid")
    cases = bundle["case_registry.json"]["cases"]
    if len(cases) != 8 or len({x["case_id"] for x in cases}) != 8:
        raise ContractError("baseline cases missing or duplicated")
    return {"status": "REGISTRATION_VALIDATED_FOR_TECHNICAL_REPAIR", "protocol_files": len(bundle),
            "runtime_ready": False, "numeric_economic_threshold": "REQUIRES_TE02_CALIBRATION_FREEZE"}


def require_runtime_ready(record, *, evidence_root=None):
    """A registration pass alone can never open a market study."""
    required = ("fup02_final_handoff", "source_identity_verified", "os_isolation_verified",
                "economic_engine_qualified", "model_and_controls_qualified",
                "economic_threshold_materialized", "total_budget_allocated", "no_affected_p0")
    missing = [key for key in required if record.get(key) is not True]
    if missing:
        raise ContractError("runtime gate closed: " + ", ".join(missing))
    if evidence_root is None:
        raise ContractError("boolean readiness without evidence is insufficient")
    root = Path(evidence_root).resolve()
    refs = record.get("evidence_refs", {})
    for key in required:
        ref = refs.get(key)
        if not isinstance(ref, dict) or not ref.get("path") or not ref.get("sha256"):
            raise ContractError(f"missing runtime proof reference: {key}")
        path = (root / ref["path"]).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ContractError("runtime proof reference escapes evidence root or is absent")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != ref["sha256"]:
            raise ContractError("runtime proof hash drift")
        proof = json.loads(data)
        if (proof.get("study_id") != "time_edge_validation_v4" or proof.get("gate_id") != key
                or proof.get("status") != "VERIFIED" or not proof.get("measurements")
                or not proof.get("source_manifest_sha256")
                or proof["source_manifest_sha256"] != record.get("source_manifest_sha256")):
            raise ContractError(f"runtime proof is missing measurements or has wrong identity: {key}")
    return True
