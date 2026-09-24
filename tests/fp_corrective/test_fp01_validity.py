"""FP01-T01..T07: guide §13 FP01.4 validity tests on the real behavior, real path.

Each test below exercises the actual code it guards -- no mocks of the function
under test -- and carries a red control (the old/legacy behavior must fail the
same assertion, or a deliberately mutated input must move the output), so a
"test that passed because nothing happened" cannot carry a gate.
"""
from __future__ import annotations

import pytest

from crypto_regime_lab.experiments.time_edge_contracts import daily_returns
from crypto_regime_lab.fp import availability, chronology, claim_logic, decay_bounds
from crypto_regime_lab.fp.chronology import chronological_split


def _emission(day: int, hour: int = 0, month: int = 1) -> dict:
    return {"timestamp": f"2021-{month:02d}-{day:02d}T{hour:02d}:00:00+00:00",
            "state": "JM_BULL", "available_at": f"2021-{month:02d}-{day:02d}T{hour:02d}:00:00+00:00"}


def test_fp01_t01_future_only_emissions_do_not_change_calibration():
    tape = [_emission(d) for d in (3, 10, 17, 24, 31)]
    start = "2021-02-01T00:00:00+00:00"
    before = availability.window_dwell_profile(tape, evaluation_start=start)
    mutated = [_emission(d) for d in (3, 10, 17, 24, 31)]
    mutated += [_emission(d, 6, month=2) for d in (3, 10, 17)]  # future-only Feb additions
    mutated[0] = dict(mutated[0], state="JM_BEAR", available_at=mutated[0]["available_at"])
    after = availability.window_dwell_profile(mutated, evaluation_start=start)
    for field in ("n_events", "first_event", "last_event", "mean_gap_days", "rate_per_day"):
        assert after[field] == before[field], (
            f"future-only mutations moved calibration field {field}")
    assert after["n_events"] == 5 and after["n_excluded_tail"] == 3
    # Non-vacuous red control: move ONE prefix event and the profile must shift.
    shifted = [_emission(d) for d in (4, 10, 17, 24, 31)]
    moved = availability.window_dwell_profile(shifted, evaluation_start=start)
    assert moved != before, "the profile would be constant regardless of prefix input"
    assert moved["n_excluded_tail"] == 0
    with pytest.raises(availability.ChronologyViolation):
        availability.window_dwell_profile(tape, evaluation_start="2021-01-01T00:00:00+00:00")
    owned = availability.assert_available(
        [{"available_at": "2021-01-05T00:00:00+00:00"}], decision_time=start)
    assert owned["status"] == "ALL_AVAILABLE" and owned["n_checked"] == 1
    with pytest.raises(availability.ChronologyViolation):
        availability.assert_available(
            [{"available_at": "2021-02-01T00:00:00+00:00"}], decision_time=start)


def test_fp01_t03_boundary_keeps_exactly_two_returns_on_100_120_108():
    marks = [("2021-01-01T00:00:00Z", 100.0),
             ("2021-01-02T00:00:00Z", 120.0),
             ("2021-01-03T00:00:00Z", 108.0)]
    start, end = "2021-01-02T00:00:00Z", "2021-01-04T00:00:00Z"
    # The guide's canonical IS-side contract measures the first in-window mark
    # against the preceding mark: [(d2, 120/100-1), (d3, 108/120-1)].
    expected = daily_returns(
        [(d, v) for d, v in marks], initial_equity=100.0,
        start="2021-01-01T00:00:00Z", end=end)
    assert [r for _, r in expected[:2]] == pytest.approx([0.0, 0.2])
    repaired = decay_bounds.windowed_returns(marks, start=start, end=end)
    assert repaired["status"] == "OK", repaired
    assert repaired["return_values"] == pytest.approx([0.2, -0.1])
    assert repaired["prior_equity_source"] == "last_mark_strictly_before_window"
    # Red control: the legacy RA-07 convention fails the same assertion --
    # it reports exactly ONE return (the first is dropped).
    legacy = decay_bounds.legacy_first_return_dropped(marks, start=start, end=end)
    assert len(legacy["return_values"]) == 1, legacy
    # Reconciliation artifact on the same marks: +1 observation, stated delta.
    recon = decay_bounds.reconcile(marks, start=start, end=end)
    assert recon["observations_added"] == 1
    assert recon["mean_daily_return_delta"] == pytest.approx(0.05 - (-0.1))
    # Missing evidence stays missing: no prior mark -> explicit, not invented.
    missing = decay_bounds.windowed_returns(marks[1:], start=start, end=end)
    assert missing["status"] == "PRIOR_EQUITY_UNAVAILABLE" and missing["returns"] == []


