"""Coverage for sd/training_rows.py, including a full synthetic end-to-end
pipeline through the REAL reused fp.chronology/fp.forward_ledger guard and
into model_bc's fit functions (guide SD02.2/2.3, S2-T10-MATURITY-adjacent).
"""
from __future__ import annotations

import random

import pytest

from crypto_regime_lab.fp.forward_ledger import training_view
from crypto_regime_lab.selector.alpha_schemas import A_SC
from crypto_regime_lab.sd import jm_vintage as jv
from crypto_regime_lab.sd import model_bc as mbc
from crypto_regime_lab.sd import training_rows as tr


ANCHOR_PARAMS = {"coeff": 4, "AP": 20, "alpha.condition_threshold": 55,
                 "novolumedata": False, "src_col": "close"}


def _label_row(candidate_id, params, *, is_anchor, is_sharpe, fwd_sharpe, y_value):
    return {"candidate_id": candidate_id, "params": params, "is_anchor": is_anchor,
           "is_window": {"sharpe": is_sharpe, "sharpe_status": "OK"},
           "fwd_window": {"sharpe": fwd_sharpe, "sharpe_status": "OK"},
           "relative_decay_Y": {"value": y_value, "status": "OK"}}


def _synthetic_archive(origins, *, seed=0, n_candidates=6):
    rng = random.Random(seed)
    archive, descriptors = {}, {}
    for origin in origins:
        rows = [_label_row("anchor", ANCHOR_PARAMS, is_anchor=True, is_sharpe=1.0,
                           fwd_sharpe=0.8, y_value=0.0)]
        descs = [{"candidate_id": "anchor", "activity_entries": 20}]
        for i in range(n_candidates):
            params = {"coeff": rng.randint(1, 8), "AP": rng.randint(5, 60),
                      "alpha.condition_threshold": rng.choice([30, 40, 50, 60, 70, 80]),
                      "novolumedata": False, "src_col": "close"}
            y = rng.gauss(0, 0.3)
            rows.append(_label_row(f"c{i}", params, is_anchor=False,
                                   is_sharpe=1.0 + rng.gauss(0, 0.2),
                                   fwd_sharpe=0.8 + rng.gauss(0, 0.2), y_value=y))
            descs.append({"candidate_id": f"c{i}", "activity_entries": rng.randint(5, 40)})
        archive[origin] = {"origin_cutoff": origin, "label_rows": rows}
        descriptors[origin] = descs
    return archive, descriptors


def _synthetic_tape(origins, *, all_ok=True):
    tape = {}
    for i, origin in enumerate(origins):
        if all_ok:
            tape[origin] = jv.VintageOriginRecord(origin_cutoff=origin, recipe_c=1.0, status="OK",
                                                  state=i % 2, lambda_j=1.0, loss_scale=1.0,
                                                  n_iter=5, converged=True, reason=None)
        else:
            tape[origin] = jv.VintageOriginRecord(origin_cutoff=origin, recipe_c=1.0,
                                                  status=jv.STATUS_INSUFFICIENT_PREHISTORY,
                                                  state=None, lambda_j=None, loss_scale=None,
                                                  n_iter=None, converged=None, reason="test")
    return tape


ORIGINS_12 = [f"2022-{m:02d}-01" for m in range(1, 13)]


def test_chronology_records_skips_undefined_labels():
    archive, descriptors = _synthetic_archive(["2022-01-01"], n_candidates=2)
    archive["2022-01-01"]["label_rows"].append(
        {"candidate_id": "bad", "params": ANCHOR_PARAMS, "is_anchor": False,
        "is_window": {"sharpe": None, "sharpe_status": "TOO_FEW_OBSERVATIONS"},
        "relative_decay_Y": {"value": None, "status": "UNDEFINED_INPUT"}})
    descriptors["2022-01-01"].append({"candidate_id": "bad", "activity_entries": 1})
    records = tr.chronology_records(archive, descriptors, A_SC)
    assert all(r["record_id"] != "2022-01-01|bad" for r in records)
    assert len(records) == 3   # anchor + 2 candidates, bad one skipped


def test_label_available_at_is_56_days_after_origin():
    got = tr.label_available_at("2022-01-01")
    assert got.startswith("2022-02-26")   # 2022-01-01 + 56 days


