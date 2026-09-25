"""SD02.6 learning-to-action verification (guide SS9.4 S2-T07-INDEPENDENT-C,
S2-T08-SHRINK-FALLBACK): proves the ACTUAL selection pipeline (fold_scoring +
model_bc composed together, the same composition scripts/run_sd02_validation.py
uses) exhibits the guide's required structural properties, not just each
piece in isolation.
"""
from __future__ import annotations

import random

from crypto_regime_lab.sd import fold_scoring as fsc
from crypto_regime_lab.sd import model_bc as mbc


ANCHOR_FEATURES = {"f1": 0.0, "f2": 0.0}


def _rows(n_origins, *, seed=0, force_anchor_wins=False):
    """Synthetic training rows where every candidate's true label is a
    modest constant BELOW the guard margin, so B's own minY selection
    genuinely falls back to the anchor (a real, not contrived, B-anchor
    outcome) when force_anchor_wins=True."""
    rng = random.Random(seed)
    rows = []
    for o in range(n_origins):
        origin_id = f"o{o:03d}"
        rows.append({"origin_id": origin_id, "candidate_features": dict(ANCHOR_FEATURES),
                    "anchor_features": dict(ANCHOR_FEATURES), "y": 0.0, "state": o % 2})
        for c in range(4):
            f1, f2 = rng.gauss(0, 1), rng.gauss(0, 1)
            y = 5.0 if force_anchor_wins else (0.4 * f1 - 0.2 * f2 + rng.gauss(0, 0.02))
            rows.append({"origin_id": origin_id, "candidate_features": {"f1": f1, "f2": f2},
                        "anchor_features": dict(ANCHOR_FEATURES), "y": y, "state": o % 2})
    return rows


def _panel_from_rows(fold_rows, *, anchor_id="anchor"):
    out = [{"candidate_id": anchor_id, "params": {}, "features": ANCHOR_FEATURES,
           "sr_is": 1.0, "is_anchor": True}]
    for i, r in enumerate(fold_rows):
        out.append({"candidate_id": f"c{i}", "params": {}, "features": r["candidate_features"],
                   "sr_is": 1.0, "is_anchor": False})
    return out


def test_c_is_scored_even_when_b_falls_back_to_the_anchor():
    """S2-T07-INDEPENDENT-C: a genuine B-anchor outcome (every real
    candidate fails the Q_hat guard) must not prevent C from being
    fit/scored -- C has no dependency on B's own selection RESULT, only on
    B's fitted prediction FUNCTION."""
    train_rows = _rows(15, seed=1, force_anchor_wins=True)
    fit_b = mbc.fit_model_b(train_rows)

    # Verify B genuinely falls back to the anchor on a fresh panel (a real
    # B-anchor outcome, not assumed)
    panel = _panel_from_rows([{"candidate_features": {"f1": rv, "f2": -rv}} for rv in (0.1, 0.2, 0.3)])
    b_result = fsc.score_pool(
        lambda row, anchor: mbc.predict_b(fit_b, row["features"], anchor["features"]),
        panel, anchor_id="anchor")
    assert b_result["selection"]["is_anchor"] is True, "test setup must produce a genuine B-anchor outcome"

    # C must STILL be fit and scored -- no branch anywhere checks b_result first
    fit_c = mbc.fit_model_c(fit_b, train_rows)
    c_result = fsc.score_pool(
        lambda row, anchor: mbc.predict_c(fit_c, row["features"], anchor["features"], state=0)["y_hat"],
        panel, anchor_id="anchor")
    assert c_result is not None
    assert c_result["selection"]["decision"] == "CANDIDATE_SELECTED"
    assert len(c_result["scored"]) == len(panel)


def test_shared_technical_failure_has_a_reason_not_a_silent_skip():
    """The ONLY thing that can legitimately prevent C from scoring is a
    genuinely shared technical failure (e.g. B itself never cleared its own
    origin-count floor) -- and that failure carries a typed reason, never a
    silent empty result."""
    too_few_rows = _rows(5, seed=2)   # below MIN_GLOBAL_TRAIN_ORIGINS=12
    try:
        mbc.fit_model_b(too_few_rows)
        raised = False
    except mbc.ModelError as exc:
        raised = True
        assert "12" in str(exc) or "origins" in str(exc)
    assert raised, "an insufficient-origin B fit must raise a typed, informative error"


def test_low_state_support_correction_is_zero_not_a_fabricated_value():
    """S2-T08-SHRINK-FALLBACK: a state with < MIN_STATE_TRAIN_ORIGINS gets
    NO fitted correction (falls back to B's own prediction exactly), never
    an unstable near-zero-support fit."""
    rows = _rows(12, seed=3)
    for i, row in enumerate(rows):
        row["state"] = 1 if row["origin_id"] in ("o000", "o001") else 0   # state 1: only 2 origins
    fit_b = mbc.fit_model_b(rows)
    fit_c = mbc.fit_model_c(fit_b, rows)
    assert 1 not in fit_c.state_ridge_fits
    sample = next(r for r in rows if r["state"] == 1)
    result = mbc.predict_c(fit_c, sample["candidate_features"], sample["anchor_features"], state=1)
    assert result["correction"] == 0.0
    assert result["y_hat"] == result["y_hat_b"]
    assert result["label"] == "GLOBAL_FALLBACK"


def test_unknown_state_falls_back_to_global_never_a_hard_box_rejection():
    """No hard min/max one-point OOD box exists -- an unrecognised state
    value still gets a real B-based prediction, just with correction=0."""
    rows = _rows(12, seed=4)
    fit_b = mbc.fit_model_b(rows)
    fit_c = mbc.fit_model_c(fit_b, rows)
    sample = rows[0]
    result = mbc.predict_c(fit_c, sample["candidate_features"], sample["anchor_features"],
                           state="totally_novel_state_value_999")
    assert result["label"] == "GLOBAL_FALLBACK"
    assert result["reason"] == "UNKNOWN_STATE"
    assert result["y_hat"] == mbc.predict_b(fit_b, sample["candidate_features"], sample["anchor_features"])
