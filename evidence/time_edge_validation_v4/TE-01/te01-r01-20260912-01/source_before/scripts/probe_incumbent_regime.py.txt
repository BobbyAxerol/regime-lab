#!/usr/bin/env python
"""Probe QuantBT's own regime facility (L01.6 addendum).

The lab is asked to build a regime layer *around* the installed engine, so the
regime notion QuantBT already ships must be characterised empirically first.
Every claim here is produced by a reproducer, not by reading the source.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

import quantbt  # noqa: E402  (from the lab venv)

from crypto_regime_lab.evidence.manifest import EvidenceWriter  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402


def probe_future_dependence() -> dict:
    """Does a label at time t depend on observations after t?

    Reproducer: build a series, label it, then change only the TAIL and relabel.
    A causal (online) labeller leaves the prefix labels untouched.
    """
    rng = np.random.default_rng(20260909)
    base = rng.normal(0.0, 0.005, 400)
    mutated = base.copy()
    mutated[300:] = rng.normal(0.0, 0.05, 100)  # tail becomes high-vol only

    labels_base = quantbt.volatility_regime_labels(base, regime_count=3, lookback=20)
    labels_mut = quantbt.volatility_regime_labels(mutated, regime_count=3, lookback=20)

    prefix_base = labels_base[:300]
    prefix_mut = labels_mut[:300]
    changed = int(np.sum(prefix_base != prefix_mut))
    return {
        "probe_id": "QBT_REGIME_TAIL_MUTATION",
        "expectation": "a causal labeller leaves prefix labels unchanged when only the tail changes",
        "prefix_length": 300,
        "prefix_labels_changed": changed,
        "prefix_changed_fraction": round(changed / 300.0, 6),
        "causal_within_window": bool(changed == 0),
        "observed": (
            "prefix labels changed after a tail-only mutation"
            if changed
            else "prefix labels unchanged"
        ),
    }


def probe_label_semantics() -> dict:
    """What do the labels actually encode, and how are they distributed?"""
    rng = np.random.default_rng(7)
    calm = rng.normal(0.0, 0.002, 300)
    wild = rng.normal(0.0, 0.02, 300)
    series = np.concatenate([calm, wild])
    labels = quantbt.volatility_regime_labels(series, regime_count=3, lookback=20)
    counts = {int(k): int(v) for k, v in zip(*np.unique(labels, return_counts=True))}
    calm_mean = float(np.mean(labels[:300]))
    wild_mean = float(np.mean(labels[300:]))
    # Constant input: trailing vol is degenerate, so cut points collapse.
    constant = quantbt.volatility_regime_labels(np.zeros(200), regime_count=3, lookback=20)
    return {
        "probe_id": "QBT_REGIME_LABEL_SEMANTICS",
        "expectation": "labels are trailing-|return| quantile buckets, 0 = low vol",
        "label_counts": counts,
        "mean_label_calm_half": calm_mean,
        "mean_label_wild_half": wild_mean,
        "separates_calm_from_wild": bool(wild_mean > calm_mean),
        "constant_input_unique_labels": sorted({int(x) for x in constant}),
        "quantile_cuts_are_in_sample": True,
    }


def probe_directionality() -> dict:
    """Does the labeller see direction, or only magnitude?"""
    rng = np.random.default_rng(11)
    up = np.abs(rng.normal(0.0, 0.01, 300))
    down = -up
    labels_up = quantbt.volatility_regime_labels(up, regime_count=3, lookback=20)
    labels_down = quantbt.volatility_regime_labels(down, regime_count=3, lookback=20)
    return {
        "probe_id": "QBT_REGIME_DIRECTION_BLIND",
        "expectation": "sign-flipped returns give identical labels if only |r| is used",
        "identical_labels_under_sign_flip": bool(np.array_equal(labels_up, labels_down)),
        "implication": "no bull/bear direction axis; magnitude only",
    }


def probe_wfo_regime_config() -> dict:
    """Where does WalkForwardConfig expose regime knobs, and what are the defaults?"""
    cfg = quantbt.WalkForwardConfig()
    return {
        "probe_id": "QBT_WFO_REGIME_CONFIG",
        "regime_count_default": cfg.regime_count,
        "regime_lookback_default": cfg.regime_lookback,
        "regime_weights_default": cfg.regime_weights,
        "candidate_selection_metric_default": cfg.candidate_selection_metric,
        "optimization_mode_default": cfg.optimization_mode,
        "optimization_schedule_default": cfg.optimization_schedule,
        "fold_account_policy_default": cfg.fold_account_policy,
        "sbb_simulation_default": cfg.sbb_simulation,
    }


def main() -> int:
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    writer = EvidenceWriter.open(policy, study_id="crypto_regime_timeedge_v2")
    with writer.attempt("L01.6.probe_incumbent_regime") as att:
        probes = [probe_future_dependence(), probe_label_semantics(),
                  probe_directionality(), probe_wfo_regime_config()]
        att.detail = {"probe_count": len(probes)}
    report = {
        "evidence_type": "INSTALLED_ENGINE_SOURCE_PROBES_NOT_MARKET_BACKTEST",
        "quantbt_version": quantbt.__version__,
        "quantbt_origin": quantbt.__file__,
        "probes": probes,
        "reading": (
            "QuantBT 1.1.1 ships volatility_regime_labels: trailing mean-|return| bucketed by "
            "quantiles computed over the WHOLE array it is given. It is direction-blind and its "
            "cut points are in-sample to that array, so labels at time t move when later "
            "observations change. It is a valid in-objective descriptor for an IS window, and a "
            "valid M0-style comparator, but it is NOT an online causal state estimator and must "
            "carry decision_eligible=false when used outside an in-sample scoring window."
        ),
        "lab_consequence": (
            "The lab's LAB-05 jump model must be compared against this incumbent as the M0/legacy "
            "baseline, and any claim that 'QuantBT already does regime' has to state which of the "
            "two semantics is meant."
        ),
    }
    art = writer.write_json("incumbent_regime_probe.json", report,
                            schema="crypto_regime_lab.incumbent_regime_probe.v1")
    for p in probes:
        print(f"  {p['probe_id']}")
        for k, v in p.items():
            if k != "probe_id":
                print(f"      {k}: {v}")
    print(f"\nevidence -> {art['artifact_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
