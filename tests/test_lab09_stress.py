"""L09.4 / L09.5 — each stress must change the one thing it names and nothing else.

A stress that also changes something else is not a stress, it is a confound; a
stress that changes nothing is decoration. Both failure modes are checked.
"""

from __future__ import annotations

import numpy as np
import pytest

from crypto_regime_lab.experiments.evaluator import ACCOUNT
from crypto_regime_lab.experiments.stress import (StressError, ambiguity_profile,
                                                  label_permutation, missing_enrichment,
                                                  mislabelled_transitions, scaled_costs,
                                                  stale_feed, transitions_in)


def tape(states, namespace="ns0", start_hour=0):
    return [{"state_namespace": namespace, "state_id": int(s),
             "available_at": f"2024-01-{1 + (start_hour + i) // 6:02d} "
                             f"{((start_hour + i) % 6) * 4:02d}:00:00",
             "quality_status": "OK", "decision_eligible": True}
            for i, s in enumerate(states)]


def test_transitions_are_counted_within_a_namespace_only():
    rows = tape([0, 0, 1, 1], "ns0") + tape([2, 2, 0], "ns1", start_hour=4)
    assert transitions_in(rows) == [2, 6]      # 0->1 inside ns0, 2->0 inside ns1
    # the ns0 -> ns1 boundary at index 4 is a refit, not a market transition


def test_scaled_costs_restores_the_account_even_when_the_block_raises():
    before = dict(ACCOUNT)
    with pytest.raises(ValueError):
        with scaled_costs(2.0):
            assert ACCOUNT["taker_fee_rate"] == before["taker_fee_rate"] * 2
            assert ACCOUNT["slippage_bps"] == before["slippage_bps"] * 2
            raise ValueError("boom")
    assert ACCOUNT["taker_fee_rate"] == before["taker_fee_rate"]
    assert ACCOUNT["slippage_bps"] == before["slippage_bps"]


def test_scaled_costs_moves_both_components_not_only_the_fee():
    """Scaling only the fee understates the stress on a high-turnover arm.

    Slippage is charged per fill inside the price and the fee is charged on
    notional; a 2x "cost stress" that left slippage alone would be about 80% of
    the cost it claims to be at this account's configured rates.
    """
    base_fee, base_slip = ACCOUNT["taker_fee_rate"], ACCOUNT["slippage_bps"]
    with scaled_costs(1.5) as economics:
        assert ACCOUNT["taker_fee_rate"] == pytest.approx(base_fee * 1.5)
        assert ACCOUNT["slippage_bps"] == pytest.approx(base_slip * 1.5)
        assert economics["taker_fee_rate"] == pytest.approx(base_fee * 1.5)
        assert economics["slippage_bps"] == pytest.approx(base_slip * 1.5)
        assert economics["multiplier"] == 1.5
    assert (ACCOUNT["taker_fee_rate"], ACCOUNT["slippage_bps"]) == (base_fee, base_slip)


def test_a_cost_multiplier_must_be_positive():
    with pytest.raises(StressError):
        with scaled_costs(0.0):
            pass


def test_mislabelling_moves_transitions_without_inventing_states():
    rows = tape([0] * 20 + [1] * 20 + [2] * 20)
    stressed, fidelity = mislabelled_transitions(rows, fraction=1.0, shift=3, seed=5)
    assert fidelity["transitions"] == 2
    assert fidelity["moved"] >= 1
    assert fidelity["positions_that_differ"] >= 1
    assert {r["state_id"] for r in stressed} <= {0, 1, 2}
    assert len(stressed) == len(rows)
    assert transitions_in(stressed) != transitions_in(rows)


def test_mislabelling_a_tape_with_no_transition_says_so_instead_of_pretending():
    rows = tape([1] * 30)
    stressed, fidelity = mislabelled_transitions(rows, fraction=1.0, shift=3, seed=5)
    assert fidelity["transitions"] == 0
    assert "no within-namespace transition" in fidelity["reason"]
    assert [r["state_id"] for r in stressed] == [r["state_id"] for r in rows]


def test_mislabelling_rejects_a_fraction_outside_the_unit_interval():
    with pytest.raises(StressError):
        mislabelled_transitions(tape([0, 1] * 20), fraction=1.5, shift=2, seed=1)


def test_a_stale_feed_holds_a_value_and_keeps_the_tape_length():
    rows = tape(list(np.arange(120) % 3))
    stressed, fidelity = stale_feed(rows, stale_runs=3, run_observations=10, seed=9)
    assert len(stressed) == len(rows)
    assert fidelity["observations_frozen"] > 0
    assert fidelity["share_of_tape_frozen"] == pytest.approx(
        fidelity["observations_frozen"] / len(rows))
    assert any(r["quality_status"] == "STALE_FEED" for r in stressed)
    assert transitions_in(stressed) != transitions_in(rows)


