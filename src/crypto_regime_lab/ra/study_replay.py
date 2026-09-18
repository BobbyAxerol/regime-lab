"""Deterministic ask/tell replay for cached-objective studies (RA02.5).

A TPE study restarted from a list of completed trials does not necessarily
reproduce its sampler state. The sanctioned alternative in the guide is
deterministic replay: a fresh study with the same sampler seed re-asks every
recorded proposal in order and re-tells every recorded objective (served
from the cache), which advances the sampler identically to the
uninterrupted run. Prefix equivalence is asserted, not assumed.

Nothing here imports optuna at module import time; the study factory is
injected so the module stays importable without the dependency.
"""
from __future__ import annotations


# A small startup keeps TPE's model in play early: with the default (10) the
# sampler is still in its random phase for short studies and a tell-dropping
# restart would reproduce the same continuation, making the parity control
# vacuous.
STARTUP_TRIALS = 2


class StudyReplayError(ValueError):
    """A replayed proposal diverged from the recorded one."""


class StudyInterrupted(Exception):
    """Simulated crash carrying the records completed so far."""

    def __init__(self, records):
        super().__init__(f"study interrupted after {len(records)} trials")
        self.records = records


def _default_study_factory(seed):
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    return optuna.create_study(
        sampler=optuna.samplers.TPESampler(seed=seed, n_startup_trials=STARTUP_TRIALS),
        direction="maximize")


def _distributions(space):
    """Translate a declarative search space into optuna distributions."""
    import optuna

    resolved = {}
    for name, spec in (space or {}).items():
        if not (isinstance(spec, (list, tuple)) and len(spec) == 2):
            raise ValueError(f"search space entry {name!r} must be (kind, args)")
        kind, args = spec
        if kind == "int":
            resolved[name] = optuna.distributions.IntDistribution(*args)
        elif kind == "float":
            resolved[name] = optuna.distributions.FloatDistribution(*args)
        elif kind == "categorical":
            resolved[name] = optuna.distributions.CategoricalDistribution(args)
        else:
            raise ValueError(f"unsupported search space kind: {kind!r}")
    return resolved


def run_study(seed: int, n_trials: int, objective_of, *, replay=(),
              interrupt_after: int | None = None, study_factory=None,
              space=None) -> dict:
    """Run (or resume) one deterministic study over cached objectives.

    ``replay`` is the ordered list of ``{"params", "value"}`` records the
    interrupted run already completed; each is re-asked and re-told so the
    sampler state advances exactly as it did before the crash.
    ``interrupt_after`` raises ``StudyInterrupted`` after that many trials.
    ``space`` is the declarative search space ({"x": ("int", (0, 5))}).
    """
    factory = study_factory or _default_study_factory
    distributions = _distributions(space)
    study = factory(seed)
    records: list[dict] = []
    evaluations = 0
    for record in replay:
        trial = study.ask(distributions)
        if dict(trial.params) != dict(record["params"]):
            raise StudyReplayError(
                "replayed proposal diverged from the recorded one at trial "
                f"{len(records) + 1}: {dict(trial.params)} != {record['params']}")
        study.tell(trial, record["value"])
        records.append({"params": dict(trial.params), "value": record["value"]})
    for index in range(len(replay), n_trials):
        trial = study.ask(distributions)
        value = objective_of(dict(trial.params))
        evaluations += 1
        study.tell(trial, value)
        records.append({"params": dict(trial.params), "value": value})
        if interrupt_after is not None and len(records) == interrupt_after:
            raise StudyInterrupted(records)
    return {"proposals": [r["params"] for r in records],
            "objectives": [r["value"] for r in records],
            "records": records,
            "evaluations": evaluations,
            "replayed": len(replay)}


def run_study_dropping_tells(seed: int, records, n_more: int,
                             study_factory=None, space=None) -> list[dict]:
    """Red control: resume while dropping the sampler's tell/update calls.

    A restart that reuses cached objectives but never feeds them back to the
    sampler cannot reproduce the uninterrupted continuation. Returns the
    proposals after the recorded prefix.
    """
    factory = study_factory or _default_study_factory
    distributions = _distributions(space)
    study = factory(seed)
    for _record in records:
        study.ask(distributions)  # proposal ignored on purpose: no tell/update
    return [dict(study.ask(distributions).params) for _ in range(n_more)]
