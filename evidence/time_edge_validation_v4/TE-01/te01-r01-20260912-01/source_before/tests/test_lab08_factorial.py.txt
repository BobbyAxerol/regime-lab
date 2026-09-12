"""LAB-08 — the controlled discovery factorial, its controls, and its comparability."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from crypto_regime_lab.experiments.calendar_baseline import CALENDAR
from crypto_regime_lab.experiments.controls import (
    CONTROLS,
    ControlError,
    delayed_states,
    dwell_profile,
    expost_labels,
    placebo_fidelity,
    placebo_states,
    risk_only_scaler,
)
from crypto_regime_lab.experiments.factorial import (
    ARM_DEFINITION,
    ARMS,
    ArmResult,
    paired_daily_difference,
)
from crypto_regime_lab.experiments.regime_schedule import (
    RegimeSchedule,
    assert_compute_matched,
    transition_cutoffs,
)


def _emissions(n=900, start="2021-01-01", freq="4h", seed=3, dwell=40):
    rng = np.random.default_rng(seed)
    times = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    states, current = [], 0
    for _ in range(n):
        if rng.random() < 1.0 / dwell:
            current = int(rng.integers(0, 3))
        states.append(current)
    return [{"state_namespace": "jm@test", "state_id": s,
             "observed_at": str(t - pd.Timedelta(freq)), "available_at": str(t)}
            for s, t in zip(states, times)]


# --- the dynamic arms must not buy an advantage with extra searches -------


def test_the_dynamic_arm_gets_exactly_the_calendars_refresh_count():
    """Guide 10.5: the new method may not be given more chances to look.

    An arm that refits on every state change would refresh far more often than
    the calendar's six, and any edge it showed would be confounded with having
    been allowed more searches.
    """
    # three years of 4h emissions, as the real development window has
    schedule = transition_cutoffs(_emissions(n=6570), count=CALENDAR.folds,
                                  earliest="2021-01-01", latest="2023-12-31")
    assert schedule.folds == CALENDAR.folds
    match = assert_compute_matched(CALENDAR, schedule)
    assert match["matched"] is True
    assert match["calendar_refreshes"] == match["dynamic_refreshes"]
    assert match["calendar_train_days"] == match["dynamic_train_days"]


def test_triggers_are_taken_in_time_order_not_by_size():
    """"The biggest transitions" is a quantity only the future knows."""
    import inspect

    source = inspect.getsource(transition_cutoffs)
    assert "never \"biggest\"" in source or "only the future knows" in source
    schedule = transition_cutoffs(_emissions(n=6570), count=4,
                                  earliest="2021-01-01", latest="2023-12-31")
    moments = [pd.Timestamp(c) for c in schedule.cutoffs]
    assert moments == sorted(moments)


def test_triggers_respect_a_minimum_gap():
    schedule = transition_cutoffs(_emissions(n=6570, dwell=8, seed=11), count=5,
                                  earliest="2021-01-01", latest="2023-12-31",
                                  min_gap_days=30.0)
    moments = [pd.Timestamp(c) for c in schedule.cutoffs]
    for previous, current in zip(moments, moments[1:]):
        assert (current - previous) >= pd.Timedelta(days=30)


def test_a_schedule_that_cannot_be_filled_is_refused():
    """A dynamic arm with fewer refreshes is not compute-matched."""
    # RF-03/A10 superseded the raising contract: a schedule that cannot be
    # filled returns fewer cutoffs. It is never padded back to the calendar.
    schedule = transition_cutoffs(_emissions(n=40), count=6, earliest="2021-01-01",
                                  latest="2021-01-05", min_gap_days=30.0)
    assert len(schedule.cutoffs) < 6 and "periods had no eligible transition" in schedule.source


def test_a_trigger_sits_at_availability_not_at_the_bar_it_describes():
    emissions = _emissions(n=6570)
    schedule = transition_cutoffs(emissions, count=3, earliest="2021-01-01",
                                  latest="2023-12-31")
    by_available = {pd.Timestamp(e["available_at"]): e for e in emissions}
    for cutoff in schedule.cutoffs:
        moment = pd.Timestamp(cutoff)
        assert moment in by_available, "a trigger must sit on a time a state was AVAILABLE"
        emission = by_available[moment]
        # in a contiguous tape every available_at is also the NEXT bar's
        # observed_at, so the property is per-emission: the trigger is that
        # emission's availability, strictly after the bar it describes
        assert pd.Timestamp(emission["available_at"]) > pd.Timestamp(emission["observed_at"]), (
            "the bar a state describes is not the time it could be acted on; LAB-07 found a "
            "version of this published fifteen times too early")


# --- the controls ---------------------------------------------------------


def test_all_seven_mandatory_controls_are_declared():
    assert set(CONTROLS) == {
        "RISK_ONLY", "CALENDAR_MATCHED", "BANK_CALENDAR", "STATE_PLACEBO",
        "DELAYED_STATE", "EXPOST_DIAGNOSTIC", "USER_PRESET_REFERENCE"}
    for control, explains in CONTROLS.items():
        assert explains, f"{control} does not say what it rules out"


def test_the_placebo_matches_the_real_dwell_rather_than_switching_freely():
    """A placebo that switches constantly loses on costs alone.

    Beating a strawman would look like evidence for the states while being
    evidence only that random switching is expensive.
    """
    real = [e["state_id"] for e in _emissions(n=1200, dwell=40)]
    profile = dwell_profile(real)
    fake = placebo_states(profile, length=len(real), seed=20260911)
    fidelity = placebo_fidelity(real, fake)
    assert fidelity["matched"] is True
    assert 0.6 <= fidelity["switch_rate_ratio"] <= 1.4


def test_a_free_running_placebo_is_detected_as_unmatched():
    """The fidelity check must be able to FAIL, or it certifies any placebo."""
    real = [e["state_id"] for e in _emissions(n=1200, dwell=40)]
    rng = np.random.default_rng(1)
    strawman = list(rng.integers(0, 3, len(real)))
    fidelity = placebo_fidelity(real, strawman)
    assert fidelity["matched"] is False
    assert fidelity["switch_rate_ratio"] > 5


def test_the_placebo_is_built_from_rates_not_from_a_future_sequence():
    """Two placebos from the same profile differ; both match its statistics."""
    real = [e["state_id"] for e in _emissions(n=2000, dwell=30, seed=23)]
    profile = dwell_profile(real)
    placebos = [placebo_states(profile, length=len(real), seed=seed) for seed in (1, 2, 3, 4, 5)]
    assert len({tuple(p) for p in placebos}) == len(placebos), (
        "a placebo that reproduces one sequence IS that sequence")
    matched = [placebo_fidelity(real, fake)["matched"] for fake in placebos]
    assert sum(matched) >= 4, (
        f"only {sum(matched)}/5 placebos matched the real switch rate: the generator reproduces "
        "a rate, so most draws must land inside the tolerance")


def test_the_delay_control_moves_availability_not_the_world():
    emissions = _emissions(n=400, dwell=8, seed=17)   # dense enough to contain switches
    delayed = delayed_states(emissions, observations=1)
    assert len(delayed) == len(emissions)
    assert all(d["delay_is_on_availability_not_on_the_world"] for d in delayed)
    assert [d["observed_at"] for d in delayed] == [e["observed_at"] for e in emissions]
    assert any(d["state_id"] != e["state_id"] for d, e in zip(delayed, emissions))
    with pytest.raises(ControlError, match="not a delay"):
        delayed_states(emissions, observations=0)


def test_the_hindsight_control_is_never_tradeable():
    states = [0, 1, 1, 2, 0]
    verdict = expost_labels(states, horizon_returns=[0.01, -0.02, 0.03, 0.00, 0.01])
    assert verdict["eligible_for_a_trade_result"] is False
    assert "had not happened at decision time" in verdict["rule"]


def test_risk_only_never_levers_above_the_baseline():
    """The control must not beat the method by sizing up on unshared information."""
    rng = np.random.default_rng(5)
    train_states = list(rng.integers(0, 3, 400))
    train_returns = list(rng.normal(0, 0.01, 400))
    scales = risk_only_scaler(list(rng.integers(0, 3, 200)),
                              train_states=train_states, train_returns=train_returns)
    assert all(0.5 <= s <= 1.0 for s in scales)


def test_an_unseen_state_gets_no_extrapolated_size():
    scales = risk_only_scaler([99], train_states=[0, 0, 1], train_returns=[0.01, -0.01, 0.02])
    assert scales == [1.0], "a state never seen in training must not be sized on a guess"


# --- arm comparability ----------------------------------------------------


def test_the_five_arms_differ_only_in_selector_and_timing():
    assert set(ARMS) == {"A", "B", "C", "D", "E"}
    selectors = {arm: ARM_DEFINITION[arm][0] for arm in ARMS}
    schedules = {arm: ARM_DEFINITION[arm][1] for arm in ARMS}
    assert selectors["A"] == selectors["C"], "A and C must share a selector; only timing differs"
    assert selectors["B"] == selectors["D"], "B and D must share a selector; only timing differs"
    assert schedules["A"] == schedules["B"] == "calendar"
    assert schedules["C"] == schedules["D"] == "regime"


def test_a_contrast_is_taken_on_shared_dates_only():
    index = pd.date_range("2021-01-01", periods=40, freq="1D", tz="UTC")
    left = ArmResult("B", "A-SC", "BTCUSDT", "RUN",
                     equity=np.linspace(20000, 21000, 40), index=index)
    right = ArmResult("A", "A-SC", "BTCUSDT", "RUN",
                      equity=np.linspace(20000, 20500, 40), index=index[:40])
    contrast = paired_daily_difference(left, right)
    assert contrast["status"] == "OK"
    assert contrast["shared_days"] > 0
    assert "same dates only" in contrast["pairing"]


def test_an_unrunnable_arm_reports_null_not_zero():
    """Guide 13.2: a blocked cell booked as PnL 0 biases every aggregate."""
    blocked = ArmResult("C", "A-HASH", "BTCUSDT", "NOT_READY",
                        detail={"reason": "ladder fidelity blocker"})
    record = blocked.as_record()
    assert record["net_return"] is None
    assert record["trades"] is None
    assert "never booked as a PnL of 0" in record["note"]
    contrast = paired_daily_difference(blocked, blocked)
    assert contrast["status"] == "INCOMPARABLE"
    assert contrast["mean_daily_difference"] is None


def test_a_schedule_record_states_the_matching_rule():
    schedule = RegimeSchedule(cutoffs=("2021-01-01T00:00:00+00:00",))
    record = schedule.as_record()
    assert "never how many" in record["matched_rule"]


# --- artifacts ------------------------------------------------------------


@pytest.fixture(scope="module")
def protocol(lab_root):
    path = lab_root / "configs" / "lab08_pilot_protocol.json"
    if not path.is_file():
        pytest.skip("run scripts/freeze_lab08_protocol.py")
    return json.loads(path.read_text())


def test_the_protocol_was_frozen_before_any_arm_ran(lab_root, protocol):
    """L08.1: a protocol that can be rewritten after a result is not frozen."""
    frozen = pd.Timestamp(protocol["frozen_at_utc"])
    for name in ("lab08_factorial_full.json", "lab08_factorial_pilot.json"):
        path = lab_root / "configs" / name
        if not path.is_file():
            continue
        run = json.loads(path.read_text())
        assert pd.Timestamp(run["protocol_frozen_at_utc"]) == frozen
        assert pd.Timestamp(run["generated_at_utc"]) > frozen, (
            f"{name} claims to predate the protocol it ran under")


def test_the_protocol_covers_all_twenty_cells_including_the_blocked_ones(protocol):
    matrix = protocol["primary_matrix"]
    assert matrix["total"] == 20
    assert matrix["not_runnable"] > 0, "A-HASH's blocker must still be visible"
    assert matrix["runnable"] + matrix["not_runnable"] == 20
    for cell in matrix["cells"]:
        if not cell["runnable"]:
            assert cell["blocker"], f"{cell['alpha_id']} is not runnable with no blocker recorded"


def test_the_protocol_registers_every_contrast_and_control(protocol):
    assert protocol["registered_contrasts"] == ["B-A", "C-A", "D-B", "D-C", "(D-C)-(B-A)"]
    assert set(protocol["controls"]) == set(CONTROLS)
    assert protocol["stage"] == "discovery"
    assert protocol["outer_window_is_not_consumed"] is True
    assert set(protocol["exit_options"]) == {"DESIGN_FROZEN", "NO_PROMISING_DESIGN"}


def test_regime_triggers_spread_across_the_window_not_the_front():
    """Taking the first N transitions concentrates every refresh in the opening months.

    The pilot showed both failure modes: a tape covering only the last six
    months put every trigger there, and a greedy walk from the front put every
    trigger in the first six. Either way the arm holds its initial parameters for
    years and the contrast measures coverage, not timing.
    """
    schedule = transition_cutoffs(_emissions(n=6570), count=6,
                                  earliest="2021-01-01", latest="2023-12-31")
    moments = [pd.Timestamp(c) for c in schedule.cutoffs]
    span = pd.Timestamp("2023-12-31", tz="UTC") - pd.Timestamp("2021-01-01", tz="UTC")
    period = span / 6
    for index, moment in enumerate(moments):
        lower = pd.Timestamp("2021-01-01", tz="UTC") + period * index
        upper = pd.Timestamp("2021-01-01", tz="UTC") + period * (index + 1)
        assert lower <= moment < upper, (
            f"trigger {index} at {moment} is outside its own period; the refreshes are "
            "concentrating instead of spreading")
    assert (moments[-1] - moments[0]) > span * 0.6, (
        "the triggers cover less than 60% of the window")


def test_a_period_with_no_transition_refuses_rather_than_pads():
    flat = [{"state_namespace": "jm@test", "state_id": 0,
             "observed_at": str(t - pd.Timedelta("4h")), "available_at": str(t)}
            for t in pd.date_range("2021-01-01", periods=6570, freq="4h", tz="UTC")]
    # RF-03/A10: no eligible transition means no refresh, not a padded count.
    schedule = transition_cutoffs(flat, count=6, earliest="2021-01-01", latest="2023-12-31")
    assert schedule.cutoffs == () and "6 periods had no eligible transition" in schedule.source


def test_arm_a_carries_the_legacy_label_it_earned(lab_root):
    """T54 — the baseline is the installed public route, and that route declares OOS selection.

    LAB-04 read the engine's own metadata: `optimization_mode='none'`, the public
    default and therefore arm A, is among the modes declaring OOS-adjusted
    selection. Every contrast in this phase is measured against that arm, so
    calling any of them out-of-sample is exactly the claim guide 13.6 forbids.
    """
    path = lab_root / "configs" / "lab08_discovery.json"
    if not path.is_file():
        pytest.skip("run scripts/analyse_lab08_discovery.py")
    label = json.loads(path.read_text())["legacy_arm_label"]
    trace = json.loads((lab_root / "configs" / "lab04_installed_wfo_trace.json").read_text())
    declared = trace["legacy_oos_labelling"]["modes_declaring_oos_selection"]

    assert label["public_route_mode"] == trace["public_route_default"]["optimization_mode"]
    assert label["mode_declares_oos_selection"] == (label["public_route_mode"] in declared)
    if label["mode_declares_oos_selection"]:
        assert label["label"] == "A_legacy_selection_adjusted"
        assert label["may_be_reported_as_an_untouched_baseline"] is False
    assert label["authoritative_source"], "the label must name where the declaration came from"


def test_arm_e_is_reported_separately_and_cannot_freeze_a_design(lab_root):
    """Guide 10.1: E is an extension compared against B, never a substitute for C or D."""
    path = lab_root / "configs" / "lab08_discovery.json"
    if not path.is_file():
        pytest.skip("run scripts/analyse_lab08_discovery.py")
    discovery = json.loads(path.read_text())
    assert "E-B" in discovery["contrast_panel"], "E must be compared against B"
    eligible = {c["contrast"] for c in discovery["design_selection"]["candidates"]}
    assert "E-B" not in eligible, (
        "E-B is in the design-selection candidates: freezing on it would be using the extension "
        "in place of a core arm")
    assert eligible <= {"B-A", "C-A", "D-B", "D-C"}


def test_a_selector_that_never_selects_is_a_result_not_a_crash():
    """A-SC/BNBUSDT: arm B's quality gate rejected every candidate at all six cutoffs.

    An earlier version raised there and took a nine-cell run down with it, turning
    a reportable finding — the robustness selector declining on this cell — into a
    failed run.
    """
    from crypto_regime_lab.experiments.factorial import _schedule_from_selections

    frame = pd.DataFrame({"close": [1.0] * 50},
                         index=pd.date_range("2021-01-01", periods=50, freq="1D", tz="UTC"))
    nothing = [{"cutoff": "2021-01-05", "params": None},
               {"cutoff": "2021-01-20", "params": None}]
    seed = {"AP": 20, "alpha.condition_threshold": 50, "coeff": 3,
            "novolumedata": False, "src_col": "close"}
    initial, schedule, retained = _schedule_from_selections(
        nothing, frame, "A-SC", seed_params=seed)
    assert retained is True
    assert schedule == [], "a retained incumbent has no later activation"
    assert initial.params == seed
    assert initial.activation_id == "act-incumbent-retained"

    from crypto_regime_lab.experiments.factorial import FactorialError
    with pytest.raises(FactorialError, match="nothing to deploy"):
        _schedule_from_selections(nothing, frame, "A-SC", seed_params=None)


def test_the_run_checkpoints_each_cell(lab_root):
    """A crash at cell 10 cost nine cells and about two hours."""
    path = lab_root / "configs" / "lab08_factorial_full.json"
    if not path.is_file():
        pytest.skip("run scripts/run_lab08_factorial.py --stage full")
    document = json.loads(path.read_text())
    assert document.get("checkpointed") is True
    assert "costs one cell rather than the whole run" in document["checkpoint_note"]


def test_risk_only_is_blocked_rather_than_silently_returning_the_baseline(lab_root):
    """A control whose calibration cannot transfer is vacuous, not passing.

    RISK_ONLY fits a per-state scale on one window and applies it on a later
    one. The model refits every 28 days and LAB-05 declares cross-namespace
    state translation DIAGNOSTIC ONLY, so only ~1.75% of scoring observations
    carry a state key seen during calibration. The other 98% fell back to a
    scale of 1.0 — the control returned the baseline path while printing a
    number that looked like a result.
    """
    path = lab_root / "configs" / "lab08_factorial_full.json"
    if not path.is_file():
        pytest.skip("run scripts/run_lab08_factorial.py --stage full")
    cells = [c for c in json.loads(path.read_text())["cells"] if c["status"] == "RUN"]
    assert cells, "no cell ran, so this checks nothing"
    for cell in cells:
        record = (cell.get("controls") or {}).get("RISK_ONLY")
        if record is None or record.get("status") == "NOT_RUN":
            continue
        transfer = record.get("share_of_scoring_states_seen_in_calibration")
        assert transfer is not None, "the control must MEASURE how much calibration transfers"
        if record["status"] == "BLOCKED_BY_STATE_NAMESPACING":
            assert transfer < 0.5
            assert "never as a scale of 1.0" in record["not_dropped"]
            assert "net_return" not in record, (
                "a blocked control must not publish a return that is just the baseline")
        else:
            assert transfer >= 0.5, (
                f"{cell['alpha_id']}/{cell['symbol']}: RISK_ONLY ran with only {transfer:.2%} of "
                "its calibration transferring, so its scale is mostly the 1.0 fallback")


def test_arm_e_is_flagged_when_it_is_a_copy_of_arm_d(lab_root):
    """Five columns where there are four arms reads as five independent results."""
    path = lab_root / "configs" / "lab08_discovery.json"
    if not path.is_file():
        pytest.skip("run scripts/analyse_lab08_discovery.py")
    discovery = json.loads(path.read_text())
    arm_e = discovery["arm_e"]
    assert arm_e["cells_compared"] > 0, "nothing was compared, so this checks nothing"
    if arm_e["degenerate"]:
        assert arm_e["E_is_a_distinct_arm"] is False
        panel = discovery["contrast_panel"]
        assert panel["E-B"].get("equals_D_B_by_construction") is True
        assert panel["E-B"]["mean_daily_difference"] == panel["D-B"]["mean_daily_difference"], (
            "E is identical to D, so E-B must equal D-B; two different numbers mean two "
            "different statistics are in the same table")


def test_the_holm_family_is_exactly_the_registered_contrasts(lab_root):
    """E-B inside the family made it six and changed every adjusted p-value."""
    discovery_path = lab_root / "configs" / "lab08_discovery.json"
    protocol_path = lab_root / "configs" / "lab08_pilot_protocol.json"
    if not (discovery_path.is_file() and protocol_path.is_file()):
        pytest.skip("run the LAB-08 pipeline")
    holm = json.loads(discovery_path.read_text())["design_selection"]["holm"]
    registered = json.loads(protocol_path.read_text())["registered_contrasts"]
    assert holm["family"] == registered
    assert holm["family_size"] == len(registered)
    assert "E-B" in holm["excluded_from_family"]


def test_the_compute_claims_are_measured_not_asserted(lab_root):
    path = lab_root / "configs" / "lab08_discovery.json"
    if not path.is_file():
        pytest.skip("run scripts/analyse_lab08_discovery.py")
    compute = json.loads(path.read_text())["compute"]
    assert compute["peak_working_set_gib"] is not None, (
        "budget_exceeded without a measured working set is an assertion")
    assert compute["workers_used"] >= 1
    assert "read from the OS rather than declared" in compute["measurement_note"]
    budget = compute["resource_budget"]
    assert compute["budget_exceeded"] == (
        compute["workers_used"] > budget["workers"]
        or compute["peak_working_set_gib"] > budget["working_memory_gib"])


def test_the_lab08_report_carries_the_real_numbers(lab_root):
    """CLAUDE.md rule 9, applied to LAB-08's report.

    Added in LAB-09: every other generated phase report had a drift test and this
    one did not, so the report could have disagreed with `lab08_discovery.json`
    and nothing would have said so.

    The comparison is NUMERIC, not textual. Asserting a formatted string would
    pass or fail on the report's choice of notation rather than on whether the
    number is right, and would have to be rewritten every time the table changes
    its precision.
    """
    import re

    report = lab_root / "reports" / "lab08_report.md"
    discovery = lab_root / "configs" / "lab08_discovery.json"
    if not (report.is_file() and discovery.is_file()):
        pytest.skip("run scripts/write_lab08_report.py")
    text = report.read_text()
    document = json.loads(discovery.read_text())
    assert document["design_selection"]["outcome"] in text

    checked = 0
    for name, record in document["contrast_panel"].items():
        value = record.get("mean_daily_difference")
        if value is None:
            continue
        rows = [ln for ln in text.splitlines() if ln.startswith(f"| `{name}` |")]
        assert rows, f"the report does not show contrast {name}"
        printed = None
        for row in rows:
            cells = [c.strip() for c in row.strip("|").split("|")]
            for cell in cells[1:]:
                match = re.fullmatch(r"[-+]?\d*\.?\d+(?:e[-+]?\d+)?", cell)
                if match:
                    printed = float(cell)
                    break
            if printed is not None:
                break
        assert printed is not None, f"no numeric cell in the report row for {name}"
        assert printed == pytest.approx(value, abs=5e-7), (
            f"{name}: the report shows {printed} and the artifact says {value}")
        checked += 1
    assert checked >= 4, "the report showed fewer contrasts than the artifact carries"


def test_the_compute_capture_counts_every_unit_the_registration_declares(lab_root):
    """L08.6 + guide 10.5.

    The registration names five counted units. An earlier version of the capture
    reported ONE of them, for the dynamic half only, and called the result
    MATCHED_TOTAL_COMPUTE — a budget report that does not count four of its own
    declared units cannot say whether the arms were given the same total.
    """
    path = lab_root / "configs" / "lab08_discovery.json"
    if not path.is_file():
        pytest.skip("run scripts/analyse_lab08_discovery.py")
    compute = json.loads(path.read_text())["compute"]
    units = compute["counted_units"]

    for family in ("calendar_arms_A_and_B", "dynamic_arms_C_D_E"):
        spend = units["per_arm_family"][family]
        for field in ("cutoffs", "unique_strategy_evaluations", "fold_bar_visits",
                      "independent_local_probes"):
            assert spend[field] > 0, f"{family} reports {field}=0, which cannot be right"

    assert units["matched"]["cutoffs_equal"] is True
    ratio = units["matched"]["evaluations_ratio"]
    assert ratio is not None and 0.9 < ratio < 1.1, (
        f"the arms' search effort differs by more than 10% (ratio {ratio}); compute-matching "
        "is the claim that makes the contrast interpretable")

    fits = units["regime_model_fits"]
    assert fits["total_multi_start_fits"] > 0
    assert all(v.get("data_role") == "development" for v in fits["per_symbol"].values()
               if v.get("data_role")), (
        "a registry from another data role is being billed to this phase")
    assert units["response_evaluations"]["count"] > 0

    latency = compute["latency"]
    assert latency["refit_latency_seconds"]["zero_latency_jobs"] == 0, (
        "guide L07.3 forbids a zero refit latency")
    assert latency["refit_latency_seconds"]["min"] > 0
    assert latency["cold_vs_warm_runtime"]["status"] == "NOT_SEPARATELY_MEASURED"
    assert latency["cold_vs_warm_runtime"]["why"]


def test_arm_e_is_compared_against_both_things_the_guide_asks_for(lab_root):
    """Guide 10.1: E is compared against B AND against the matched-bank control.

    Both comparisons are degenerate on this run. A degenerate comparison is
    reported as one; leaving it out because it says nothing is how a required
    control quietly disappears.
    """
    path = lab_root / "configs" / "lab08_discovery.json"
    if not path.is_file():
        pytest.skip("run scripts/analyse_lab08_discovery.py")
    arm_e = json.loads(path.read_text())["arm_e"]
    assert arm_e["versus_B"]["contrast"] == "E-B"
    assert arm_e["versus_BANK_CALENDAR"]["control_status"]
    assert arm_e["versus_BANK_CALENDAR"]["comparison"]
    assert arm_e["versus_BANK_CALENDAR"]["what_would_make_it_informative"]


def test_every_contrast_against_arm_a_carries_the_baseline_caveat(lab_root):
    """T54 — the label has to reach the reported COMPARISON, not just the document.

    LAB-04 measured that the installed public route declares OOS-adjusted
    selection and labelled arm A `A_legacy_selection_adjusted`. That label sat on
    the document and in the report's prose. A contrast lifted out of the panel —
    which is exactly what LAB-09's claim report does for the selection and timing
    contributions — arrived with no hint that its baseline is not untouched.
    """
    path = lab_root / "configs" / "lab08_discovery.json"
    if not path.is_file():
        pytest.skip("run scripts/analyse_lab08_discovery.py")
    document = json.loads(path.read_text())
    label = document["legacy_arm_label"]
    if not label["mode_declares_oos_selection"]:
        pytest.skip("the installed route does not declare OOS selection on this install")

    against_a, clean = [], []
    for name, record in document["contrast_panel"].items():
        involves_a = "A" in name.replace("(", "").replace(")", "").split("-")
        (against_a if involves_a else clean).append((name, record))

    assert against_a, "no contrast is measured against arm A, which cannot be right"
    for name, record in against_a:
        assert record.get("baseline_is_not_untouched") is True, (
            f"{name} is measured against arm A and does not say its baseline is not untouched")
        assert record.get("baseline_label") == "A_legacy_selection_adjusted"
        assert "out-of-sample" in record["baseline_caveat"]
    for name, record in clean:
        assert not record.get("baseline_is_not_untouched"), (
            f"{name} does not involve arm A but carries the baseline caveat")

    # the interaction contains B-A, so it is partly against arm A too
    interaction = dict(document["contrast_panel"]).get("(D-C)-(B-A)")
    if interaction:
        assert interaction.get("baseline_is_not_untouched") is True


def test_the_variants_that_were_registered_and_never_run_are_recorded(lab_root):
    """Guide 11.3 / L08 outputs — keep the alpha and timeframe variants TRIED.

    The rule exists to stop a variant that produced a worse answer from being
    quietly dropped. The strongest form of that record is the one nobody writes:
    the alternatives were pre-registered and NONE was run, so there is nothing
    dropped to hide. An empty list of attempted variants and an unstated one look
    identical in an artifact, and only one of them is evidence.
    """
    path = lab_root / "configs" / "lab08_discovery.json"
    if not path.is_file():
        pytest.skip("run scripts/analyse_lab08_discovery.py")
    variants = json.loads(path.read_text())["variants_registered_and_not_run"]
    protocol = json.loads((lab_root / "configs" / "lab08_pilot_protocol.json").read_text())

    timeframes = variants["timeframe_variants"]
    assert timeframes["secondary_registered"] == {
        alpha: frames["secondary_registered"]
        for alpha, frames in protocol["timeframes"].items()}
    assert timeframes["primary_decision_bars"] == {
        alpha: frames["decision_bars"] for alpha, frames in protocol["timeframes"].items()}
    assert timeframes["secondary_variants_run"] == 0
    for alpha, secondary in timeframes["secondary_registered"].items():
        assert secondary != timeframes["primary_decision_bars"][alpha], (
            f"{alpha}'s secondary timeframe is the same as its primary, so nothing was reserved")

    alphas = variants["alpha_variants"]
    assert alphas["tier_used_by_every_arm"] == "canonical_v1"
    assert alphas["thesis_changes_entering_an_arm"] == 0, (
        "a thesis change entered an experiment arm; guide 2.1 keeps those in a separate tier")
    for delta in alphas["deltas_outside_every_arm"]:
        assert delta["applies_to_experiment_arms"] == [], delta["delta_id"]
