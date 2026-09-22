"""FP03-G-SCHEMA and the engine-free half of FP03-G-PREFIX/COVERAGE: schema
mapping, unknown-value rejection, sampler introspection, and prefix-slicing
correctness on synthetic trial records (no real engine call needed for
these -- guide 11.6's zero-engine-call spirit applied wherever the claim
does not actually require one).
"""
from __future__ import annotations

import pytest

from crypto_regime_lab.fp import checkpoint_search as cs
from crypto_regime_lab.fp import param_qualification as pq
from crypto_regime_lab.fp import search_introspection as si

BASE_PARAMS = {"coeff": 4, "AP": 20, "alpha.condition_threshold": 55,
              "novolumedata": False, "src_col": "close"}


def test_fp03_t_schema_mapping_matches_declared_bounds():
    rows = pq.schema_mapping_rows("A-SC")
    by_name = {r["name"]: r for r in rows}
    assert set(by_name) == {"coeff", "AP", "alpha.condition_threshold",
                            "novolumedata", "src_col"}
    assert all(r["engine_mapping_consistent"] for r in rows), rows
    assert by_name["coeff"]["kind"] == "int"
    assert by_name["coeff"]["declared_low"] == 1 and by_name["coeff"]["declared_high"] == 8
    assert by_name["novolumedata"]["kind"] == "fixed"


def test_fp03_t_unknown_values_are_typed_rejections_not_silent_acceptance():
    rows = pq.unknown_value_rejections("A-SC", base_params=BASE_PARAMS)
    assert len(rows) == 3  # the three non-fixed dimensions
    assert all(r["correctly_rejected"] for r in rows), rows
    assert all(r["reason"] for r in rows)


def test_fp03_t_fixed_dimensions_never_enter_the_search_ranges():
    rows = pq.fixed_dimensions_never_vary("A-SC")
    assert len(rows) == 2
    assert all(r["engine_value_is_scalar"] and r["matches_declared"] for r in rows), rows


def test_fp03_t_sampler_identity_is_read_not_assumed():
    identity = si.installed_sampler_identity()
    assert identity["sampler_class"] == "optuna.samplers.TPESampler"
    assert isinstance(identity["n_startup_trials_default"], int)
    assert identity["n_startup_trials_default"] > 0
    import optuna
    assert identity["optuna_version_installed"] == optuna.__version__


def test_fp03_t_ask_tell_sequence_empirically_concentrates():
    """Not just 'the constructor says n_startup_trials=10' -- the sampler's
    actual proposals must measurably concentrate toward the optimum after
    the startup window, on a real (if toy) Optuna run."""
    result = si.demonstrate_ask_tell_sequence(n_trials=15, seed=42)
    assert result["empirically_concentrating"] is True
    assert len(result["startup_trial_numbers"]) == result["n_startup_trials_used_for_split"]
    assert len(result["ask_tell_sequence"]) == 15


def test_fp03_t_classify_real_trials_counts_duplicates_and_uniques():
    records = [{"trial_id": i, "params": {"AP": 5 + (i % 3)}, "pruned": False}
              for i in range(12)]
    out = si.classify_real_trials(records)
    assert out["n_trials_attempted"] == 12
    assert out["startup_trial_count"] == out["sampler_identity"]["n_startup_trials_default"]
    assert out["unique_effective_candidates"] == 3
    assert out["duplicate_reused_evaluations"] == 9


def _fake_wf_result(n: int) -> dict:
    """A synthetic wf_result with n trial_records, deterministic params/objective
    so prefix-validity can be checked exactly."""
    return {"trial_records": [
        {"trial_id": i, "objective": float(i), "pruned": False,
         "params": {"coeff": 1 + (i % 8), "AP": 5 + i, "alpha.condition_threshold": 30,
                    "novolumedata": False, "src_col": "close"}}
        for i in range(n)
    ]}