def test_a_stale_feed_refuses_a_tape_too_short_to_carry_the_stretches():
    with pytest.raises(StressError):
        stale_feed(tape([0, 1] * 10), stale_runs=5, run_observations=20, seed=9)


def test_missing_enrichment_drops_rows_rather_than_zeroing_them():
    rows = tape(list(np.arange(200) % 3))
    stressed, fidelity = missing_enrichment(rows, outages=3, outage_observations=10, seed=4)
    assert fidelity["rows_after"] < fidelity["rows_before"]
    assert fidelity["rows_dropped"] == fidelity["rows_before"] - fidelity["rows_after"]
    # every surviving row is one of the originals, untouched
    originals = {(r["available_at"], r["state_id"]) for r in rows}
    assert all((r["available_at"], r["state_id"]) in originals for r in stressed)


def test_missing_enrichment_drops_contiguous_stretches_not_scattered_rows():
    """An outage is a stretch, and a scattered drop cannot move a refresh schedule.

    The first version removed a random 20% of observations independently. The
    resulting schedule came out IDENTICAL to the real one on every cutoff —
    removing scattered rows almost never moves where the first transition of a
    period falls — so the stress ran for an hour and could not have produced a
    different answer.
    """
    rows = tape(list(np.arange(300) % 3))
    stressed, fidelity = missing_enrichment(rows, outages=4, outage_observations=20, seed=7)
    assert fidelity["contiguous"] is True
    assert fidelity["outages"] == 4
    kept = {r["available_at"] for r in stressed}
    gone = [i for i, r in enumerate(rows) if r["available_at"] not in kept]
    # the dropped indices form a small number of runs, not 80 separate ones
    runs = 1 + sum(1 for a, b in zip(gone, gone[1:]) if b != a + 1)
    assert runs <= 4, f"the drops form {runs} separate runs; an outage is contiguous"
    assert len(gone) == fidelity["rows_dropped"]


def test_missing_enrichment_refuses_an_outage_it_cannot_fit():
    with pytest.raises(StressError):
        missing_enrichment(tape([0, 1] * 10), outages=5, outage_observations=20, seed=4)
    with pytest.raises(StressError):
        missing_enrichment(tape([0, 1] * 40), outages=0, outage_observations=5, seed=4)


def test_a_label_permutation_leaves_the_transition_positions_alone():
    """The control that must change nothing.

    If this one ever fails, something downstream is reading a state id as though
    the integer meant something across a refit.
    """
    rows = tape(list(np.arange(90) % 3), "ns0") + tape(list(np.arange(90) % 3), "ns1",
                                                       start_hour=90)
    stressed, fidelity = label_permutation(rows, seed=2)
    assert transitions_in(stressed) == transitions_in(rows)
    assert fidelity["transition_positions_unchanged"] is True
    assert fidelity["namespaces_permuted"] == 2


def test_a_label_permutation_actually_permutes_something():
    """A permutation that happened to be the identity would pass the test above."""
    rows = tape(list(np.arange(120) % 3))
    differing = 0
    for seed in range(8):
        stressed, _ = label_permutation(rows, seed=seed)
        differing += sum(1 for a, b in zip(rows, stressed)
                         if a["state_id"] != b["state_id"])
    assert differing > 0


def test_ambiguity_compares_against_development_rather_than_its_own_decile():
    record = {"namespaces": {"ns0": {"emissions": [
        {"second_best_gap": g, "quality_status": "OK"} for g in np.linspace(0.1, 1.0, 100)]}}}
    own = ambiguity_profile(record)
    assert own["observations"] == 100
    assert "share_below_development_p10" not in own
    # a tape whose gaps are all smaller than development's tenth percentile is
    # more ambiguous than the interval the design was built on, and says so
    compared = ambiguity_profile(record, reference_p10=0.95)
    assert compared["share_below_development_p10"] > 0.9
    assert compared["more_ambiguous_than_development"] is True
    assert ambiguity_profile(record, reference_p10=0.05)[
        "more_ambiguous_than_development"] is False


def test_ambiguity_on_a_tape_with_no_recorded_gap_reports_that():
    assert ambiguity_profile({"namespaces": {}})["status"] == "NO_GAP_RECORDED"


