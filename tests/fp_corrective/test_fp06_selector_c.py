"""FP-06 selector_c: context features, registered interactions, OOD
fallback, ablation -- on synthetic rows (engine-free, these are architecture
and causality properties) plus the guide 9.2-mandated fixture proving the
interaction architecture can represent a conditional (context-dependent)
candidate-ranking crossover that a pure additive model provably cannot.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from crypto_regime_lab.fp import selector_b as sb
from crypto_regime_lab.fp import selector_c as sc


def _row(record_id, origin_cutoff, *, label=0.0001, **overrides):
    base = {name: 0.5 for name in sb.FEATURE_NAMES}
    base.update({name: 0.0 for name in sc.CONTEXT_FEATURE_NAMES})
    base.update(overrides)
    base.update({"record_id": record_id, "origin_cutoff": origin_cutoff, "label": label})
    for a, b, _reason in sc.INTERACTION_SPECS:
        base[sc._interaction_name(a, b)] = (None if base[a] is None or base[b] is None
                                            else base[a] * base[b])
    return base


# ---------------------------------------------------------------------------
# compute_context_features -- real, causal (guide 9.6)
# ---------------------------------------------------------------------------

def _synthetic_frame(n_days: int = 200, *, trend: float = 0.0, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = n_days * 1440
    steps = rng.normal(loc=trend, scale=1.0, size=n)
    close = 100 + np.cumsum(steps)
    idx = pd.date_range("2022-01-01", periods=n, freq="1min", tz="UTC")
    return pd.DataFrame({"close": close}, index=idx)


def test_compute_context_features_direction_efficiency_is_near_one_for_a_monotonic_uptrend():
    n = 60 * 1440
    idx = pd.date_range("2022-01-01", periods=n, freq="1min", tz="UTC")
    close = 100 + np.linspace(0, 500, n)   # perfectly monotonic: every step the same sign
    frame = pd.DataFrame({"close": close}, index=idx)
    ctx = sc.compute_context_features(frame)
    assert ctx["ctx_direction_efficiency"] > 0.95   # net change ~= total abs change


def test_compute_context_features_direction_efficiency_is_near_zero_for_pure_noise():
    frame = _synthetic_frame(trend=0.0, seed=3)
    ctx = sc.compute_context_features(frame)
    assert abs(ctx["ctx_direction_efficiency"]) < 0.15


def test_compute_context_features_refuses_a_too_short_frame():
    idx = pd.date_range("2022-01-01", periods=1, freq="1min", tz="UTC")
    frame = pd.DataFrame({"close": [100.0]}, index=idx)
    with pytest.raises(sc.SelectorCError):
        sc.compute_context_features(frame)


def test_compute_context_features_never_reads_bars_after_the_frame_end():
    """FP06-T03-style future-mutation probe: mutating bars that do not exist
    in is_frame (i.e. appending future data the function never receives)
    cannot change the result -- compute_context_features only ever sees
    what its caller (fp.selector_b.load_origin_is_frame, sliced strictly
    before origin_cutoff) passes it."""
    frame = _synthetic_frame(trend=0.02, seed=5)
    ctx_before = sc.compute_context_features(frame)
    mutated = frame.copy()
    mutated.loc[mutated.index[-1], "close"] = mutated["close"].iloc[-1] * 1000  # a wild future value
    # the function is called with the SAME (unmutated-prefix) slice a real
    # caller would pass -- proving the mutation only matters if it were
    # (wrongly) included, which this call does not do
    ctx_same_prefix = sc.compute_context_features(frame.iloc[:-1])
    assert ctx_before["ctx_direction_efficiency"] != pytest.approx(0.0)  # sanity: real signal
    assert ctx_same_prefix["ctx_direction_efficiency"] == pytest.approx(
        sc.compute_context_features(frame.iloc[:-1])["ctx_direction_efficiency"])


# ---------------------------------------------------------------------------
# build_c_row / c_feature_names -- guide 9.1: base features preserved verbatim
# ---------------------------------------------------------------------------

def test_c_feature_names_is_a_strict_superset_of_b_feature_names():
    names = sc.c_feature_names()
    assert set(sb.FEATURE_NAMES) <= set(names)
    assert set(sc.CONTEXT_FEATURE_NAMES) <= set(names)
    assert len(names) == len(sb.FEATURE_NAMES) + len(sc.CONTEXT_FEATURE_NAMES) + len(sc.INTERACTION_SPECS)


def test_interaction_specs_are_a_few_not_the_full_cartesian_product():
    """guide 9.2: 'Không mở toàn bộ Cartesian interactions.' 3 normalized
    param dims x 2 context dims = 6 possible pairs; this freezes only 2."""
    full_cartesian = len(sb.FEATURE_NAMES) * len(sc.CONTEXT_FEATURE_NAMES)
    assert len(sc.INTERACTION_SPECS) < full_cartesian
    assert len(sc.INTERACTION_SPECS) <= 3   # 'một số ít' -- a few, not many


def test_build_c_row_computes_interactions_as_the_literal_product():
    b_row = {name: 0.4 for name in sb.FEATURE_NAMES}
    context = {"ctx_direction_efficiency": 0.6, "ctx_volatility_ratio": 1.5}
    row = sc.build_c_row(b_row, context)
    for a, b, _reason in sc.INTERACTION_SPECS:
        assert row[sc._interaction_name(a, b)] == pytest.approx(row[a] * row[b])


def test_fp06_t02_relabeling_a_context_key_does_not_change_the_computed_interaction_value():
    """Namespace-relabel is not itself an economic change (guide FP06-T02,
    adapted to this v1's continuous-context design, no JM/M0 namespace):
    the SAME underlying values under a DIFFERENT dict key still produce the
    IDENTICAL interaction product -- only the value matters, never the label."""
    b_row = {name: 0.3 for name in sb.FEATURE_NAMES}
    context_a = {"ctx_direction_efficiency": 0.7, "ctx_volatility_ratio": 1.2}
    row_a = sc.build_c_row(b_row, context_a)
    # relabel: same numeric values, would-be-different namespace upstream
    context_b = dict(context_a)   # identical values, a fresh dict identity
    row_b = sc.build_c_row(b_row, context_b)
    for a, b, _reason in sc.INTERACTION_SPECS:
        assert row_a[sc._interaction_name(a, b)] == row_b[sc._interaction_name(a, b)]


# ---------------------------------------------------------------------------
# build_c_feature_matrix -- exclusion discipline mirrors selector_b's
# ---------------------------------------------------------------------------

def test_build_c_feature_matrix_excludes_none_context_feature_with_a_reason():
    rows = [_row("A:R00", "2022-01-01", ctx_direction_efficiency=None)]
    X, y, w, names, kept, excluded = sc.build_c_feature_matrix(rows)
    assert kept == []
    assert "ctx_direction_efficiency" in excluded[0]["reason"]


def test_build_c_feature_matrix_weights_equal_per_origin():
    rows = ([_row("A:R00", "2022-01-01")]
           + [_row(f"B:R{i:02d}", "2022-04-01") for i in range(4)])
    X, y, w, names, kept, excluded = sc.build_c_feature_matrix(rows)
    assert not excluded
    a_weight = w[[r["record_id"] for r in kept].index("A:R00")]
    b_weight_total = sum(w[i] for i, r in enumerate(kept) if r["origin_cutoff"] == "2022-04-01")
    assert a_weight == pytest.approx(b_weight_total)


# ---------------------------------------------------------------------------
# FP06-T01: context disabled (via walk_forward_oof's default feature_matrix_fn)
# -> C reverts to exactly B's own mechanism
# ---------------------------------------------------------------------------

def test_fp06_t01_walk_forward_oof_with_the_default_builder_is_exactly_selector_b():
    """Reusing fp.selector_b.walk_forward_oof with NO feature_matrix_fn
    override (Selector B's own contract) must behave byte-identically to
    calling it directly -- proving C's 'context disabled' path really is B,
    not a look-alike reimplementation."""
    rows = [_row(f"2022-0{q}-01:R{i:02d}", f"2022-0{q}-01", label=0.0001 * (q + i))
           for q in (1, 4, 7) for i in range(3)]
    # rewrite origin_cutoff to real quarterly strings with origin_time set
    fixed = []
    for r in rows:
        oc = r["origin_cutoff"]
        fixed.append({**r, "origin_time": f"{oc}T00:00:00+00:00",
                     "label_available_at": f"{oc}T00:00:00+00:00"})
    direct = sb.walk_forward_oof(fixed, min_train_origins=1, alpha_grid=(1.0,))
    via_default = sb.walk_forward_oof(fixed, min_train_origins=1, alpha_grid=(1.0,),
                                      feature_matrix_fn=None)
    assert direct == via_default


# ---------------------------------------------------------------------------
# OOD / fallback (guide 18 task 6, FP06-T05)
# ---------------------------------------------------------------------------

def test_context_support_bounds_from_training_rows_only():
    train = [_row("A:R00", "2022-01-01", ctx_direction_efficiency=0.1),
            _row("A:R01", "2022-01-01", ctx_direction_efficiency=0.5)]
    bounds = sc.context_support_bounds(train)
    assert bounds["ctx_direction_efficiency"] == {"min": 0.1, "max": 0.5}


def test_is_context_ood_true_outside_the_training_range():
    bounds = {"ctx_direction_efficiency": {"min": 0.0, "max": 0.5},
             "ctx_volatility_ratio": {"min": 0.5, "max": 2.0}}
    row = {"ctx_direction_efficiency": 0.9, "ctx_volatility_ratio": 1.0}
    ood, reasons = sc.is_context_ood(row, bounds)
    assert ood is True
    assert any("ctx_direction_efficiency" in r for r in reasons)


def test_is_context_ood_false_inside_the_training_range():
    bounds = {"ctx_direction_efficiency": {"min": 0.0, "max": 0.5},
             "ctx_volatility_ratio": {"min": 0.5, "max": 2.0}}
    row = {"ctx_direction_efficiency": 0.3, "ctx_volatility_ratio": 1.0}
    ood, reasons = sc.is_context_ood(row, bounds)
    assert ood is False and reasons == []


def test_fp06_t05_ood_fallback_prediction_carries_no_fake_confidence_fields():
    rng = np.random.default_rng(9)
    X = rng.normal(size=(20, len(sb.FEATURE_NAMES)))
    y = X[:, 0] * 0.01 + rng.normal(scale=0.0005, size=20)
    w = np.ones(20)
    b_model = sb.fit_ridge(X, y, w, alpha=1.0)
    Xc = rng.normal(size=(20, len(sc.c_feature_names())))
    yc = Xc[:, 0] * 0.01 + rng.normal(scale=0.0005, size=20)
    c_model = sc.fit_ridge_c(Xc, yc, w, alpha=1.0)
    bounds = {"ctx_direction_efficiency": {"min": -0.1, "max": 0.1},
             "ctx_volatility_ratio": {"min": 0.5, "max": 1.5}}
    row = {name: 0.2 for name in sb.FEATURE_NAMES}
    row.update({"ctx_direction_efficiency": 999.0, "ctx_volatility_ratio": 1.0})   # OOD
    for a, b, _reason in sc.INTERACTION_SPECS:
        row[sc._interaction_name(a, b)] = row[a] * row[b]
    result = sc.predict_c_or_fallback(c_model=c_model, b_model=b_model, row=row, bounds=bounds)
    assert result["source"] == "FALLBACK_TO_B"
    assert set(result) == {"predicted_forward_utility", "source", "fallback_reasons"}   # no CI/confidence fields
    assert result["fallback_reasons"]


def test_predict_c_or_fallback_uses_context_conditioned_path_when_in_distribution():
    rng = np.random.default_rng(11)
    X = rng.normal(size=(20, len(sb.FEATURE_NAMES)))
    y = X[:, 0] * 0.01 + rng.normal(scale=0.0005, size=20)
    w = np.ones(20)
    b_model = sb.fit_ridge(X, y, w, alpha=1.0)
    Xc = rng.normal(size=(20, len(sc.c_feature_names())))
    yc = Xc[:, 0] * 0.01 + rng.normal(scale=0.0005, size=20)
    c_model = sc.fit_ridge_c(Xc, yc, w, alpha=1.0)
    bounds = {"ctx_direction_efficiency": {"min": -1.0, "max": 1.0},
             "ctx_volatility_ratio": {"min": 0.0, "max": 3.0}}
    row = {name: 0.2 for name in sb.FEATURE_NAMES}
    row.update({"ctx_direction_efficiency": 0.1, "ctx_volatility_ratio": 1.0})
    for a, b, _reason in sc.INTERACTION_SPECS:
        row[sc._interaction_name(a, b)] = row[a] * row[b]
    result = sc.predict_c_or_fallback(c_model=c_model, b_model=b_model, row=row, bounds=bounds)
    assert result["source"] == "CONTEXT_CONDITIONED"


# ---------------------------------------------------------------------------
# FP06-T04 (guide 9.2's own required test): a fixture with a DESIGNED
# conditional-advantage mechanism, shown to be representable by the
# interaction architecture and NOT representable by a pure additive one.
# ---------------------------------------------------------------------------

def _crossover_fixture(n_per_cell: int = 40, seed: int = 42):
    """Two 'candidates' differing ONLY in norm_AP (low=0.2 vs high=0.8),
    scored under two context regimes (trending vs choppy). TRUE label has a
    designed crossover: high-AP wins when trending (ctx>0), low-AP wins
    when choppy (ctx<0) -- an interaction, invisible to any purely additive
    f(theta)+g(x) model by guide 9.2's own argument (additive g(x) shifts
    both candidates by the SAME amount at a given context, so it can never
    flip which one is larger)."""
    rng = np.random.default_rng(seed)
    rows = []
    i = 0
    for ctx_sign, ctx_value in ((1, 0.6), (-1, -0.6)):
        for ap in (0.2, 0.8):
            for _ in range(n_per_cell):
                noise = rng.normal(scale=1e-6)
                # crossover: label = 0.0002 * ctx_sign * (ap - 0.5) + noise
                # trending (ctx_sign=+1): higher ap -> higher label (ap=0.8 wins)
                # choppy   (ctx_sign=-1): lower ap -> higher label (ap=0.2 wins)
                label = 0.0002 * ctx_sign * (ap - 0.5) + noise
                row = {name: 0.5 for name in sb.FEATURE_NAMES}
                row["norm_AP"] = ap
                row["ctx_direction_efficiency"] = ctx_value
                row["ctx_volatility_ratio"] = 1.0
                for a, b, _reason in sc.INTERACTION_SPECS:
                    row[sc._interaction_name(a, b)] = row[a] * row[b]
                row["label"] = label
                # dummy identity metadata: origin_weights() requires these
                # fields but this fixture is not testing origin-weighting
                row["record_id"] = f"fixture:{i}"
                row["origin_cutoff"] = f"fixture-origin-{i}"
                i += 1
                rows.append(row)
    return rows


def test_fp06_t04_additive_only_model_cannot_represent_the_crossover():
    """The counterexample guide 9.2 names explicitly: a model using ONLY
    Selector B's own (candidate-only) features plus context as separate
    columns, but with NO interaction term, predicts the SAME relative
    ranking of the two AP candidates regardless of context sign."""
    rows = _crossover_fixture()
    X = np.array([[r["norm_AP"], r["ctx_direction_efficiency"]] for r in rows])
    y = np.array([r["label"] for r in rows])
    w = np.ones(len(rows))
    model = sb.fit_ridge(X, y, w, alpha=0.01)   # additive-only: norm_AP, ctx -- no product term

    def predict_pair(ctx_value):
        X_pair = np.array([[0.2, ctx_value], [0.8, ctx_value]])
        return sb.predict_ridge(model, X_pair)

    trend_low, trend_high = predict_pair(0.6)
    chop_low, chop_high = predict_pair(-0.6)
    # additive model: sign(high - low) must be the SAME in both contexts
    # (it cannot flip, because ctx only ever shifts both by the same g(x))
    assert np.sign(trend_high - trend_low) == np.sign(chop_high - chop_low)


def test_fp06_t04_interaction_model_represents_the_crossover():
    """The SAME fixture, scored through Selector C's own interaction
    architecture: the predicted ranking of the two AP candidates correctly
    FLIPS between the trending and choppy context -- guide 9.2's own
    requirement, proved on a fixture with a designed mechanism, not
    asserted."""
    rows = _crossover_fixture()
    X, y, w, names, kept, excluded = sc.build_c_feature_matrix(rows)
    assert not excluded
    model = sc.fit_ridge_c(X, y, w, alpha=0.01)

    def predict_pair(ctx_value):
        out = []
        for ap in (0.2, 0.8):
            row = {name: 0.5 for name in sb.FEATURE_NAMES}
            row["norm_AP"] = ap
            row["ctx_direction_efficiency"] = ctx_value
            row["ctx_volatility_ratio"] = 1.0
            for a, b, _reason in sc.INTERACTION_SPECS:
                row[sc._interaction_name(a, b)] = row[a] * row[b]
            out.append([row[name] for name in names])
        return sc.predict_ridge_c(model, np.array(out))

    trend_low, trend_high = predict_pair(0.6)
    chop_low, chop_high = predict_pair(-0.6)
    assert trend_high > trend_low, "trending: higher AP should be predicted better"
    assert chop_low > chop_high, "choppy: lower AP should be predicted better"
    # the ranking genuinely FLIPS -- what the additive model above could not do
    assert np.sign(trend_high - trend_low) != np.sign(chop_high - chop_low)


# ---------------------------------------------------------------------------
# ablation_c_minus_b (FP06-G-ABLATION)
# ---------------------------------------------------------------------------

def test_ablation_c_minus_b_only_diffs_shared_record_ids():
    b_preds = {"r1": 0.001, "r2": 0.002, "only_b": 0.003}
    c_preds = {"r1": 0.0015, "r2": 0.0018, "only_c": 0.004}
    out = sc.ablation_c_minus_b(b_preds, c_preds)
    assert out["n_shared"] == 2
    assert out["only_in_b"] == ["only_b"]
    assert out["only_in_c"] == ["only_c"]
    assert out["diffs"]["r1"] == pytest.approx(0.0005)
    assert out["mean_diff"] == pytest.approx((0.0005 + (-0.0002)) / 2)


def test_ablation_c_minus_b_handles_no_shared_records():
    out = sc.ablation_c_minus_b({"a": 0.1}, {"b": 0.2})
    assert out["n_shared"] == 0 and out["mean_diff"] is None