def test_attach_states_none_for_non_ok_tape():
    archive, descriptors = _synthetic_archive(["2022-01-01"], n_candidates=2)
    records = tr.chronology_records(archive, descriptors, A_SC)
    tape = _synthetic_tape(["2022-01-01"], all_ok=False)
    tagged = tr.attach_states(records, tape)
    assert all(r["state"] is None for r in tagged)


def test_model_c_rows_excludes_unknown_state_records():
    archive, descriptors = _synthetic_archive(["2022-01-01", "2022-02-01"], n_candidates=2)
    records = tr.chronology_records(archive, descriptors, A_SC)
    tape = {"2022-01-01": jv.VintageOriginRecord(origin_cutoff="2022-01-01", recipe_c=1.0,
                                                 status="OK", state=0, lambda_j=1.0, loss_scale=1.0,
                                                 n_iter=1, converged=True, reason=None),
           "2022-02-01": jv.VintageOriginRecord(origin_cutoff="2022-02-01", recipe_c=1.0,
                                                status=jv.STATUS_INSUFFICIENT_PREHISTORY, state=None,
                                                lambda_j=None, loss_scale=None, n_iter=None,
                                                converged=None, reason="test")}
    tagged = tr.attach_states(records, tape)
    b_rows = tr.model_b_rows(tagged)
    c_rows = tr.model_c_rows(tagged)
    assert len(b_rows) == len(tagged)   # B keeps everything
    assert all(r["origin_id"] == "2022-01-01" for r in c_rows)   # C only the known-state origin


def test_full_synthetic_pipeline_through_real_chronology_guard_and_model_fit():
    """End-to-end: 12 synthetic origins -> chronology records -> states ->
    REAL fp.forward_ledger.training_view (reused verbatim) -> model_b/c fit.
    A later origin's own label must never appear in an earlier fold's
    training set."""
    archive, descriptors = _synthetic_archive(ORIGINS_12, seed=5, n_candidates=6)
    records = tr.chronology_records(archive, descriptors, A_SC)
    tape = _synthetic_tape(ORIGINS_12, all_ok=True)
    tagged = tr.attach_states(records, tape)

    # decision_time set AFTER every origin's own label has matured (56 days
    # past the last origin) -- everything should be usable
    decision_time = "2023-06-01T00:00:00+00:00"
    view = training_view(tagged, decision_time=decision_time)
    assert view["n_usable"] == len(tagged)
    assert view["n_blocked"] == 0

    b_rows = tr.model_b_rows(view["usable"])
    c_rows = tr.model_c_rows(view["usable"])
    fit_b = mbc.fit_model_b(b_rows)
    fit_c = mbc.fit_model_c(fit_b, c_rows)
    assert fit_b.n_train_origins == 12
    assert set(fit_c.state_support_counts) <= {0, 1}


def test_retag_states_generic_mapping_used_by_jm_and_r_rule_alike():
    archive, descriptors = _synthetic_archive(["2022-01-01", "2022-02-01"], n_candidates=2)
    records = tr.chronology_records(archive, descriptors, A_SC)
    retagged = tr.retag_states(records, {"2022-01-01": 0, "2022-02-01": None})
    assert all(r["state"] == 0 for r in retagged if r["origin_cutoff"] == "2022-01-01")
    assert all(r["state"] is None for r in retagged if r["origin_cutoff"] == "2022-02-01")


def test_retag_states_raises_on_missing_origin_mapping():
    archive, descriptors = _synthetic_archive(["2022-01-01"], n_candidates=1)
    records = tr.chronology_records(archive, descriptors, A_SC)
    with pytest.raises(tr.TrainingRowsError):
        tr.retag_states(records, {})


def test_early_decision_time_blocks_future_labels():
    archive, descriptors = _synthetic_archive(ORIGINS_12, seed=6, n_candidates=4)
    records = tr.chronology_records(archive, descriptors, A_SC)
    tape = _synthetic_tape(ORIGINS_12, all_ok=True)
    tagged = tr.attach_states(records, tape)
    # decision_time between origin 1's maturity (2022-01-01 + 56d = 2022-02-26)
    # and origin 2's maturity (2022-02-01 + 56d = 2022-03-29) -- only origin
    # 1's label should be usable
    view = training_view(tagged, decision_time="2022-03-01T00:00:00+00:00")
    usable_origins = {r["origin_cutoff"] for r in view["usable"]}
    assert usable_origins == {"2022-01-01"}
    assert view["n_blocked"] > 0
