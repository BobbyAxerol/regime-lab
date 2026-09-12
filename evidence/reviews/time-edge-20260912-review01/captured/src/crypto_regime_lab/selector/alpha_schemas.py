"""Declared search spaces for the four alphas (guide 7.1).

Bounds live HERE, in the schema, and never come from whatever a sampler happened
to visit. Fixed keys are declared ``fixed`` so they stay out of every distance
denominator; conditional keys declare ``active_when`` so an inactive branch
creates no false distance; ordered pairs are declared as dependencies so probes
parameterise the manifold instead of repairing points after sampling.

How the bounds were placed
--------------------------
A bound that excludes the region an alpha was authored to operate in is a design
error, not a neutral choice: the first draft here declared ``min_length`` at
4..40 for A-HMA, whose own preset dictionaries all sit between 120 and 320, and
``htf_ema_len`` at 10..60 for A-VWAP, whose presets span 130..570. Measured on
BTCUSDT over 2020-07..2021-01, that first draft left A-VWAP's entry gate empty:
the reversion trigger fired on 697 long and 1147 short bars, and the HTF trend
filter agreed on 0 and 1 of them respectively.

So each declared interval is set to ENCLOSE the operating range of that alpha's
own preset dictionaries, then padded outward. Only the EXTENT of the space is
informed that way. The preset values themselves stay quarantined exactly as
LAB-02 recorded them (``provenance = user_full_sample_tpe``): they are never
candidates, never anchors, never warm starts, and never a reference result. The
extent is registered here, before any arm comparison, and is identical for every
arm.
"""

from __future__ import annotations

from .schema_distance import ParamSchema, ParamSpec, SchemaError

A_SC = ParamSchema.from_specs(
    [
        ParamSpec("coeff", "int", 1, 8, 1),
        ParamSpec("AP", "int", 5, 60, 1),
        ParamSpec("alpha.condition_threshold", "int", 30, 80, 5),
        ParamSpec("novolumedata", "fixed", fixed_value=False),
        ParamSpec("src_col", "fixed", fixed_value="close"),
    ],
    name="A-SC",
)

A_HMA = ParamSchema.from_specs(
    [
        ParamSpec("min_length", "int", 40, 360, 10),
        ParamSpec("max_length", "int", 60, 420, 10),
        ParamSpec("minor_min", "int", 10, 120, 2),
        ParamSpec("minor_max", "int", 30, 220, 5),
        ParamSpec("flat", "float", 4.0, 50.0, 1.0),
        ParamSpec("atr_fast", "int", 4, 60, 2),
        ParamSpec("atr_slow", "int", 10, 140, 5),
        ParamSpec("mult", "float", 0.5, 6.0, 0.25),
        ParamSpec("max_sl", "float", 1.0, 9.0, 0.25),
        ParamSpec("take_profit", "float", 1.0, 8.0, 0.5),
        ParamSpec("min_profit", "float", 0.1, 4.0, 0.1),
        ParamSpec("sl_input", "categorical",
                  choices=("One Distance Zone", "Half Distance Zone", "Last High/Low", "ATR Only")),
        ParamSpec("tick_size", "fixed", fixed_value=0.01),
    ],
    dependencies=(("min_length", "max_length"), ("minor_min", "minor_max"),
                  ("atr_fast", "atr_slow")),
    name="A-HMA",
)

A_VWAP = ParamSchema.from_specs(
    [
        ParamSpec("rsi_len", "int", 5, 80, 1),
        ParamSpec("rsi_os", "int", 10, 50, 1),
        ParamSpec("rsi_ob", "int", 55, 90, 1),
        ParamSpec("dev_mult", "float", 0.5, 5.0, 0.1),
        ParamSpec("atr_len", "int", 5, 90, 1),
        ParamSpec("stop_atr", "float", 1.0, 10.0, 0.1),
        ParamSpec("target_r", "float", 1.0, 10.0, 0.1),
        ParamSpec("htf_ema_len", "int", 20, 700, 10),
        ParamSpec("exit_at_vwap", "bool", choices=(False, True)),
        ParamSpec("time_stop_on", "bool", choices=(False, True)),
        # only meaningful when the time stop is on -> declared conditional
        ParamSpec("time_stop_bars", "int", 5, 120, 5, active_when=("time_stop_on", True)),
        ParamSpec("htf_tf", "fixed", fixed_value="1h"),
    ],
    dependencies=(("rsi_os", "rsi_ob"),),
    name="A-VWAP",
)

A_HASH = ParamSchema.from_specs(
    [
        ParamSpec("mom_len", "int", 5, 70, 1),
        ParamSpec("ema_len", "int", 10, 80, 2),
        ParamSpec("cooldown_bars", "int", 0, 40, 1),
        ParamSpec("stop_loss_perc", "float", 0.5, 8.0, 0.25),
        ParamSpec("rr_ratio", "float", 1.0, 5.0, 0.1),
        ParamSpec("tp1_ratio", "float", 0.5, 4.0, 0.1),
        ParamSpec("tp2_ratio", "float", 1.0, 5.0, 0.1),
        ParamSpec("mom_threshold_mult", "float", 0.5, 7.0, 0.25),
        ParamSpec("tp1_qty_perc", "int", 20, 70, 5),
        ParamSpec("tp2_qty_perc", "int", 20, 70, 5),
    ],
    # the canonical ladder requires tp1 < tp2 < final and REFUSES to sort a bad
    # preset (finding AH-07), so the full chain is declared, not just the first link
    dependencies=(("tp1_ratio", "tp2_ratio"), ("tp2_ratio", "rr_ratio")),
    name="A-HASH",
)