def test_fp03_g_prefix_lower_checkpoint_is_a_true_prefix_of_higher():
    """FP03-G-PREFIX's actual claim: checkpoint 32 must use EXACTLY the
    first 32 trials of the SAME ask/tell sequence checkpoint 64 also reads
    from -- never a separately-seeded re-run. Proved by constructing ONE
    wf_result and checking both checkpoints' 'selected' and coverage counts
    are consistent with pure slicing, not by trusting the function's own
    internal bookkeeping."""
    wf_result = _fake_wf_result(64)
    checkpoints = cs.checkpoints_from_prefix("A-SC", wf_result, levels=(32, 64))
    cp32 = next(c for c in checkpoints if c["level"] == 32)
    cp64 = next(c for c in checkpoints if c["level"] == 64)
    assert cp32["status"] == cp64["status"] == "REACHED"
    # Trial 63 has the highest objective (63.0); it must appear in the
    # 64-checkpoint's selection but be IMPOSSIBLE for the 32-checkpoint
    # to have seen (it does not exist in trials 0..31).
    assert cp32["selected"]["trial_id"] < 32
    assert cp64["selected"]["trial_id"] == 63
    assert cp32["coverage"]["n_attempted"] == 32
    assert cp64["coverage"]["n_attempted"] == 64
    # The 32-checkpoint's own attempted count must be independent of what
    # exists beyond trial 31 -- re-derive it directly from the SAME raw
    # records, not from the checkpoint function's summary alone.
    raw_prefix_32 = sorted(wf_result["trial_records"], key=lambda r: r["trial_id"])[:32]
    assert cp32["coverage"]["n_attempted"] == len(raw_prefix_32)
    assert cp32["selected"]["trial_id"] == max(raw_prefix_32, key=lambda r: r["objective"])["trial_id"]


def test_fp03_g_prefix_not_reached_when_fewer_trials_than_level():
    wf_result = _fake_wf_result(20)
    checkpoints = cs.checkpoints_from_prefix("A-SC", wf_result, levels=(32, 64))
    assert all(c["status"] == "NOT_REACHED" for c in checkpoints)
    assert all(c["n_trials_available"] == 20 for c in checkpoints)


def test_fp03_g_coverage_is_measured_not_a_fixed_adjective():
    wf_result = _fake_wf_result(32)
    records = cs._trial_records(wf_result)
    coverage = cs.region_coverage("A-SC", records)
    assert coverage["declared_grid_size"] == 8 * 56 * 11
    assert 0.0 < coverage["raw_coverage_fraction"] < 1.0
    assert coverage["n_unique"] <= coverage["n_attempted"]
    assert coverage["behavioral_objective_spread"] == pytest.approx(31.0)


def test_fp03_checkpoint_search_raises_on_missing_trial_records():
    with pytest.raises(ValueError, match="trial_records"):
        cs._trial_records({"ok": True})


def test_fp03_run_origin_search_measures_real_wall_and_instrumentation():
    """Regression test: an earlier edit silently dropped the Stage/timer
    wrapping from run_origin_search, so a FRESH (non-cached) call returned
    wall_seconds_measured=None and instrumentation=None -- invisible in
    FP-03's own committed evidence only because all three of its origins
    happened to hit a stale .cache/ file written by an earlier, still-working
    version of this function. Found while auditing FP-03 before reusing
    run_origin_search for FP-04's 12 brand-new (never-cached) origins, none
    of which could have hit that same stale cache. Small real engine call
    (2 trials, 3-day train memory) so this runs in a few seconds, not the
    ~45 minutes a real 256-trial/180-day origin costs."""
    result = cs.run_origin_search(origin_cutoff="2023-06-05", trials=2, seed=20260922,
                                  train_memory_days=3, forward_days=2)
    assert result["wf_result"]["ok"] is True
    assert isinstance(result["wall_seconds_measured"], float)
    assert result["wall_seconds_measured"] > 0.0
    instrumentation = result["instrumentation"]
    assert instrumentation is not None
    for key in ("base_mib", "peak_mib", "after_gc_mib", "delta_mib", "residual_mib", "wall_s"):
        assert key in instrumentation
    assert instrumentation["peak_mib"] > 0.0
    # the lab-level wrapper's wall-clock (data load + engine call) must be at
    # least the engine-only Stage's own wall_s, never less
    assert result["wall_seconds_measured"] >= instrumentation["wall_s"]