def test_fp01_t04_warmup_outside_evaluation_does_not_grow_sample_count():
    # Marks 01-12..01-31 are warmup (before the window); 02-01..02-03 are the window.
    marks = [(f"2021-01-{d:02d}T00:00:00Z", 20000.0 + 10 * d) for d in range(12, 32)]
    marks += [(f"2021-02-{d:02d}T00:00:00Z", 21000.0 + 50 * d) for d in (1, 2, 3)]
    start, end = "2021-02-01T00:00:00Z", "2021-02-04T00:00:00Z"
    three_days = decay_bounds.windowed_returns(marks, start=start, end=end)
    assert three_days["status"] == "OK", three_days
    assert three_days["days"] == 3 and len(three_days["return_values"]) == 3
    # Red control: add MORE warmup marks before the window -- sample count and
    # every reported return must be unchanged.
    more_warmup = ([(f"2020-12-{d:02d}T00:00:00Z", 19000.0 + 5 * d)
                    for d in range(1, 32)] + marks)
    rerun = decay_bounds.windowed_returns(more_warmup, start=start, end=end)
    assert rerun["status"] == "OK", rerun
    assert rerun["days"] == 3 and rerun["return_values"] == pytest.approx(
        three_days["return_values"])
    # And the IS-side canonical contract agrees on the count.
    rows = daily_returns([(d, v) for d, v in more_warmup if d >= "2021-01-31T00:00:00Z"],
                         initial_equity=20960.0, start=start, end=end)
    assert len(rows) == 3


def test_fp01_t07_chronology_guard_refuses_future_labels():
    rows = [
        {"origin": "A", "origin_time": "2021-01-01T00:00:00+00:00", "label": 0.01,
         "label_available_at": "2021-02-15T00:00:00+00:00"},
        {"origin": "B", "origin_time": "2021-02-01T00:00:00+00:00", "label": -0.02,
         "label_available_at": "2021-03-15T00:00:00+00:00"},
        {"origin": "C", "origin_time": "2021-03-01T00:00:00+00:00", "label": 0.03,
         "label_available_at": "2021-04-15T00:00:00+00:00"},
    ]
    # A validation decision made at 2021-02-10 may train on A only: B's label
    # is a MARCH outcome (unavailable), C's an APRIL one. A's label is a
    # FEBRUARY-15 outcome -- unavailable at the 2021-02-10 decision too, so
    # the honest split is THREE blocked rows.
    split = chronology.chronological_split(rows, decision_time="2021-02-20T00:00:00+00:00")
    assert split["n_usable"] == 1 and split["usable"][0]["origin"] == "A"
    assert split["n_blocked"] == 2
    assert {row["row"]["origin"] for row in split["blocked"]} == {"B", "C"}
    late = chronology.chronological_split(rows, decision_time="2021-02-10T00:00:00+00:00")
    assert late["n_usable"] == 0 and late["n_blocked"] == 3, (
        "A's label is a 2021-02-15 outcome: a 2021-02-10 decision may not train on it")
    # Red control: the naive time-sorted LOO task over the SAME fixture leaks
    # B and C into training for a held-A validation decided at 2021-02-10 --
    # the guard catches both as exactly the future labels they are.
    naive = chronology.naive_time_sorted_loo_train(rows, held=0)
    leaked = chronological_split(naive, decision_time="2021-02-10T00:00:00+00:00")
    assert leaked["n_usable"] == 0 and leaked["n_blocked"] == 2, (
        "the naive LOO rows must BOTH fail the chronology guard against a "
        "2021-02-10 decision")
    # A row with no availability field cannot be proven available: refusal.
    with pytest.raises(chronology.ChronologyViolation):
        chronology.chronological_split(
            [{"origin": "X", "label": 0.5}], decision_time="2021-02-10T00:00:00+00:00")