# ------------------------------------------------------------------ cost levels
def test_the_cost_panel_carries_the_registered_grid_and_the_declared_account():
    """AS_DECLARED is not a stress; it is the account the study registered.

    The lab hands the engine's round-trip `fee` parameter the registered ONE-WAY
    rate, so the engine charges half. Doubling the fee -- and only the fee, the
    slippage binding was measured correct -- reproduces the registered contract.
    A panel that stopped at 2x would show the right number by accident and for
    the wrong reason, and would move if either binding changed.
    """
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from run_lab09_stress import cost_levels

    levels = cost_levels([1.0, 1.5, 2.0])
    assert [name for name, _f, _s in levels] == ["1x", "1.5x", "2x", "AS_DECLARED"]
    by_name = {name: (fee, slip) for name, fee, slip in levels}
    assert by_name["1x"] == (1.0, 1.0)
    assert by_name["2x"] == (2.0, 2.0)
    assert by_name["AS_DECLARED"] == (2.0, 1.0), (
        "AS_DECLARED doubles the fee because the engine halves it, and leaves slippage alone "
        "because that binding was measured correct")


def test_the_declared_level_charges_the_rate_the_study_registered():
    """Tie the AS_DECLARED level to the registration, not to a literal."""
    import json
    import sys
    from pathlib import Path

    lab_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(lab_root / "scripts"))
    from run_lab09_stress import cost_levels

    registered = json.loads((lab_root / "configs" / "study_registration.json").read_text())
    one_way = registered["execution"]["fee_funding_slippage_config"]["taker_fee_rate"]
    fee_multiplier = dict((n, f) for n, f, _s in cost_levels([1.0]))["AS_DECLARED"]
    with scaled_costs(1.0, fee_multiplier=fee_multiplier, slippage_multiplier=1.0):
        # the engine halves whatever it is handed, so the charged one-way rate is half
        charged_one_way = ACCOUNT["taker_fee_rate"] / 2.0
    assert charged_one_way == pytest.approx(one_way)


# ------------------------------------------------------ the waiting history
def test_a_switch_that_waited_and_then_activated_still_says_what_it_waited_for():
    """L09.5.6 needs the REASON, and the reason is cleared on activation.

    `blocked_reason` answers "why is this switch blocked NOW", so a switch that
    waited 350 bars for an open campaign and then activated reports `None` — and
    a histogram of final reasons shows `{"none": 5}` beside 1,380 blocked bars.
    Technically true, exactly backwards, and it made the guide's "campaign not
    flat" clause unanswerable from the run's own data.
    """
    from crypto_regime_lab.integration.continuous_account import SwitchRecord

    record = SwitchRecord(activation_id="act-1", parameter_version="v2", requested_at_bar=10,
                          effective_at_bar=None, blocked_bars=0, blocked_reason="REQUESTED")
    for _ in range(3):
        record.wait("TRANSITION_BLOCKED_OPEN_CAMPAIGN")
    for _ in range(2):
        record.wait("WAITING_FOR_WARM_INDICATORS")
    assert record.blocked_bars == 5
    assert record.blocked_reason == "WAITING_FOR_WARM_INDICATORS"

    # it activates, which clears the CURRENT reason
    record.effective_at_bar = 15
    record.blocked_reason = None
    assert record.as_record()["blocked_reason"] is None
    # ...and the history survives
    assert record.as_record()["blocked_bars_by_reason"] == {
        "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 3, "WAITING_FOR_WARM_INDICATORS": 2}
    assert sum(record.as_record()["blocked_bars_by_reason"].values()) == record.blocked_bars


def test_the_arm_record_separates_waiting_for_a_campaign_from_waiting_to_warm_up():
    """Two different gates in guide 9.5, in order. Conflating them loses the order."""
    from crypto_regime_lab.experiments.factorial import ArmResult
    from crypto_regime_lab.integration.continuous_account import SwitchRecord

    import numpy as np
    import pandas as pd

    switches = []
    for index, reason in enumerate(("TRANSITION_BLOCKED_OPEN_CAMPAIGN",
                                    "WAITING_FOR_WARM_INDICATORS")):
        record = SwitchRecord(activation_id=f"act-{index}", parameter_version=f"v{index}",
                              requested_at_bar=index, effective_at_bar=index + 5,
                              blocked_bars=0, blocked_reason=None)
        for _ in range(4):
            record.wait(reason)
        record.blocked_reason = None
        switches.append(record)

    index = pd.date_range("2024-01-01", periods=40, freq="1h", tz="UTC")
    result = ArmResult("D", "A-SC", "BTCUSDT", "RUN",
                       equity=np.linspace(20000.0, 20100.0, 40), index=index,
                       fills=[], entries=0, switches=switches)
    delays = result.as_record()["switch_delays"]
    assert delays["blocked_bars_total"] == 8
    assert delays["switches_that_waited_for_an_open_campaign"] == 1
    assert delays["switches_that_waited_for_warm_indicators"] == 1
    assert delays["final_reason_counts"] == {"none": 2}
    assert "did not wait" not in delays["final_reason_note"]
    assert delays["blocked_bars_by_reason"] == {
        "TRANSITION_BLOCKED_OPEN_CAMPAIGN": 4, "WAITING_FOR_WARM_INDICATORS": 4}
