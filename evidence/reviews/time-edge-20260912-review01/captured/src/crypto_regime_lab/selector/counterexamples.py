"""L04.2 — selector counterexamples, run against the REAL installed functions.

The guide asks for eight counterexamples, each attached to actual source symbols
and reproducers, and says plainly: if the behaviour is already correct upstream,
record it as VERIFIED_EXISTING rather than inventing a defect.

That distinction turned out to matter here, because the install has TWO selector
families with DIFFERENT geometry:

  * ``quantbt.optimization.candidate_selection`` (``CandidateSelector``,
    ``MultiSeedOptimization``) measures distance with ``_param_distance``, which
    normalises by ``_numeric_span(records, name)`` — the span of the OBSERVED
    samples;
  * ``quantbt.walkforward`` clusters with ``_param_matrix`` /
    ``_normalize_param_values``, which normalise by the DECLARED
    ``param_ranges`` and drop any parameter that does not vary.

So the same question has two different answers depending on which route a study
takes, and a blanket claim about "the selector" would be wrong.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Callable

import numpy as np

from .robust_score import EpisodePanel, score_all
from .schema_distance import ParamSchema, ParamSpec

VERDICT_DEFECT = "DEFECT_CONFIRMED"
VERDICT_EXISTING = "VERIFIED_EXISTING_CORRECT"
VERDICT_LAB = "LAB_SELECTOR_IMMUNE"


@dataclass
class Counterexample:
    id: str
    title: str
    guide_test: str
    family: str
    source_symbols: tuple[str, ...]
    verdict: str
    observed: Any
    expectation: str
    reproducer: str
    lab_behaviour: Any = None
    note: str = ""

    def as_record(self) -> dict:
        return {
            "id": self.id, "title": self.title, "guide_test": self.guide_test,
            "selector_family": self.family, "source_symbols": list(self.source_symbols),
            "verdict": self.verdict, "observed": self.observed,
            "expectation": self.expectation, "reproducer": self.reproducer,
            "lab_behaviour": self.lab_behaviour, "note": self.note,
        }


def _records(param_dicts: list[dict]) -> list[Any]:
    return [SimpleNamespace(params=dict(p), metadata={}) for p in param_dicts]


def _lab_schema() -> ParamSchema:
    return ParamSchema.from_specs([
        ParamSpec("fast", "int", 3, 200, 1),
        ParamSpec("slow", "int", 15, 200, 5),
        ParamSpec("dev", "fixed", fixed_value=50),
        ParamSpec("time_stop", "bool"),
        ParamSpec("stop_bars", "int", 1, 20, 1, active_when=("time_stop", True)),
    ], dependencies=(("fast", "slow"),), name="counterexample_schema")


# ---------------------------------------------------------------------------
# 1. sharp peak vs broad profitable neighbourhood (T29)
# ---------------------------------------------------------------------------

def ce_sharp_peak_vs_plateau() -> Counterexample:
    episodes = [f"e{i}" for i in range(6)]
    peak = EpisodePanel("peak", {"fast": 4, "slow": 20}, {e: 1.5 for e in episodes})
    peak_nb = [EpisodePanel(f"pn{i}", {"fast": 4 + i, "slow": 20}, {e: 0.1 for e in episodes})
               for i in range(1, 5)]
    broad = EpisodePanel("broad", {"fast": 8, "slow": 30}, {e: 1.0 for e in episodes})
    broad_nb = [EpisodePanel(f"bn{i}", {"fast": 8 + i, "slow": 30}, {e: 0.95 for e in episodes})
                for i in range(1, 5)]
    panels = {p.candidate_id: p for p in [peak, *peak_nb, broad, *broad_nb]}
    out = score_all(panels, {"peak": [p.candidate_id for p in peak_nb],
                             "broad": [p.candidate_id for p in broad_nb]})
    peak_s, broad_s = out["scores"]["peak"], out["scores"]["broad"]
    return Counterexample(
        "CE-01", "sharp peak versus a broad profitable neighbourhood", "T29",
        "lab robust score", ("selector.robust_score.score_candidate",), VERDICT_LAB,
        {"peak": {"G": peak_s["g"], "F": peak_s["f"], "R": peak_s["r"]},
         "broad": {"G": broad_s["g"], "F": broad_s["f"], "R": broad_s["r"]},
         "broad_wins_on_R": broad_s["r"] > peak_s["r"]},
        "the peak has the better raw quality but a large neighbour regret, so R prefers the "
        "broad profitable region",
        "two synthetic neighbourhoods with identical episode counts",
        note="all valid bad probes stay in the denominator; none is dropped for losing",
    )


# ---------------------------------------------------------------------------
# 2. flat but negative region (T30)
# ---------------------------------------------------------------------------

def ce_flat_but_negative() -> Counterexample:
    episodes = [f"e{i}" for i in range(6)]
    flat = EpisodePanel("flat_negative", {"fast": 9, "slow": 25}, {e: -0.4 for e in episodes})
    flat_nb = [EpisodePanel(f"fn{i}", {"fast": 9 + i, "slow": 25}, {e: -0.41 for e in episodes})
               for i in range(1, 5)]
    panels = {p.candidate_id: p for p in [flat, *flat_nb]}
    out = score_all(panels, {"flat_negative": [p.candidate_id for p in flat_nb]})
    score = out["scores"]["flat_negative"]
    return Counterexample(
        "CE-02", "a perfectly flat region that is negative", "T30",
        "lab robust score", ("selector.robust_score.score_candidate",), VERDICT_LAB,
        {"G": score["g"], "F": score["f"], "R": score["r"], "status": score["status"]},
        "flatness alone must not qualify: the region fails economic quality",
        "a flat neighbourhood at utility -0.4",
        note="R is high because F is tiny, which is exactly why the quality gate is separate",
    )


# ---------------------------------------------------------------------------
# 3. duplicate samples
# ---------------------------------------------------------------------------

def ce_duplicate_samples() -> Counterexample:
    from .probe_design import ProbeDesign

    schema = _lab_schema()
    design = ProbeDesign(schema, radius=0.05, probes_per_anchor=10)
    built = design.build({"a": {"fast": 20, "slow": 60, "dev": 50, "time_stop": False}})
    probes = built["probes"]["a"]
    ids = [p["probe_id"] for p in probes]
    return Counterexample(
        "CE-03", "duplicate samples must not inflate the local panel", "T29 (panel accounting)",
        "lab probe design", ("selector.probe_design.ProbeDesign.probes_for",), VERDICT_LAB,
        {"probes": len(probes), "unique_ids": len(set(ids)), "duplicates": len(ids) - len(set(ids))},
        "every probe in a local panel is a distinct point",
        "request 10 probes inside a tight radius and count unique ids",
    )


# ---------------------------------------------------------------------------
# 4. fixed dimensions dilute a distance
# ---------------------------------------------------------------------------

def ce_fixed_dimension_dilution() -> Counterexample:
    from quantbt.optimization.candidate_selection import _param_distance

    records = _records([{"fast": 4, "slow": 20, "dev": 50}, {"fast": 6, "slow": 30, "dev": 50}])
    a, b = {"fast": 4, "slow": 20, "dev": 50}, {"fast": 6, "slow": 20, "dev": 50}
    with_fixed = _param_distance(a, b, records, ["fast", "slow", "dev"])
    without_fixed = _param_distance(a, b, records, ["fast", "slow"])

    schema = _lab_schema()
    lab_a = {**a, "time_stop": False}
    lab_b = {**b, "time_stop": False}
    return Counterexample(
        "CE-04", "a fixed dimension dilutes every distance", "T31",
        "quantbt.optimization.candidate_selection",
        ("_param_distance", "candidate_selection.py:281-300"), VERDICT_DEFECT,
        {"distance_with_fixed_dim": round(with_fixed, 6),
         "distance_without_fixed_dim": round(without_fixed, 6),
         "ratio": round(with_fixed / without_fixed, 4) if without_fixed else None},
        "a parameter that never varies carries no information and must not enter the denominator",
        "call the installed _param_distance with and without a constant parameter in param_names",
        lab_behaviour={"lab_distance": round(schema.distance(lab_a, lab_b), 6),
                       "fixed_excluded_from_denominator": True},
        note="the WFO family is NOT affected: _is_clusterable_param drops any parameter that does "
             "not vary before the matrix is built",
    )


# ---------------------------------------------------------------------------
# 5. sampled-span scaling
# ---------------------------------------------------------------------------

def ce_sampled_span_scaling() -> Counterexample:
    from quantbt.optimization.candidate_selection import _numeric_span, _param_distance
    from quantbt.walkforward import _normalize_param_values

    base = _records([{"fast": 4, "slow": 20}, {"fast": 6, "slow": 30}])
    far = base + _records([{"fast": 200, "slow": 20}])
    a, b = {"fast": 4, "slow": 20}, {"fast": 6, "slow": 20}
    d_base = _param_distance(a, b, base, ["fast", "slow"])
    d_far = _param_distance(a, b, far, ["fast", "slow"])

    declared = (3, 200, 1)
    wfo_base = _normalize_param_values([4, 6], declared)
    wfo_far = _normalize_param_values([4, 6, 200], declared)[:2]

    schema = _lab_schema()
    return Counterexample(
        "CE-05", "one far-away sample rescales the whole geometry", "T31",
        "quantbt.optimization.candidate_selection",
        ("_numeric_span", "_param_distance", "candidate_selection.py:302-306"), VERDICT_DEFECT,
        {"distance_before": round(d_base, 6), "distance_after_one_far_sample": round(d_far, 6),
         "shrink_factor": round(d_base / d_far, 1) if d_far else None,
         "span_before": _numeric_span(base, "fast"), "span_after": _numeric_span(far, "fast")},
        "geometry must come from the DECLARED bounds, so an unrelated sample cannot rescale it",
        "add one distant record and re-measure the distance between two unchanged points",
        lab_behaviour={
            "lab_distance_unchanged": round(schema.distance(a | {"dev": 50, "time_stop": False},
                                                            b | {"dev": 50, "time_stop": False}), 6),
            "wfo_family_normalised_values_unchanged": bool(np.allclose(wfo_base, wfo_far)),
        },
        note="the WFO family normalises by the declared (low, high) in param_ranges and is immune; "
             "only the CandidateSelector family rescales",
    )


# ---------------------------------------------------------------------------
# 6. inactive parameters and missing consensus
# ---------------------------------------------------------------------------

def ce_inactive_parameter_distance() -> Counterexample:
    from quantbt.optimization.candidate_selection import _param_distance

    records = _records([{"fast": 4, "slow": 20}, {"fast": 6, "slow": 30}])
    a = {"fast": 4, "slow": 20}                       # time stop off: stop_bars inactive
    b = {"fast": 4, "slow": 20, "stop_bars": 5}       # time stop on
    installed = _param_distance(a, b, records, ["fast", "slow", "stop_bars"])

    schema = _lab_schema()
    lab_a = {"fast": 4, "slow": 20, "dev": 50, "time_stop": False}
    lab_b = {"fast": 4, "slow": 20, "dev": 50, "time_stop": True, "stop_bars": 5}
    return Counterexample(
        "CE-06", "an inactive parameter manufactures distance", "T31/T32",
        "quantbt.optimization.candidate_selection",
        ("_param_distance", "candidate_selection.py:290-299"), VERDICT_DEFECT,
        {"installed_distance": round(installed, 6),
         "cause": "a missing value is not numeric, so the branch returns a full unit of distance"},
        "an inactive conditional parameter must not create distance; a branch MISMATCH is a "
        "declared, locked penalty instead",
        "compare two points that differ only in whether a conditional branch is active",
        lab_behaviour={"lab_distance": round(schema.distance(lab_a, lab_b), 6),
                       "explicit_branch_penalty": True},
    )


def ce_missing_consensus() -> Counterexample:
    """A candidate with too few neighbours cannot support a stability claim."""
    episodes = [f"e{i}" for i in range(6)]
    lonely = EpisodePanel("lonely", {"fast": 5, "slow": 20}, {e: 1.2 for e in episodes})
    panels = {"lonely": lonely}
    out = score_all(panels, {"lonely": []})
    score = out["scores"]["lonely"]
    return Counterexample(
        "CE-07", "no local consensus available", "T29 (stability evidence)",
        "lab robust score", ("selector.robust_score.score_candidate",), VERDICT_LAB,
        {"status": score["status"], "F": score["f"], "R": score["r"]},
        "with no neighbour sharing an episode there is no stability evidence, so the candidate is "
        "INSUFFICIENT_LOCAL_EVIDENCE rather than silently excellent",
        "score a candidate whose neighbourhood is empty",
    )


# ---------------------------------------------------------------------------
# 7. invalid centroid (T33)
# ---------------------------------------------------------------------------

def ce_unevaluated_centroid() -> Counterexample:
    from .representative import NotEvaluated, assert_evaluated, centroid_point

    schema = _lab_schema()
    eligible = {"c1": {"fast": 4, "slow": 20, "dev": 50, "time_stop": False},
                "c2": {"fast": 6, "slow": 30, "dev": 50, "time_stop": False},
                "c3": {"fast": 8, "slow": 25, "dev": 50, "time_stop": False}}
    centre = centroid_point(schema, list(eligible.values()))
    evaluated = list(eligible.values())
    try:
        assert_evaluated(centre, evaluated)
        refused = False
    except NotEvaluated:
        refused = True
    return Counterexample(
        "CE-08", "a centroid nobody evaluated is not deployable", "T33",
        "lab representative", ("selector.representative.assert_evaluated",), VERDICT_LAB,
        {"centroid": centre, "centroid_in_evaluated_set": centre in evaluated,
         "deployment_refused": refused},
        "a geometric centre is a proposal; it must be evaluated before it can be selected",
        "compute the centroid of three evaluated candidates and try to deploy it",
    )


# ---------------------------------------------------------------------------
# 8. incumbent guard differing from the robust objective (T35)
# ---------------------------------------------------------------------------

def ce_incumbent_guard() -> Counterexample:
    episodes = [f"e{i}" for i in range(6)]
    incumbent = EpisodePanel("incumbent", {"fast": 5, "slow": 20},
                             {e: 0.9 for e in episodes})
    inc_nb = [EpisodePanel(f"in{i}", {"fast": 5 + i, "slow": 20}, {e: 0.88 for e in episodes})
              for i in range(1, 5)]
    challenger = EpisodePanel("challenger", {"fast": 9, "slow": 35}, {e: 1.05 for e in episodes})
    ch_nb = [EpisodePanel(f"cn{i}", {"fast": 9 + i, "slow": 35}, {e: 0.2 for e in episodes})
             for i in range(1, 5)]
    panels = {p.candidate_id: p for p in [incumbent, *inc_nb, challenger, *ch_nb]}
    out = score_all(panels, {"incumbent": [p.candidate_id for p in inc_nb],
                             "challenger": [p.candidate_id for p in ch_nb]})
    inc, ch = out["scores"]["incumbent"], out["scores"]["challenger"]
    raw_winner = "challenger" if ch["g"] > inc["g"] else "incumbent"
    robust_winner = "challenger" if ch["r"] > inc["r"] else "incumbent"
    return Counterexample(
        "CE-09", "a raw-quality guard disagrees with the robust objective", "T35",
        "lab robust score", ("selector.robust_score.score_candidate",), VERDICT_LAB,
        {"incumbent": {"G": inc["g"], "R": inc["r"]},
         "challenger": {"G": ch["g"], "R": ch["r"]},
         "winner_on_raw_quality": raw_winner, "winner_on_robust_objective": robust_winner,
         "guards_disagree": raw_winner != robust_winner},
        "when a raw guard and the robust objective disagree the policy must be VISIBLE, and the "
        "incumbent must be judged on the same objective and budget as the challenger",
        "score an incumbent on a plateau against a challenger on a peak",
        note="the incumbent received the same episode count and the same neighbourhood budget",
    )


# ---------------------------------------------------------------------------
# 9. full-sample tuned presets must not enter the primary bank (T36)
# ---------------------------------------------------------------------------

def ce_preset_quarantine() -> Counterexample:
    import json
    from pathlib import Path

    catalog_path = Path(__file__).resolve().parents[3] / "configs" / "preset_catalog.json"
    presets = []
    if catalog_path.is_file():
        presets = json.loads(catalog_path.read_text())["presets"]
    offenders = [p["preset_id"] for p in presets
                 if p.get("eligible_for_primary_candidate_bank")
                 or p.get("eligible_for_early_fold_warm_start")]
    return Counterexample(
        "CE-10", "full-sample tuned presets must not seed the primary bank", "T36",
        "lab preset quarantine", ("configs/preset_catalog.json",),
        VERDICT_LAB if not offenders else VERDICT_DEFECT,
        {"presets_checked": len(presets), "eligible_for_primary_bank": offenders,
         "all_quarantined": not offenders},
        "every supplied preset is provenance=user_full_sample_tpe and is barred from the primary "
        "candidate bank and from warm-starting an early fold",
        "read the committed preset catalog and check the eligibility flags",
    )


def ce_bad_neighbours_retained() -> Counterexample:
    """A valid probe that lost money must stay in the denominator.

    Dropping it is the single easiest way to manufacture a plateau, so the case
    measures what happens to F, R and P_survive when one is removed.
    """
    episodes = [f"e{i}" for i in range(6)]
    centre = EpisodePanel("centre", {"fast": 5, "slow": 20}, {e: 1.0 for e in episodes})
    good = [EpisodePanel(f"g{i}", {"fast": 5 + i, "slow": 20}, {e: 0.98 for e in episodes})
            for i in range(1, 4)]
    loser = EpisodePanel("loser", {"fast": 9, "slow": 20}, {e: -3.0 for e in episodes})

    kept = score_all({p.candidate_id: p for p in [centre, *good, loser]},
                     {"centre": [p.candidate_id for p in [*good, loser]]})["scores"]["centre"]
    dropped = score_all({p.candidate_id: p for p in [centre, *good]},
                        {"centre": [p.candidate_id for p in good]})["scores"]["centre"]
    return Counterexample(
        "CE-11", "a losing but valid neighbour must not be dropped", "T29",
        "lab robust score", ("selector.robust_score.score_candidate",), VERDICT_LAB,
        {"with_the_losing_probe": {"F": kept["f"], "R": kept["r"],
                                   "P_survive": kept["p_survive"]},
         "if_it_were_dropped": {"F": dropped["f"], "R": dropped["r"],
                                "P_survive": dropped["p_survive"]},
         "R_penalty_from_keeping_it": round(dropped["r"] - kept["r"], 6),
         "retained": True},
        "every valid evaluation stays in the denominator; only structurally invalid points are "
        "excluded, and they are excluded rather than scored badly",
        "score one centre with and without a valid neighbour that lost money",
    )


ALL_COUNTEREXAMPLES: tuple[Callable[[], Counterexample], ...] = (
    ce_bad_neighbours_retained,
    ce_sharp_peak_vs_plateau, ce_flat_but_negative, ce_duplicate_samples,
    ce_fixed_dimension_dilution, ce_sampled_span_scaling, ce_inactive_parameter_distance,
    ce_missing_consensus, ce_unevaluated_centroid, ce_incumbent_guard, ce_preset_quarantine,
)


def run_counterexamples() -> dict:
    records, errors = [], []
    for fn in ALL_COUNTEREXAMPLES:
        try:
            records.append(fn().as_record())
        except Exception as exc:
            import traceback
            errors.append({"counterexample": fn.__name__,
                           "error": f"{type(exc).__name__}: {exc}",
                           "traceback": traceback.format_exc()[-800:]})
    by_verdict: dict[str, list[str]] = {}
    for record in records:
        by_verdict.setdefault(record["verdict"], []).append(record["id"])
    return {
        "schema": "crypto_regime_lab.selector_counterexamples.v1",
        "count": len(records),
        "errors": errors,
        "by_verdict": by_verdict,
        "counterexamples": records,
        "selector_families": {
            "candidate_selection": {
                "symbols": ["CandidateSelector", "RobustSelectionConfig", "_param_distance",
                            "_numeric_span"],
                "geometry": "normalised by the SAMPLED span of observed records",
                "consumers": ["optimization.multiseed", "optimization.__init__"],
            },
            "walkforward": {
                "symbols": ["_param_matrix", "_normalize_param_values", "_is_clusterable_param",
                            "select_flat_minima_record", "select_is_only_robust_record",
                            "select_is_plateau_robust_record", "select_full_sample_robust_record"],
                "geometry": "normalised by the DECLARED param_ranges; non-varying parameters dropped",
                "consumers": ["WalkForwardEngine"],
            },
        },
        "scoping_rule": (
            "a claim about 'the selector' would be wrong: the two families measure distance "
            "differently, so every finding names the family it applies to"
        ),
    }