def test_fp01_t06_identical_arms_give_no_false_significant_p_value():
    from crypto_regime_lab.ra.ra07_stats_primitives import (
        bootstrap_paired_delta, paired_daily_returns)
    days = [f"2021-02-{d:02d}T00:00:00+00:00" for d in range(1, 21)]
    equity = [[d, 20000.0 * (1 + 0.001 * (i % 5 - 2))] for i, d in enumerate(days)]
    rows = paired_daily_returns(equity, [list(row) for row in equity])
    assert len(rows) == 19 and all(row["diff"] == 0.0 for row in rows)
    out = bootstrap_paired_delta(rows, block_length=5, n_resamples=500, seed=20260922)
    assert out["status"] == "OK", out
    assert out["point_estimate"] == 0.0
    # A degenerate identical-arms resample cannot reach any significance level:
    # the p-value must be maximal and the CI must collapse on zero.
    assert out["p_value_two_sided"] == 1.0, (
        f"identical arms gave p={out['p_value_two_sided']}: a false significance")
    assert out["ci_95"] == [0.0, 0.0]


def test_fp01_claim_logic_band_alone_cannot_form_a_verdict():
    # FUP-05's failure shape: placebo inside/above a calendar band, NO direct
    # treatment-minus-comparator contrast -> unevaluable by construction.
    dead = claim_logic.timing_verdict(
        treatment_arm="M4_REGIME", direct_contrast=None,
        calendar_band={"worst": -0.000169, "placebo": -0.000031})
    assert dead["status"] == "NOT_EVALUABLE_DIRECT_CONTRAST_MISSING"
    assert dead["calendar_band_context"] is not None  # context kept, verdict refused
    # A direct contrast decides: treatment below -> artifact, above -> survived.
    below = claim_logic.timing_verdict(
        treatment_arm="M4_REGIME",
        direct_contrast={"comparator_arm": "PLACEBO_TIMING",
                         "delta": claim_logic.direct_pair_delta(0.0001, 0.0003),
                         "delta_sign": "treatment_below",
                         "uncertainty": {"method": "not_assessed_in_fp01"}})
    assert below["status"] == "CADENCE_ARTIFACT" and below["delta"] < 0
    above = claim_logic.timing_verdict(
        treatment_arm="M4_REGIME",
        direct_contrast={"comparator_arm": "M4_CAL_MATCHED",
                         "delta": claim_logic.direct_pair_delta(0.0003, 0.0001),
                         "delta_sign": "treatment_above",
                         "uncertainty": {"method": "not_assessed_in_fp01"}})
    assert above["status"] == "SURVIVED_FALSIFICATION" and above["delta"] > 0
    # Missing delta_sign is not inferred from the sign of delta: refusal.
    unsigned = claim_logic.timing_verdict(
        treatment_arm="M4_REGIME",
        direct_contrast={"comparator_arm": "M4_CAL_MATCHED", "delta": 0.0002})
    assert unsigned["status"] == "NOT_EVALUABLE_DIRECT_CONTRAST_MISSING"
    with pytest.raises(ValueError):
        claim_logic.direct_pair_delta(float("nan"), 0.0001)



