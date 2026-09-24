"""FP03.3/guide 6.1 -- what must be logged about the search, verified against
the ACTUALLY INSTALLED Optuna, not assumed from its documentation (the
guide's own source S1/S2 cites 4.2.1; this lab's installed version may
differ -- checked here, not assumed).

The stock Mode 4 search (``quantbt/walkforward.py``, read directly, not
guessed) constructs its sampler as plain
``optuna.samplers.TPESampler(seed=study_seed)`` with every other
constructor argument left at its DEFAULT -- so ``n_startup_trials`` for the
real search is whatever this installed TPESampler's own default is. This
module reads that default live and separately DEMONSTRATES it empirically
(a toy 2D objective, ask/tell sequence recorded) rather than trusting the
constructor signature alone: the first ``n_startup_trials`` proposals must
look like scattered random sampling, and later ones must visibly
concentrate toward the optimum.
"""
from __future__ import annotations

SEARCH_INTROSPECTION_SCHEMA = "regime_lab.fp03_search_introspection.v1"


def installed_sampler_identity() -> dict:
    """Read, not assumed: version, sampler class, and its actual default
    n_startup_trials on THIS install."""
    import inspect

    import optuna

    sig = inspect.signature(optuna.samplers.TPESampler.__init__)
    default_startup = sig.parameters["n_startup_trials"].default
    return {
        "optuna_version_installed": optuna.__version__,
        "guide_source_cites": "4.2.1 (S1/S2) -- verify-not-assume applies: installed differs" if optuna.__version__ != "4.2.1" else "4.2.1 (matches guide source)",
        "sampler_class": "optuna.samplers.TPESampler",
        "stock_construction": "optuna.samplers.TPESampler(seed=study_seed) -- quantbt/walkforward.py, every other arg left default",
        "n_startup_trials_default": default_startup,
    }


def demonstrate_ask_tell_sequence(*, n_trials: int = 15, seed: int = 42) -> dict:
    """A toy 2D objective (zero engine calls, guide 11.6's 'bootstrap... zero
    new engine calls' spirit applied to search-mechanism verification): logs
    every trial's proposed params in ask/tell order, and empirically checks
    the startup->adaptive transition the installed default predicts, rather
    than only citing the constructor default."""
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    identity = installed_sampler_identity()
    startup_n = int(identity["n_startup_trials_default"])

    events: list[dict] = []

    def objective(trial):
        x = trial.suggest_float("x", 0.0, 1.0)
        y = trial.suggest_int("y", 1, 8)
        events.append({"trial_number": trial.number, "params": {"x": x, "y": y}})
        return -((x - 0.5) ** 2) - (y - 4) ** 2

    sampler = optuna.samplers.TPESampler(seed=seed)
    study = optuna.create_study(direction="maximize", sampler=sampler)
    study.optimize(objective, n_trials=n_trials)

    startup = [e for e in events if e["trial_number"] < startup_n]
    adaptive = [e for e in events if e["trial_number"] >= startup_n]
    # Empirical check: adaptive trials' distance to the known optimum
    # (x=0.5, y=4) should, on average, be smaller than startup trials' --
    # the sampler is actually concentrating, not just past a trial-count
    # threshold with no measurable effect.
    def dist(e):
        return abs(e["params"]["x"] - 0.5) + abs(e["params"]["y"] - 4) / 8.0

    startup_mean_dist = sum(dist(e) for e in startup) / len(startup) if startup else None
    adaptive_mean_dist = sum(dist(e) for e in adaptive) / len(adaptive) if adaptive else None
    return {
        "schema": SEARCH_INTROSPECTION_SCHEMA,
        "sampler_identity": identity,
        "n_trials": n_trials, "seed": seed,
        "ask_tell_sequence": events,
        "n_startup_trials_used_for_split": startup_n,
        "startup_trial_numbers": [e["trial_number"] for e in startup],
        "adaptive_trial_numbers": [e["trial_number"] for e in adaptive],
        "startup_mean_distance_to_optimum": startup_mean_dist,
        "adaptive_mean_distance_to_optimum": adaptive_mean_dist,
        "empirically_concentrating": (
            adaptive_mean_dist is not None and startup_mean_dist is not None
            and adaptive_mean_dist < startup_mean_dist),
    }


def classify_real_trials(trial_records: list[dict]) -> dict:
    """Applied to a REAL search's trial records (fp/checkpoint_search.py, not
    this module's own toy objective): startup/adaptive split by VERIFIED
    n_startup_trials, plus unique-candidate and duplicate-evaluation counts
    -- guide 6.1's remaining per-search-run fields."""
    identity = installed_sampler_identity()
    startup_n = int(identity["n_startup_trials_default"])
    ordered = sorted(trial_records, key=lambda r: r["trial_id"])
    startup = [r for r in ordered if r["trial_id"] < startup_n]
    adaptive = [r for r in ordered if r["trial_id"] >= startup_n]

    def _key(params: dict) -> tuple:
        return tuple(sorted(params.items()))

    seen: dict = {}
    duplicates = 0
    for r in ordered:
        key = _key(r["params"])
        seen[key] = seen.get(key, 0) + 1
        if seen[key] > 1:
            duplicates += 1
    return {
        "schema": SEARCH_INTROSPECTION_SCHEMA,
        "sampler_identity": identity,
        "n_trials_attempted": len(ordered),
        "n_trials_completed": sum(1 for r in ordered if not r.get("pruned")),
        "n_trials_pruned": sum(1 for r in ordered if r.get("pruned")),
        "startup_trial_count": len(startup),
        "adaptive_trial_count": len(adaptive),
        "unique_effective_candidates": len(seen),
        "duplicate_reused_evaluations": duplicates,
    }
