"""LAB-04 acceptance tests T29-T36 plus the module invariants behind them."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

LAB_ROOT = Path(__file__).resolve().parent.parent

from crypto_regime_lab.experiments import calendar_baseline as CB
from crypto_regime_lab.experiments.evaluator import ACCOUNT, UTILITY, episode_bounds
from crypto_regime_lab.selector.alpha_schemas import (SCHEMAS, SEED_POINTS, inert_value,
                                                      suggest_point)
from crypto_regime_lab.selector.counterexamples import run_counterexamples
from crypto_regime_lab.selector.probe_design import ProbeDesign
from crypto_regime_lab.selector.representative import (NotEvaluated, assert_evaluated,
                                                       centroid_point, choose_representative,
                                                       medoid)
from crypto_regime_lab.selector.robust_score import EpisodePanel, score_all
from crypto_regime_lab.selector.schema_distance import ParamSchema, ParamSpec

PY_BIN = LAB_ROOT / "environments" / "lab_venv" / "bin" / "python"


@pytest.fixture(scope="module")
def counterexamples():
    return run_counterexamples()


def _panel(cid, params, value, episodes=6):
    return EpisodePanel(cid, params, {f"e{i}": value for i in range(episodes)})


# ---------------------------------------------------------------------------
# T29 -- sharp peak vs broad profitable neighbourhood
# ---------------------------------------------------------------------------

def test_t29_broad_neighbourhood_beats_a_sharp_peak(counterexamples):
    case = next(c for c in counterexamples["counterexamples"] if c["id"] == "CE-01")
    assert case["observed"]["broad_wins_on_R"] is True
    assert case["observed"]["peak"]["G"] > case["observed"]["broad"]["G"], (
        "the peak must be the better candidate on raw quality, or the case proves nothing")
    assert case["observed"]["peak"]["F"] > case["observed"]["broad"]["F"]


def test_t29_bad_neighbour_counterexample_is_first_class(counterexamples):
    case = next(c for c in counterexamples["counterexamples"] if c["id"] == "CE-11")
    assert case["observed"]["retained"] is True
    assert case["observed"]["R_penalty_from_keeping_it"] > 0, (
        "keeping the losing probe must cost the candidate something, or retention is cosmetic")
    assert (case["observed"]["with_the_losing_probe"]["P_survive"]
            < case["observed"]["if_it_were_dropped"]["P_survive"])


def test_t29_valid_bad_probes_stay_in_the_denominator():
    """A losing but valid neighbour must not be dropped to flatter a candidate."""
    centre = _panel("c", {"fast": 5}, 1.0)
    good = [_panel(f"g{i}", {"fast": 5 + i}, 0.99) for i in range(1, 4)]
    bad = _panel("bad", {"fast": 9}, -5.0)
    with_bad = score_all({p.candidate_id: p for p in [centre, *good, bad]},
                         {"c": [p.candidate_id for p in [*good, bad]]})
    without_bad = score_all({p.candidate_id: p for p in [centre, *good]},
                            {"c": [p.candidate_id for p in good]})
    assert with_bad["scores"]["c"]["f"] > without_bad["scores"]["c"]["f"]
    assert with_bad["scores"]["c"]["r"] < without_bad["scores"]["c"]["r"]
    assert with_bad["scores"]["c"]["p_survive"] < without_bad["scores"]["c"]["p_survive"]


def test_t29_runtime_error_is_incomplete_evidence_not_a_loss():
    centre = _panel("c", {"fast": 5}, 1.0)
    broken = EpisodePanel("n1", {"fast": 6}, {"e0": 0.9},
                          failed_episodes={"e1": "engine raised"})
    out = score_all({"c": centre, "n1": broken}, {"c": ["n1"]})
    assert out["scores"]["c"]["status"] == "INCOMPLETE_PANEL"
    assert out["scores"]["c"]["complete_panel"] is False


def test_t29_structurally_invalid_is_not_bad_performance():
    centre = _panel("c", {"fast": 5}, 1.0)
    invalid = EpisodePanel("n1", {"fast": 999}, structurally_invalid=True,
                           invalid_reason="outside declared bounds")
    good = _panel("n2", {"fast": 6}, 0.95)
    out = score_all({"c": centre, "n1": invalid, "n2": good}, {"c": ["n1", "n2"]})
    assert out["scores"]["n1"]["status"] == "STRUCTURALLY_INVALID"
    assert out["scores"]["n1"]["r"] is None
    # the invalid point contributes no regret and no survival denominator
    assert out["scores"]["c"]["neighbours_used"] == 1


# ---------------------------------------------------------------------------
# T30 -- flat but negative
# ---------------------------------------------------------------------------

def test_t30_flat_but_negative_fails_economic_quality(counterexamples):
    case = next(c for c in counterexamples["counterexamples"] if c["id"] == "CE-02")
    assert case["observed"]["status"] == "FAILS_ECONOMIC_QUALITY"
    assert case["observed"]["G"] < 0
    # flatness makes the stability penalty tiny, so R sits right on top of G: the
    # region looks maximally "stable" and is still rejected, by the quality gate alone
    assert abs(case["observed"]["R"] - case["observed"]["G"]) < 0.05
    assert case["observed"]["F"] < 0.05


def test_t30_a_flat_negative_region_is_never_eligible():
    flat = _panel("flat", {"fast": 5}, -0.3)
    nb = [_panel(f"n{i}", {"fast": 5 + i}, -0.31) for i in range(1, 4)]
    out = score_all({p.candidate_id: p for p in [flat, *nb]},
                    {"flat": [p.candidate_id for p in nb]})
    assert out["eligible_candidates"] == []


# ---------------------------------------------------------------------------
# T31 -- fixed / inactive params / a far sampled point
# ---------------------------------------------------------------------------

def test_t31_geometry_is_unchanged_by_a_far_sampled_point(counterexamples):
    case = next(c for c in counterexamples["counterexamples"] if c["id"] == "CE-05")
    assert case["verdict"] == "DEFECT_CONFIRMED"
    assert case["observed"]["shrink_factor"] > 50, (
        "the installed CandidateSelector geometry must visibly collapse, or the case is not the "
        "defect it claims to be")
    assert case["lab_behaviour"]["wfo_family_normalised_values_unchanged"] is True


def test_t31_lab_distance_ignores_samples_entirely():
    schema = ParamSchema.from_specs([ParamSpec("fast", "int", 3, 200, 1),
                                     ParamSpec("slow", "int", 10, 200, 5)])
    a, b = {"fast": 4, "slow": 20}, {"fast": 6, "slow": 20}
    before = schema.distance(a, b)
    # there is nowhere to put a sample: the function does not take one
    assert schema.distance(a, b) == before
    assert before == pytest.approx(abs(4 - 6) / (200 - 3) / 2)


def test_t31_fixed_dimension_is_excluded_from_the_denominator():
    with_fixed = ParamSchema.from_specs([ParamSpec("fast", "int", 0, 10, 1),
                                         ParamSpec("dev", "fixed", fixed_value=50)])
    without = ParamSchema.from_specs([ParamSpec("fast", "int", 0, 10, 1)])
    a = {"fast": 2, "dev": 50}
    b = {"fast": 4, "dev": 50}
    assert with_fixed.distance(a, b) == without.distance({"fast": 2}, {"fast": 4})


def test_t31_inactive_parameter_creates_no_false_distance():
    schema = ParamSchema.from_specs([
        ParamSpec("fast", "int", 0, 10, 1),
        ParamSpec("time_stop", "bool"),
        ParamSpec("stop_bars", "int", 1, 20, 1, active_when=("time_stop", True)),
    ])
    a = {"fast": 4, "time_stop": False, "stop_bars": 1}
    b = {"fast": 4, "time_stop": False, "stop_bars": 19}
    assert schema.distance(a, b) == 0.0, "an inactive key must not separate two points"
    c = {"fast": 4, "time_stop": True, "stop_bars": 19}
    assert schema.distance(a, c) > 0.0, "a real branch change must cost the declared penalty"


# ---------------------------------------------------------------------------
# T32 -- dependent parameter manifold
# ---------------------------------------------------------------------------

def test_t32_probes_on_a_dependent_manifold_are_feasible_and_unique():
    for alpha_id, schema in SCHEMAS.items():
        design = ProbeDesign(schema, radius=0.12, probes_per_anchor=8)
        built = design.build({f"a_{alpha_id}": dict(SEED_POINTS[alpha_id])})
        probes = built["probes"][f"a_{alpha_id}"]
        assert len(probes) == 8, f"{alpha_id}: expected a full local panel"
        ids = [p["probe_id"] for p in probes]
        assert len(set(ids)) == len(ids), f"{alpha_id}: duplicate probes"
        for probe in probes:
            ok, why = schema.is_feasible(probe["point"])
            assert ok, f"{alpha_id}: infeasible probe {why}"
            assert 0.0 < probe["distance_to_anchor"] <= 0.12


def test_t32_a_chained_dependency_is_declared_in_full():
    """A-HASH needs tp1 < tp2 < rr_ratio; declaring only the first link is a gap."""
    schema = SCHEMAS["A-HASH"]
    design = ProbeDesign(schema, probes_per_anchor=8)
    built = design.build({"a": dict(SEED_POINTS["A-HASH"])})
    for probe in built["probes"]["a"]:
        point = probe["point"]
        assert point["tp1_ratio"] < point["tp2_ratio"] < point["rr_ratio"], (
            "the canonical ladder refuses to sort a bad preset, so the schema must never "
            "propose one")


def test_t32_dependencies_are_parameterised_not_repaired():
    schema = SCHEMAS["A-HMA"]
    design = ProbeDesign(schema, probes_per_anchor=8)
    built = design.build({"a": dict(SEED_POINTS["A-HMA"])})
    for probe in built["probes"]["a"]:
        point = probe["point"]
        assert point["min_length"] < point["max_length"]
        assert point["minor_min"] < point["minor_max"]
        assert point["atr_fast"] < point["atr_slow"]


def test_t32_probe_design_is_reproducible_across_processes():
    """A frozen design that changes per interpreter is not frozen."""
    code = (
        "import sys; sys.path.insert(0, 'src');"
        "from crypto_regime_lab.selector.probe_design import ProbeDesign;"
        "from crypto_regime_lab.selector.alpha_schemas import SCHEMAS, SEED_POINTS;"
        "d = ProbeDesign(SCHEMAS['A-VWAP'], probes_per_anchor=8);"
        "b = d.build({'a': dict(SEED_POINTS['A-VWAP'])});"
        "print(','.join(p['probe_id'] for p in b['probes']['a']))"
    )
    runs = set()
    for salt in ("0", "1", "random"):
        done = subprocess.run([str(PY_BIN), "-c", code], cwd=LAB_ROOT, capture_output=True,
                              text=True, env={"PATH": "/usr/bin:/bin", "PYTHONHASHSEED": salt})
        assert done.returncode == 0, done.stderr[-400:]
        runs.add(done.stdout.strip())
    assert len(runs) == 1, f"probe ids differ across PYTHONHASHSEED settings: {runs}"


def test_t32_inactive_conditional_key_still_builds_a_valid_point():
    schema = SCHEMAS["A-VWAP"]
    spec = schema.specs["time_stop_bars"]
    assert inert_value(spec) == int(spec.low)

    class _Trial:
        def suggest_int(self, name, low, high, step=1):
            return low

        def suggest_float(self, name, low, high, step=None):
            return low

        def suggest_categorical(self, name, choices):
            return choices[0]

    point = suggest_point(_Trial(), schema)
    assert point["time_stop_on"] is False
    assert "time_stop_bars" in point, "the adapter requires the key even when the branch is off"
    ok, why = schema.is_feasible(point)
    assert ok, why


# ---------------------------------------------------------------------------
# T33 -- an unevaluated centroid
# ---------------------------------------------------------------------------

def test_t33_unevaluated_centroid_is_not_deployable(counterexamples):
    case = next(c for c in counterexamples["counterexamples"] if c["id"] == "CE-08")
    assert case["observed"]["deployment_refused"] is True
    assert case["observed"]["centroid_in_evaluated_set"] is False


def test_t33_assert_evaluated_accepts_only_a_point_that_was_run():
    schema = SCHEMAS["A-SC"]
    points = [dict(SEED_POINTS["A-SC"], AP=v) for v in (10, 20, 30)]
    centre = centroid_point(schema, points)
    with pytest.raises(NotEvaluated):
        assert_evaluated(centre, [p for p in points if p != centre])
    assert_evaluated(points[0], points)


# ---------------------------------------------------------------------------
# T34 -- medoid metric and tie-break
# ---------------------------------------------------------------------------

def test_t34_medoid_minimises_the_same_distance_the_selector_declares():
    schema = SCHEMAS["A-SC"]
    candidates = {f"c{i}": dict(SEED_POINTS["A-SC"], AP=v)
                  for i, v in enumerate((10, 12, 14, 40))}
    rep = medoid(schema, candidates)
    totals = {cid: sum(schema.distance(candidates[cid], candidates[other])
                       for other in candidates if other != cid)
              for cid in candidates}
    assert rep.total_distance == pytest.approx(min(totals.values()))
    assert rep.candidate_id == min(totals, key=lambda k: (totals[k], k))


def test_t34_tie_break_is_deterministic_on_the_stable_id():
    schema = ParamSchema.from_specs([ParamSpec("fast", "int", 0, 10, 1)])
    candidates = {"zeta": {"fast": 2}, "alpha": {"fast": 8}}
    rep = medoid(schema, candidates)
    assert rep.tie_broken_on_id is True
    assert rep.candidate_id == "alpha"
    assert medoid(schema, dict(reversed(list(candidates.items())))).candidate_id == "alpha"


# ---------------------------------------------------------------------------
# T35 -- incumbent guard vs the robust objective
# ---------------------------------------------------------------------------

def test_t35_incumbent_guard_disagreement_is_visible(counterexamples):
    case = next(c for c in counterexamples["counterexamples"] if c["id"] == "CE-09")
    assert case["observed"]["guards_disagree"] is True
    assert case["observed"]["winner_on_raw_quality"] == "challenger"
    assert case["observed"]["winner_on_robust_objective"] == "incumbent"


def test_t35_incumbent_receives_the_same_validation_budget():
    episodes = [f"e{i}" for i in range(6)]
    inc = EpisodePanel("inc", {"fast": 5}, {e: 0.9 for e in episodes})
    inc_nb = [_panel(f"i{i}", {"fast": 5 + i}, 0.88) for i in range(1, 5)]
    ch = EpisodePanel("ch", {"fast": 30}, {e: 1.0 for e in episodes})
    ch_nb = [_panel(f"c{i}", {"fast": 30 + i}, 0.5) for i in range(1, 5)]
    out = score_all({p.candidate_id: p for p in [inc, *inc_nb, ch, *ch_nb]},
                    {"inc": [p.candidate_id for p in inc_nb],
                     "ch": [p.candidate_id for p in ch_nb]})
    assert out["scores"]["inc"]["episodes_used"] == out["scores"]["ch"]["episodes_used"]
    assert out["scores"]["inc"]["neighbours_used"] == out["scores"]["ch"]["neighbours_used"]


def test_t35_the_incumbent_is_an_anchor_with_a_full_probe_budget():
    """Guide 7.2: the incumbent sits inside the anchor set, not outside it."""
    source = Path(LAB_ROOT / "src/crypto_regime_lab/experiments/calendar_baseline.py").read_text()
    assert "incumbent_anchor_ids" in source
    schema = SCHEMAS["A-SC"]
    design = ProbeDesign(schema, probes_per_anchor=8)
    built = design.build({"incumbent_A_x": dict(SEED_POINTS["A-SC"])})
    assert len(built["probes"]["incumbent_A_x"]) == 8


# ---------------------------------------------------------------------------
# T36 -- full-sample tuned presets
# ---------------------------------------------------------------------------

def test_t36_presets_are_barred_from_the_primary_bank(counterexamples):
    case = next(c for c in counterexamples["counterexamples"] if c["id"] == "CE-10")
    assert case["observed"]["all_quarantined"] is True
    assert case["observed"]["presets_checked"] > 0
    assert case["observed"]["eligible_for_primary_bank"] == []


def test_t36_no_preset_value_is_a_seed_point_or_an_anchor():
    catalog = json.loads((LAB_ROOT / "configs" / "preset_catalog.json").read_text())
    preset_points = {json.dumps(p["values"], sort_keys=True) for p in catalog["presets"]}
    for alpha_id, point in SEED_POINTS.items():
        assert json.dumps(point, sort_keys=True) not in preset_points, (
            f"{alpha_id}: the registered seed point must not be a supplied preset")


def test_t36_declared_bounds_enclose_the_alpha_operating_range():
    """The bounds were widened to cover where each alpha functions; check they did."""
    catalog = json.loads((LAB_ROOT / "configs" / "preset_catalog.json").read_text())
    misses = []
    for preset in catalog["presets"]:
        schema = SCHEMAS.get(preset["declared_in_alpha"])
        if schema is None:
            continue
        for key, value in preset["values"].items():
            spec = schema.specs.get(key)
            if spec is None or spec.kind not in ("int", "float", "log"):
                continue
            if not (spec.low <= float(value) <= spec.high):
                misses.append((preset["declared_in_alpha"], key, value, spec.low, spec.high))
    assert not misses, f"declared bounds exclude the alpha's operating range: {misses[:5]}"


# ---------------------------------------------------------------------------
# counterexample suite and family scoping
# ---------------------------------------------------------------------------

def test_counterexamples_all_run_without_error(counterexamples):
    assert counterexamples["errors"] == []
    assert counterexamples["count"] == 11


def test_findings_are_scoped_to_a_selector_family(counterexamples):
    for case in counterexamples["counterexamples"]:
        assert case["selector_family"], f"{case['id']} has no selector family"
        if case["verdict"] == "DEFECT_CONFIRMED":
            assert case["selector_family"] == "quantbt.optimization.candidate_selection"
            assert case["source_symbols"], f"{case['id']} has no source symbol"


def test_wfo_family_is_verified_not_accused():
    """The WFO record selectors normalise by DECLARED ranges and drop fixed params."""
    from quantbt.walkforward import _is_clusterable_param, _normalize_param_values

    records = [type("R", (), {"params": {"fast": 4, "dev": 50}})(),
               type("R", (), {"params": {"fast": 9, "dev": 50}})()]
    assert _is_clusterable_param("fast", (3, 40, 1), records) is True
    assert _is_clusterable_param("dev", (50, 50, 1), records) is False
    near = _normalize_param_values([4, 9], (3, 40, 1))
    far = _normalize_param_values([4, 9, 400], (3, 40, 1))[:2]
    assert np.allclose(near, far), "declared-range normalisation must ignore a far sample"


# ---------------------------------------------------------------------------
# the experiment's own invariants
# ---------------------------------------------------------------------------

def test_calendar_stays_inside_the_development_role():
    registration = json.loads((LAB_ROOT / "configs" / "study_registration.json").read_text())
    role = registration["data_roles"]["development"]
    import pandas as pd
    start, end = pd.Timestamp(role["start"], tz="UTC"), pd.Timestamp(role["end"], tz="UTC")
    for window in CB.CALENDAR.fold_windows():
        assert pd.Timestamp(window["train_start"]) >= start
        assert pd.Timestamp(window["test_end"]) <= end + pd.Timedelta(days=1)


def test_folds_are_contiguous_and_do_not_overlap_their_own_training_window():
    windows = CB.CALENDAR.fold_windows()
    for earlier, later in zip(windows, windows[1:]):
        assert earlier["test_end"] == later["cutoff"], "OOS coverage must be contiguous"
    for window in windows:
        assert window["train_start"] < window["cutoff"] <= window["test_end"]


def test_budget_matches_the_guide():
    assert CB.BUDGET.discovery_trials == 64
    assert CB.BUDGET.probes_per_anchor == 8
    assert CB.BUDGET.nominal_total == 96


def test_account_contract_matches_the_frozen_registration():
    registration = json.loads((LAB_ROOT / "configs" / "study_registration.json").read_text())
    account = registration["execution"]["account_contract"]
    costs = registration["execution"]["fee_funding_slippage_config"]
    assert ACCOUNT["initial_capital_usdt"] == account["initial_capital_usdt"]
    assert ACCOUNT["entry_notional_usdt"] == account["entry_notional_usdt"]
    assert ACCOUNT["taker_fee_rate"] == costs["taker_fee_rate"]
    assert ACCOUNT["use_funding"] is False


def test_utility_costs_are_not_charged_twice():
    assert UTILITY["turnover_penalty"] == 0.0, (
        "fees and slippage are already inside net return; a turnover penalty on top would "
        "charge the same cost twice (guide 7.3)")


def test_inner_episodes_have_equal_length():
    import pandas as pd
    index = pd.date_range("2021-01-01", periods=1003, freq="15min", tz="UTC")
    bounds = episode_bounds(index, 6)
    sizes = {hi - lo for _, lo, hi in bounds}
    assert len(sizes) == 1, "episodes of unequal length may not be pooled into one score"
    assert bounds[-1][2] == len(index)


def test_a_not_ready_alpha_reports_null_never_zero():
    import pandas as pd
    cell = CB.run_cell("A-HASH", "BTCUSDT", pd.DataFrame())
    assert cell["status"] == "NOT_READY"
    for arm in CB.ARMS:
        assert cell["arms"][arm]["net_return"] is None


# ---------------------------------------------------------------------------
# centroid geometry (T33/T34 support) -- three defects found on re-review
# ---------------------------------------------------------------------------

def test_centroid_of_an_ordered_pair_stays_feasible():
    """Averaging two ordered points and rounding could collapse them onto one value."""
    schema = ParamSchema.from_specs(
        [ParamSpec("lo", "int", 1, 10, 1), ParamSpec("hi", "int", 1, 10, 1)],
        dependencies=(("lo", "hi"),))
    centre = centroid_point(schema, [{"lo": 3, "hi": 4}, {"lo": 4, "hi": 5}])
    ok, why = schema.is_feasible(centre)
    assert ok, f"centroid violates its own schema: {why} ({centre})"
    assert centre["lo"] < centre["hi"]


def test_centroid_of_a_log_parameter_is_the_geometric_mean():
    """Distance for a log kind is measured in log space; the centre must match."""
    import math

    schema = ParamSchema.from_specs([ParamSpec("x", "log", 1.0, 1000.0)])
    centre = centroid_point(schema, [{"x": 1.0}, {"x": 1000.0}])
    assert centre["x"] == pytest.approx(math.sqrt(1.0 * 1000.0))
    assert centre["x"] != pytest.approx((1.0 + 1000.0) / 2)


def test_centroid_lands_on_the_declared_grid_and_inside_the_bounds():
    schema = ParamSchema.from_specs([ParamSpec("n", "int", 10, 100, 5)])
    centre = centroid_point(schema, [{"n": 10}, {"n": 25}])
    assert (centre["n"] - 10) % 5 == 0
    assert 10 <= centre["n"] <= 100


def test_centroid_categorical_tie_break_is_process_stable():
    """`set` iteration over str is salted, so a tie could move between runs."""
    code = (
        "import sys; sys.path.insert(0, 'src');"
        "from crypto_regime_lab.selector.representative import centroid_point;"
        "from crypto_regime_lab.selector.schema_distance import ParamSchema, ParamSpec;"
        "s = ParamSchema.from_specs([ParamSpec('m','categorical',choices=('a','b','c'))]);"
        "print(centroid_point(s, [{'m':'a'},{'m':'b'},{'m':'c'}])['m'])"
    )
    seen = set()
    for salt in ("0", "1", "12345"):
        done = subprocess.run([str(PY_BIN), "-c", code], cwd=LAB_ROOT, capture_output=True,
                              text=True, env={"PATH": "/usr/bin:/bin", "PYTHONHASHSEED": salt})
        assert done.returncode == 0, done.stderr[-300:]
        seen.add(done.stdout.strip())
    assert len(seen) == 1, f"centroid tie-break varies with PYTHONHASHSEED: {seen}"


def test_representative_reports_whether_the_centroid_is_even_feasible():
    schema = SCHEMAS["A-HMA"]
    eligible = {f"c{i}": dict(SEED_POINTS["A-HMA"], min_length=v)
                for i, v in enumerate((100, 140, 180))}
    record = choose_representative(schema, eligible,
                                   evaluated_points=list(eligible.values()))
    assert "centroid_feasible" in record
    assert record["centroid_deployable"] is record["centroid_was_evaluated"]


def test_distance_names_a_missing_active_parameter_instead_of_raising_keyerror():
    from crypto_regime_lab.selector.schema_distance import SchemaError

    schema = ParamSchema.from_specs([ParamSpec("fast", "int", 1, 10, 1),
                                     ParamSpec("slow", "int", 1, 10, 1)])
    with pytest.raises(SchemaError, match="slow"):
        schema.distance({"fast": 2, "slow": 5}, {"fast": 3})


def test_p_survive_scope_is_recorded_in_the_evidence():
    out = score_all({"c": _panel("c", {"fast": 5}, 1.0),
                     "n": _panel("n", {"fast": 6}, 0.9)}, {"c": ["n"]})
    assert "local panel" in out["p_survive_scope"].lower()
    assert "candidate itself plus its neighbours" in out["p_survive_scope"]


# ---------------------------------------------------------------------------
# handoff: the patch proposal must stay a proposal
# ---------------------------------------------------------------------------

def test_the_patch_proposal_exists_and_says_it_is_not_applied():
    diff = (LAB_ROOT / "handoff" / "lab_only_patch.diff").read_text()
    readme = (LAB_ROOT / "handoff" / "README.md").read_text()
    assert "PROPOSAL ONLY -- NOT APPLIED" in diff
    assert "candidate_selection" in diff
    for case in ("CE-04", "CE-05", "CE-06"):
        assert case in diff, f"{case} must be cited as the origin of the change"
    assert "NOT APPLIED" in readme
    assert "walkforward" in readme, "the proposal must scope itself away from the WFO family"


def test_the_installed_engine_was_not_patched():
    """Proof, not assertion: the installed function still has its original body."""
    import inspect

    from quantbt.optimization import candidate_selection

    source = inspect.getsource(candidate_selection._param_distance)
    # the three defects the proposal targets must still be present upstream
    assert "span = _numeric_span(records, name)" in source, (
        "the installed wheel appears to have been modified; the pin must stay untouched")
    assert "for name in param_names:" in source
    assert "math.sqrt(total / len(param_names))" in source
    assert "_declared_span" not in source, "the proposal was applied to the installed package"


def test_the_lab_selector_does_not_depend_on_the_proposal():
    """The lab must work whether or not upstream ever takes the patch."""
    import crypto_regime_lab.selector.schema_distance as sd

    source = Path(sd.__file__).read_text()
    assert "_numeric_span" not in source
    assert "candidate_selection" not in source


def test_radius_sensitivity_forbids_reading_R_across_radii():
    """A smaller radius mechanically inflates R; comparing it across radii is a category error."""
    path = LAB_ROOT / "configs" / "lab04_probe_radius_sensitivity.json"
    if not path.is_file():
        pytest.skip("run scripts/probe_radius_sensitivity.py")
    record = json.loads(path.read_text())
    assert record["primary_radius"] == 0.12
    assert record["declared_before_the_run"] is True
    assert "R" in record["not_comparable_across_radii"]
    assert "F" in record["not_comparable_across_radii"]
    assert "G" in record["comparable_across_radii"]
    assert "artefact of the geometry" in record["R_is_not_comparable_across_radii"]
    # the primary radius must be one of the probed radii and must not have been moved
    assert record["primary_radius"] in record["radii"]


def test_the_anchor_comparison_admits_that_both_arms_move():
    """Arm A ranks probes too, so an anchor change is not an arm-B-only manipulation."""
    path = LAB_ROOT / "configs" / "lab04_anchor_design_sensitivity.json"
    if not path.is_file():
        pytest.skip("run scripts/compare_anchor_designs.py")
    record = json.loads(path.read_text())
    mechanism = record["mechanism"]
    assert "arm_A_also_moved_in_cells" in mechanism
    assert "neither arm should be described as invariant" in mechanism["why_arm_A_moves"]
    for row in record["per_cell"]:
        assert "arm_A_changed" in row and "arm_B_changed" in row
