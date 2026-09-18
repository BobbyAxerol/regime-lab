"""A08 acceptance — the public Mode 4 causal pipeline is the baseline, not a helper.

The old arm A built trial records by hand and wrote a mean episode utility into
the `mean_is_sharpe` field. This test pins the replacement: the installed
`walk_forward` pipeline, the engine's own Mode 4 IS-only selection, a declared
`oos_used_for_selection=False`, and real trial records with selection metadata.
"""

from __future__ import annotations

from crypto_regime_lab.selector.installed_wfo import synthetic_frame
from crypto_regime_lab.selector.mode4_baseline import run_mode4_public_baseline

RANGES = {"coeff": (1, 8), "AP": (5, 60), "alpha.condition_threshold": (30, 80)}


def test_a08_the_public_mode4_causal_pipeline_runs_and_declares_is_only_selection():
    frame = synthetic_frame(n=3600, seed=5, freq="4h")
    out = run_mode4_public_baseline(frame, param_ranges=RANGES, optuna_trials=2, seed=11,
                                    split_mode=2021, split_frequency="monthly")
    assert out["ok"], out.get("error")
    trace = out["contract_trace"]
    assert trace["optimization_mode"] == "mode_4_is_only_robust"
    assert trace["optimization_schedule"] == "per_fold_causal"
    assert trace["candidate_selection_metric"] == "is_only_robust"
    assert trace["scoring_backend"] == "endpoint"
    assert trace["oos_used_for_selection"] is False
    assert trace["validation_claim"] == "strict_fold_local_retraining"
    assert out["trial_count"] > 0, "a baseline with no trial records proves nothing"
    assert out["fold_count"] >= 1
    assert out["params_by_fold"], "each fold must carry its own selected parameters"
    assert out["selected_params"]
    assert out["selected_digest"]
    assert out["requested"]["fee_binding"] == {"fee": 0.0008, "fee_rate": 0.0004}
    assert out["sizing_contract"]["target_mode"] == "signal_notional"
    objectives = [float(record["objective"]) for record in out["trial_records"]]
    assert any(abs(value) > 1e-12 for value in objectives), (
        "every objective is zero: the scorer is vacuous and the baseline would select trial 0")
    for record in out["trial_records"]:
        metadata = record["selection_metadata"]
        assert (metadata.get("oos_seen_by_optuna") is False
                or metadata.get("oos_used_for_selection") is False), metadata
    selection_records = out["fold_selection_table"] or []
    assert selection_records, "the fold selection table is empty"
    assert all(record.get("outer_oos_used_for_selection") is False for record in selection_records)
    assert all(str(record.get("causality_claim")) == "strict_fold_local_retraining"
               for record in selection_records)
    assert all(record.get("selected_params") for record in selection_records)