SCHEMAS = {"A-SC": A_SC, "A-HMA": A_HMA, "A-VWAP": A_VWAP, "A-HASH": A_HASH}

#: Registered starting point per alpha: the incumbent at the first cutoff. Each is a
#: plain mid-space choice on the declared interval, NOT a preset and NOT a tuned value.
SEED_POINTS = {
    "A-SC": {"coeff": 4, "AP": 20, "alpha.condition_threshold": 55,
             "novolumedata": False, "src_col": "close"},
    "A-HMA": {"min_length": 200, "max_length": 240, "minor_min": 60, "minor_max": 120,
              "flat": 25.0, "atr_fast": 30, "atr_slow": 75, "mult": 3.0, "max_sl": 5.0,
              "take_profit": 4.5, "min_profit": 2.0, "sl_input": "Half Distance Zone",
              "tick_size": 0.01},
    "A-VWAP": {"rsi_len": 40, "rsi_os": 30, "rsi_ob": 72, "dev_mult": 2.5, "atr_len": 45,
               "stop_atr": 5.5, "target_r": 5.5, "htf_ema_len": 360, "exit_at_vwap": False,
               "time_stop_on": True, "time_stop_bars": 60, "htf_tf": "1h"},
    "A-HASH": {"mom_len": 35, "ema_len": 44, "cooldown_bars": 20, "stop_loss_perc": 4.0,
               "tp1_ratio": 2.0, "tp2_ratio": 3.0, "rr_ratio": 4.0,
               "mom_threshold_mult": 3.5, "tp1_qty_perc": 45, "tp2_qty_perc": 45},
}


def _sample_order(schema: ParamSchema) -> list[str]:
    """Controllers before the branches they gate, lower bounds before upper bounds.

    Sorting by name alone put ``time_stop_bars`` before ``time_stop_on``, so the
    branch was resolved against a controller that had not been drawn yet and the
    point came out missing an active parameter.
    """
    lower_of = {upper: lower for lower, upper in schema.dependencies}
    remaining = sorted(schema.specs)
    order: list[str] = []
    placed: set[str] = set()
    while remaining:
        progressed = False
        for name in list(remaining):
            spec = schema.specs[name]
            needs = set()
            if spec.active_when is not None:
                needs.add(spec.active_when[0])
            if name in lower_of:
                needs.add(lower_of[name])
            if needs <= placed:
                order.append(name)
                placed.add(name)
                remaining.remove(name)
                progressed = True
        if not progressed:                     # a cycle in the declared schema
            raise SchemaError(f"cyclic parameter dependencies in {schema.name}: {remaining}")
    return order


def inert_value(spec: ParamSpec):
    """The declared, non-sampled value an INACTIVE conditional key carries.

    The adapters require every declared key to be present -- A-VWAP raises rather
    than fall back to a module default (SD-VWAP-06) -- so an inactive branch still
    needs a value. It is a fixed declared placeholder, never a sampled one, so two
    points that differ only in an inactive key remain the same point.
    """
    if spec.kind in ("bool", "categorical"):
        return (list(spec.choices) or [False])[0]
    if spec.kind == "fixed":
        return spec.fixed_value
    return int(spec.low) if spec.kind == "int" else float(spec.low)


def _grid_high(spec: ParamSpec, low: int) -> int:
    """Largest declared grid value at or below ``high`` reachable from ``low``."""
    step = int(spec.step or 1)
    span = int(spec.high) - low
    return low + (span // step) * step


def suggest_point(trial, schema: ParamSchema) -> dict:
    """Map one Optuna trial onto a schema point, respecting the declared manifold.

    Dependent pairs are parameterised directly: the upper member is drawn from a
    range that starts above the lower member, so no point has to be repaired or
    sorted after sampling (guide 7.1). An inactive conditional key is filled with
    its declared inert value rather than being sampled or omitted.
    """
    point: dict = {}
    lower_of = {upper: lower for lower, upper in schema.dependencies}
    for name in _sample_order(schema):
        spec = schema.specs[name]
        if spec.kind == "fixed":
            point[name] = spec.fixed_value
            continue
        if spec.active_when is not None:
            other, required = spec.active_when
            if point.get(other) != required:
                point[name] = inert_value(spec)
                continue
        if spec.kind == "bool":
            point[name] = trial.suggest_categorical(name, [False, True])
        elif spec.kind == "categorical":
            point[name] = trial.suggest_categorical(name, list(spec.choices))
        elif spec.kind == "int":
            low = int(spec.low)
            if name in lower_of and lower_of[name] in point:
                low = max(low, int(point[lower_of[name]]) + int(spec.step or 1))
            low = min(low, int(spec.high))
            high = _grid_high(spec, low)
            point[name] = (low if high <= low
                           else trial.suggest_int(name, low, high, step=int(spec.step or 1)))
        else:
            low = float(spec.low)
            if name in lower_of and lower_of[name] in point:
                low = max(low, float(point[lower_of[name]]) + float(spec.step or 0.0))
            low = min(low, float(spec.high))
            point[name] = trial.suggest_float(name, low, float(spec.high),
                                              step=float(spec.step) if spec.step else None)
    return point
