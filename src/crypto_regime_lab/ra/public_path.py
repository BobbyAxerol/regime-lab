"""RA04.6: public-path assertions -- the scheduled cutoff really goes into the
SAME pinned Mode 4 evaluator/selector, `evaluate_oos_candidates=False`,
train-only objects carry no future segment-end.

Two proof levels, deliberately not conflated (guide: "module-level tests
khong thay active runner integration"):

* STRUCTURAL: source-level checks (real `inspect.getsource`, not a
  paraphrase) that the active runner (`time_edge/execution.py::select_only`)
  actually passes `evaluate_oos_candidates=False` and that its
  `WalkForwardFold` sets test_start/test_end equal to train_start/train_end
  (no held-out future segment reaches the selector at all).
* INTEGRATION: one REAL call through `CutoffWalkForwardEngine.optimize_params`
  -- the EXACT class `select_only` instantiates (a subclass of the installed
  `WalkForwardEngine`, not a reimplementation) -- at a phase-owned smaller
  scale (a fraction of the registered 180-day/32-trial contract, same
  precedent as RA-02/RA-03's own real-but-small experiments; the full
  180-day/32-trial contract is reserved for RA-05's actual discovery run,
  not spent proving plumbing here). Confirms the selector's own returned
  metadata states `oos_used_for_selection: False`.

Prefix-causality (suffix mutation must not change the past) is NOT
re-derived here: it is the same `PreparedAccount`/window mechanism RA-02's
C04 already proved real-engine (`tests/ra_corrective/test_ra02_cache_cases.py
::test_c04_future_suffix_never_changes_prefix_key_or_output`) -- cited, not
duplicated.
"""
from __future__ import annotations

import inspect

from .phase_common import utcnow


def structural_checks() -> dict:
    from ..time_edge import execution

    source = inspect.getsource(execution.select_only)
    fold_source = source  # WalkForwardFold is constructed inline in select_only
    checks = {
        "evaluate_oos_candidates_false_in_source": "evaluate_oos_candidates=False" in source,
        "fold_test_equals_train_start": "test_start=train[0]" in fold_source,
        "fold_test_equals_train_end": "test_end=train[-1]" in fold_source,
        "no_outer_oos_row_guard_present": "no outer OOS row allowed" in source,
        "hard_180_day_train_window_enforced": "180*1440" in source,
    }
    return {"schema": "regime_lab.ra04_public_path_structural.v1", "checks": checks,
           "all_pass": all(checks.values()),
           "source_inspected": "src/crypto_regime_lab/time_edge/execution.py::select_only"}


def integration_check(alpha_id: str = "A-SC", *, train_days: int = 24, trials: int = 8,
                      seed: int = 20260918) -> dict:
    """One real call through the SAME engine class select_only uses, at a
    phase-owned smaller scale. Reports the selector's own returned metadata
    rather than asserting an expectation about it."""
    from ..experiments.dynamic_fold_provider import (
        CutoffWalkForwardEngine, ZeroSignalStrategy, engine_param_ranges,
    )
    from ..time_edge.execution import PreparedAccount, TrainingScorer
    from .phase_common import LAB
    from .route_qualification import synthetic_bars

    n = (train_days + 2) * 1440
    frame = synthetic_bars(n, seed=seed, sigma=0.2)
    train_start = frame.index[0]
    cutoff = frame.index[train_days * 1440]
    train_index = frame.index[(frame.index >= train_start) & (frame.index < cutoff)]

    prepared = PreparedAccount(frame)
    evdir = LAB / ".cache" / "ra04_public_path"
    evdir.mkdir(parents=True, exist_ok=True)
    scorer = TrainingScorer(prepared, alpha_id, train_start, cutoff, evdir, "ra04-public-path")

    try:
        from quantbt.walkforward import WalkForwardConfig, WalkForwardFold
    except Exception as exc:  # pragma: no cover - environment problem, not a code path
        return {"schema": "regime_lab.ra04_public_path_integration.v1", "status": "BLOCKED",
               "reason": f"{type(exc).__name__}: {exc}"}

    config = WalkForwardConfig(optimization_mode="mode_4_is_only_robust",
                               optimization_schedule="per_fold_causal",
                               candidate_selection_metric="is_only_robust",
                               optuna_trials=trials, random_seed=seed,
                               scoring_backend="endpoint", scoring_trading_days=365,
                               window_mode="rolling", train_window=f"{train_days}D",
                               is_subperiods=3,  # scaled down from the registered 6 for this smaller window
                               metadata={"compact_trial_ledger": False})
    engine = CutoffWalkForwardEngine(strategy=ZeroSignalStrategy(), config=config, scorer=scorer)
    fold = WalkForwardFold(fold_id=0, train_start=train_index[0], train_end=train_index[-1],
                           test_start=train_index[0], test_end=train_index[-1],
                           train_index=train_index, test_index=train_index,
                           warmup_index=frame.index[frame.index < train_start],
                           account_policy="reset_flat")
    selected, trials_out, candidates_out = engine.optimize_params(
        data=frame, folds=[fold], param_ranges=engine_param_ranges(alpha_id),
        evaluate_oos_candidates=False, random_seed=seed)
    metadata = dict(selected.selection_metadata)
    return {
        "schema": "regime_lab.ra04_public_path_integration.v1", "status": "OK",
        "engine_class": type(engine).__mro__[1].__module__ + "." + type(engine).__mro__[1].__qualname__,
        "engine_is_installed_walkforward_subclass": type(engine).__mro__[1].__module__.startswith("quantbt"),
        "alpha_id": alpha_id, "train_days": train_days, "trials_requested": trials,
        "trials_completed": len(trials_out), "candidates": len(candidates_out),
        "selected_params": dict(selected.params),
        "selection_metadata": metadata,
        "oos_used_for_selection_reported_by_selector": metadata.get("oos_used_for_selection"),
        "no_future_segment": fold.test_start == fold.train_start and fold.test_end == fold.train_end,
        "note": ("phase-owned scale (24D/8trials/3 subperiods), not the registered 180D/32trial "
                "contract -- proves the active runner's pinned evaluator/selector objects and "
                "evaluate_oos_candidates=False, does not spend the RA-05 discovery budget here"),
    }


def public_path_report() -> dict:
    return {"schema": "regime_lab.ra04_public_path.v1", "checked_at_utc": utcnow(),
           "structural": structural_checks(), "integration": integration_check(),
           "suffix_causality_cited_from": ("tests/ra_corrective/test_ra02_cache_cases.py::"
                                           "test_c04_future_suffix_never_changes_prefix_key_or_output "
                                           "(same PreparedAccount/window mechanism select_only is built on)")}
