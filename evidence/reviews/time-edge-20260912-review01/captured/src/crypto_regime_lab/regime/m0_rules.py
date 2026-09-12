"""L05.2 — M0, the rule-based comparator (guide 8.1).

M0 exists so that "the jump model found structure" can be compared against
something a person can read off a chart. Its thresholds are quantiles of the
TRAINING window and nothing else; they are frozen with the model and never
recomputed on the data being labelled, because a quantile taken over the window
you are labelling is a look-ahead dressed as a rule.

M0 is a control, not a fallback. It is not automatically substituted when M1
degrades -- that substitution would be a silent model change.
"""

from __future__ import annotations

import numpy as np

STATE_NAMES = ("low_vol", "mid_vol", "high_vol")


def fit_thresholds(train_volatility: np.ndarray, *, quantiles=(1 / 3, 2 / 3)) -> dict:
    values = np.asarray(train_volatility, dtype=np.float64)
    values = values[np.isfinite(values)]
    if values.size < 10:
        raise ValueError("too few finite training observations to fit M0 thresholds")
    cuts = [float(np.quantile(values, q)) for q in quantiles]
    return {
        "schema": "crypto_regime_lab.m0_thresholds.v1",
        "quantiles": list(quantiles), "cuts": cuts,
        "train_n": int(values.size),
        "fitted_on": "training window only",
        "rule": ("thresholds are frozen with the model. Recomputing a quantile over the window "
                 "being labelled would use that window's own future (guide 8.1 'threshold "
                 "train-only')"),
    }


def label(volatility: np.ndarray, thresholds: dict) -> np.ndarray:
    """Causal by construction: each label depends only on that observation and the
    frozen cuts."""
    values = np.asarray(volatility, dtype=np.float64)
    low, high = thresholds["cuts"]
    out = np.full(values.shape, 1, dtype=np.int64)
    out[values <= low] = 0
    out[values > high] = 2
    return out


def describe() -> dict:
    return {
        "model_id": "M0",
        "role": "explainable control (guide 8.1)",
        "states": list(STATE_NAMES),
        "is_fallback_for_m1": False,
        "fallback_note": ("M0 is a comparator. It is never silently substituted when M1 reports "
                          "UNKNOWN_STATE -- that would change models without a model transition "
                          "event"),
        "naming_note": ("these names describe the FEATURE the rule reads (realised volatility), "
                        "not an outcome. They are not bull/neutral/bear (guide 8.1)"),
    }
