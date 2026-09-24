"""FP03.1 -- per-dimension parameter-effect qualification (guide section 15).

For each tuning dimension of the alpha's DECLARED schema
(``selector/alpha_schemas.py``, already built for guide 7.1 -- this module
qualifies what exists, it does not invent a new search space):

* type/range/step/log/categorical mapping is read from the schema and
  cross-checked against what ``engine_param_ranges`` hands the engine;
* a fixture proves the parameter can change behavior (a real
  ``fp.evaluator.evaluate_candidate`` pair on the SAME window, params
  differing only on that one dimension);
* an out-of-schema value is a typed rejection (``ParamSchema.is_feasible``),
  never silently accepted;
* a FIXED dimension is verified to never enter the engine's search ranges.

"Không kết luận 'parameter vô tác dụng' chỉ từ một đoạn real data không có
tín hiệu phù hợp": a dimension that shows NO measured difference on one
window is reported as ``NO_DIFFERENCE_OBSERVED_ON_THIS_WINDOW``, never
``INERT`` -- those are different claims (guide's own R21-adjacent framing:
absence of evidence here is not evidence of absence).
"""
from __future__ import annotations

QUALIFICATION_SCHEMA = "regime_lab.fp03_param_qualification.v1"


def schema_mapping_rows(alpha_id: str) -> list[dict]:
    """Every declared dimension's type/range/step, cross-checked against what
    engine_param_ranges() actually hands the engine -- read live, not assumed
    to match."""
    from ..experiments.dynamic_fold_provider import engine_param_ranges
    from ..selector.alpha_schemas import SCHEMAS

    schema = SCHEMAS[alpha_id]
    engine_ranges = engine_param_ranges(alpha_id)
    rows = []
    for name, spec in schema.specs.items():
        engine_value = engine_ranges.get(name)
        row = {"name": name, "kind": spec.kind, "declared_low": spec.low,
              "declared_high": spec.high, "declared_step": spec.step,
              "declared_choices": list(spec.choices) if spec.choices else None,
              "declared_fixed_value": spec.fixed_value, "engine_value": engine_value}
        if spec.kind == "fixed":
            row["engine_mapping_consistent"] = engine_value == spec.fixed_value
        elif spec.kind == "categorical":
            row["engine_mapping_consistent"] = (
                isinstance(engine_value, list) and set(engine_value) == set(spec.choices))
        elif spec.kind == "int":
            row["engine_mapping_consistent"] = (
                isinstance(engine_value, tuple) and len(engine_value) == 3
                and int(engine_value[0]) == int(spec.low) and int(engine_value[1]) == int(spec.high))
        else:
            row["engine_mapping_consistent"] = (
                isinstance(engine_value, tuple) and len(engine_value) == 3
                and float(engine_value[0]) == float(spec.low)
                and float(engine_value[1]) == float(spec.high))
        rows.append(row)
    return rows


def unknown_value_rejections(alpha_id: str, *, base_params: dict) -> list[dict]:
    """One out-of-schema probe per non-fixed dimension: is_feasible must
    return False with a reason, never True and never raise something
    uncaught (a typed rejection, guide's own 'unknown values raise rõ')."""
    from ..selector.alpha_schemas import SCHEMAS

    schema = SCHEMAS[alpha_id]
    rows = []
    for name, spec in schema.specs.items():
        if spec.kind == "fixed":
            continue
        probe = dict(base_params)
        if spec.kind in ("int", "float", "log"):
            probe[name] = float(spec.high) + max(1.0, abs(spec.step or 1.0) * 10)
        elif spec.kind == "categorical":
            probe[name] = "__not_a_declared_choice__"
        else:
            continue
        feasible, reason = schema.is_feasible(probe)
        rows.append({"dimension": name, "probed_value": probe[name],
                    "is_feasible": feasible, "reason": reason,
                    "correctly_rejected": feasible is False and bool(reason)})
    return rows


def fixed_dimensions_never_vary(alpha_id: str) -> list[dict]:
    """Every FIXED spec's declared value must be exactly what
    engine_param_ranges() hands the engine, and it must not be a range/list
    (guide: 'no silent fallback collapse' -- a fixed dimension collapsing
    into a 1-wide range would still LOOK fixed but be a different contract)."""
    from ..experiments.dynamic_fold_provider import engine_param_ranges
    from ..selector.alpha_schemas import SCHEMAS

    schema = SCHEMAS[alpha_id]
    engine_ranges = engine_param_ranges(alpha_id)
    rows = []
    for name, spec in schema.specs.items():
        if spec.kind != "fixed":
            continue
        value = engine_ranges.get(name)
        rows.append({"dimension": name, "declared_fixed_value": spec.fixed_value,
                    "engine_value": value, "engine_value_is_scalar": not isinstance(value, (list, tuple)),
                    "matches_declared": value == spec.fixed_value})
    return rows


def behavioral_effect_fixture(cache, root, alpha_id: str, frame, base_params: dict,
                              dimension: str, low_value, high_value, *, cutoff,
                              producer: str) -> dict:
    """One real engine pair (fp.evaluator.evaluate_candidate, cached): does
    varying ONE dimension, holding the rest fixed, change the measured
    result? Two real evaluations, not a claim -- and the honest negative
    (NO_DIFFERENCE_OBSERVED_ON_THIS_WINDOW) is a valid, typed outcome, never
    silently reported as 'the parameter is inert'."""
    from . import evaluator as ev

    params_low = {**base_params, dimension: low_value}
    params_high = {**base_params, dimension: high_value}
    payload_low, event_low = ev.evaluate_candidate(cache, root, alpha_id, frame, params_low,
                                                    cutoff=cutoff, producer=f"{producer}-low")
    payload_high, event_high = ev.evaluate_candidate(cache, root, alpha_id, frame, params_high,
                                                      cutoff=cutoff, producer=f"{producer}-high")
    scalar_low = payload_low["trial_scalar"]
    scalar_high = payload_high["trial_scalar"]
    differs = (scalar_low["terminal_equity"] != scalar_high["terminal_equity"]
              or scalar_low["engine_fill_count"] != scalar_high["engine_fill_count"]
              or scalar_low["entries"] != scalar_high["entries"])
    return {
        "dimension": dimension, "low_value": low_value, "high_value": high_value,
        "low": {"status": event_low["status"], "terminal_equity": scalar_low["terminal_equity"],
               "engine_fill_count": scalar_low["engine_fill_count"], "entries": scalar_low["entries"]},
        "high": {"status": event_high["status"], "terminal_equity": scalar_high["terminal_equity"],
                "engine_fill_count": scalar_high["engine_fill_count"], "entries": scalar_high["entries"]},
        "outcome": "BEHAVIOR_DIFFERS" if differs else "NO_DIFFERENCE_OBSERVED_ON_THIS_WINDOW",
    }
