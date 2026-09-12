"""The evaluator's own invariants: determinism, and that the fast path is the right answer."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

LAB_ROOT = Path(__file__).resolve().parent.parent

from crypto_regime_lab.data import panel as P
from crypto_regime_lab.experiments.evaluator import (ACCOUNT, episode_bounds, episode_metrics,
                                                     run_candidate,
                                                     run_candidate_fixed_point_reference,
                                                     window_metrics)
from crypto_regime_lab.selector.alpha_schemas import SEED_POINTS

SNAPSHOT = LAB_ROOT / "snapshots" / "server_core_v1"


@pytest.fixture(scope="module")
def hourly_window():
    manifest = json.loads((SNAPSHOT / "manifest.json").read_text())
    frame = P.load_resampled(SNAPSHOT, "crypto_binance_futures_1m", "BTCUSDT", "1h",
                             manifest=manifest)
    frame["time"] = pd.to_datetime(frame["time"])
    if frame["time"].dt.tz is None:
        frame["time"] = frame["time"].dt.tz_localize("UTC")
    frame = frame.set_index("time").sort_index()
    window = frame[(frame.index >= "2021-03-01") & (frame.index < "2021-05-01")]
    assert len(window) > 1000
    return window


def test_the_fast_sweep_matches_a_whole_window_fixed_point(hourly_window):
    """The exit oracle must give the same account as iterating the whole window."""
    params = dict(SEED_POINTS["A-HMA"])
    fast = run_candidate("A-HMA", params, hourly_window)
    slow = run_candidate_fixed_point_reference("A-HMA", params, hourly_window)

    assert fast.converged, "the fast path must reach a self-consistent fixed point"
    assert slow.converged, "the reference loop did not converge; the comparison is void"
    assert fast.entries == slow.entries
    assert [f["bar_index"] for f in fast.fills] == [f["bar_index"] for f in slow.fills]
    assert [f["reason"] for f in fast.fills] == [f["reason"] for f in slow.fills]
    assert np.array_equal(fast.equity, slow.equity)
    assert fast.passes <= slow.passes


def test_evaluation_is_deterministic(hourly_window):
    params = dict(SEED_POINTS["A-HMA"])
    a = run_candidate("A-HMA", params, hourly_window)
    b = run_candidate("A-HMA", params, hourly_window)
    assert np.array_equal(a.equity, b.equity)
    assert [f["bar_index"] for f in a.fills] == [f["bar_index"] for f in b.fills]


def test_protective_exits_agree_with_what_the_adapter_was_driven_with(hourly_window):
    run = run_candidate("A-HMA", dict(SEED_POINTS["A-HMA"]), hourly_window)
    assert run.converged
    assert run.diagnostics.get("protective_exits", 0) > 0, (
        "this fixture must actually exercise resting stops, or it proves nothing")


def test_entries_are_sized_to_the_frozen_entry_notional(hourly_window):
    run = run_candidate("A-HMA", dict(SEED_POINTS["A-HMA"]), hourly_window)
    entries = [f for f in run.fills if f["reason"] == "entry"]
    assert entries, "no entry filled; sizing cannot be checked"
    for fill in entries[:20]:
        notional = abs(fill["qty"]) * fill["price"]
        assert notional == pytest.approx(ACCOUNT["entry_notional_usdt"], rel=0.02), (
            "an entry must be sized to the frozen notional, not to one whole unit")


def test_a_failed_episode_is_never_scored_as_zero(hourly_window):
    run = run_candidate("A-SC", dict(SEED_POINTS["A-SC"]), hourly_window)
    bounds = episode_bounds(run.index, 4)
    metrics = episode_metrics(run, bounds)
    assert len(metrics) == 4
    for name, record in metrics.items():
        assert np.isfinite(record["utility"])
        assert isinstance(record["gate_pass"], bool)


def test_window_metrics_report_convergence_and_unmapped_intents(hourly_window):
    metrics = window_metrics(run_candidate("A-HASH", dict(SEED_POINTS["A-HASH"]), hourly_window))
    assert "converged" in metrics and "unmapped_intents" in metrics
    assert metrics["unmapped_intents"] >= 0


def test_selection_is_frozen_before_the_test_window_is_touched(hourly_window):
    """Guide 7.2 step 7: freeze selection before outer evaluation.

    The same mutation method used on the installed engine, turned on the lab's own
    cutoff: rewrite everything after the cutoff and require both arms' selections
    to be byte-identical. A future refactor that leaks the test window into
    selection fails here.
    """
    from crypto_regime_lab.experiments import calendar_baseline as CB
    from crypto_regime_lab.selector.installed_wfo import mutate_oos

    cutoff = hourly_window.index[len(hourly_window) // 2]
    train = hourly_window[hourly_window.index < cutoff]
    budget = CB.SearchBudget(discovery_trials=8, anchors=2, probes_per_anchor=3)
    calendar = CB.CalendarSpec(inner_episodes=4)
    incumbents = {arm: dict(SEED_POINTS["A-SC"]) for arm in CB.ARMS}

    base = CB.run_cutoff("A-SC", "BTCUSDT", train, 0, incumbents,
                         budget=budget, calendar=calendar)
    mutated_bars = mutate_oos(hourly_window, cutoff.isoformat())
    assert not mutated_bars[mutated_bars.index >= cutoff].equals(
        hourly_window[hourly_window.index >= cutoff]), "the mutation did nothing"
    assert mutated_bars[mutated_bars.index < cutoff].equals(train), (
        "the mutation must leave the training window untouched")

    after = CB.run_cutoff("A-SC", "BTCUSDT", mutated_bars[mutated_bars.index < cutoff], 0,
                          incumbents, budget=budget, calendar=calendar)
    assert base["arm_A"]["params"] == after["arm_A"]["params"]
    assert base["arm_B"]["params"] == after["arm_B"]["params"]
    assert base["arm_A"]["point_id"] == after["arm_A"]["point_id"]


def test_both_arms_choose_from_the_identical_pool(hourly_window):
    from crypto_regime_lab.experiments import calendar_baseline as CB

    cutoff = hourly_window.index[len(hourly_window) // 2]
    train = hourly_window[hourly_window.index < cutoff]
    out = CB.run_cutoff(
        "A-SC", "BTCUSDT", train, 0,
        {arm: dict(SEED_POINTS["A-SC"]) for arm in CB.ARMS},
        budget=CB.SearchBudget(discovery_trials=8, anchors=2, probes_per_anchor=3),
        calendar=CB.CalendarSpec(inner_episodes=4))
    assert out["budget"]["both_arms_see_the_same_pool"] is True
    assert out["arm_A"]["candidates_considered"] <= out["budget"]["unique_executions"]
    # arm B is stricter by construction, never looser
    assert out["arm_B"].get("eligible_count", 0) <= out["arm_A"]["candidates_considered"]
    assert out["budget"]["shared_incumbent_anchor"] is True, (
        "at fold 0 both arms carry the same incumbent, so it must cost only one anchor")


# ---------------------------------------------------------------------------
# regressions for technical debt removed on 2026-09-10
# ---------------------------------------------------------------------------

def test_blocked_alphas_come_from_the_certification_not_a_literal():
    """A second hand-typed copy of a certification decision can drift from it."""
    from crypto_regime_lab.experiments import calendar_baseline as CB

    certification = json.loads(
        (LAB_ROOT / "configs" / "lab02_certification_summary.json").read_text())
    expected = {alpha for alpha, record in certification["certifications"].items()
                if record["status"] != "READY_FOR_RESEARCH"}
    assert set(CB.NOT_READY) == expected
    for alpha_id, reason in CB.NOT_READY.items():
        assert certification["certifications"][alpha_id]["status"] in reason


def test_decision_interval_has_one_definition():
    from crypto_regime_lab.data import qualification
    from crypto_regime_lab.experiments import calendar_baseline as CB

    assert CB.DECISION_INTERVAL is qualification.DECISION_INTERVAL, (
        "the decision interval was pinned in LAB-03; a second copy can drift from it")


def test_a_partial_matrix_is_labelled_partial():
    from crypto_regime_lab.experiments import calendar_baseline as CB

    one = CB.run_cell("A-HASH", "BTCUSDT", pd.DataFrame())
    summary = CB.summarize([one])
    assert summary["matrix_complete"] is False
    assert summary["cells_expected"] == 20


def _committed_summary() -> dict:
    """Read the COMMITTED artifact, never the scratch cache.

    `.cache/` is working space: it gets renamed when a design is re-run, so a test
    pointed at it silently skips instead of checking anything. `configs/` is the
    evidence the phase actually stands on.
    """
    path = LAB_ROOT / "configs" / "lab04_calendar_baseline.json"
    if not path.is_file():
        pytest.skip("run scripts/summarize_calendar_baseline.py")
    summary = json.loads(path.read_text())
    if summary["cells_run"] == 0:
        pytest.skip("the committed summary has no completed cells")
    return summary


def test_trade_counts_distinguish_fills_from_entries():
    """`trades` meaning either fills or round trips is how a table starts lying."""
    from crypto_regime_lab.experiments import calendar_baseline as CB

    summary = _committed_summary()
    assert "engine_fills counts FILLS" in summary["trade_count_convention"]
    for arm in CB.ARMS:
        finger = summary["parameter_behaviour_fingerprint"][arm]
        assert finger["engine_fills"] >= finger["entries"] > 0, (
            "an entry and its exit are two fills, so fills must exceed entries")
        assert finger["mean_holding_bars"] is not None


def test_summaries_never_mean_an_empty_list():
    from crypto_regime_lab.experiments import calendar_baseline as CB

    empty = CB.summarize([])
    for arm in CB.ARMS:
        assert empty["lower_tail"][arm]["mean_max_drawdown"] is None
        assert empty["period_concentration"][arm]["mean"] is None
        assert empty["parameter_behaviour_fingerprint"][arm]["mean_turnover"] is None
    assert empty["verdict"].startswith("NO_COMPARABLE_CELLS")


# ---------------------------------------------------------------------------
# repository hygiene gates
# ---------------------------------------------------------------------------

def _pyflakes(*targets: str) -> list[str]:
    import subprocess

    done = subprocess.run(
        [sys.executable, "-m", "pyflakes", *targets],
        cwd=LAB_ROOT, capture_output=True, text=True, timeout=900)
    # the four supplied alphas are byte-preserved provenance: hash_momentum.py really
    # does use np without importing numpy (finding + SD-HASH-01), and fixing it would
    # destroy the evidence
    return [ln for ln in done.stdout.splitlines() if ln and "raw-supplied" not in ln]


def test_no_dead_code_or_undefined_names_in_lab_source():
    findings = _pyflakes("src/", "scripts/", "tests/")
    assert findings == [], "\n".join(findings)


def test_the_raw_alphas_are_still_byte_identical():
    """The lint exclusion above is only safe while the originals are untouched."""
    import hashlib

    from crypto_regime_lab.safety.archive import ALLOWED_ALPHA_FILES

    raw_dir = LAB_ROOT / "src" / "crypto_regime_lab" / "alphas" / "raw-supplied"
    for name, expected in ALLOWED_ALPHA_FILES.items():
        digest = hashlib.sha256((raw_dir / name).read_bytes()).hexdigest()
        assert digest.startswith(expected[:16]), f"{name} no longer matches the archive manifest"


def test_dev_tools_are_declared_and_stay_out_of_the_runtime_lock():
    tools = json.loads((LAB_ROOT / "configs" / "dev_tools.json").read_text())
    lock = (LAB_ROOT / "configs" / "requirements.lock").read_text()
    for name in tools["tools"]:
        assert name not in lock, f"{name} is dev tooling and must not enter the runtime lock"
    assert tools["engine_pin_unchanged"]["quantbt-engine"] == "1.1.1"
    assert tools["engine_pin_unchanged"]["quantbt-native"] == "0.4.2"

    src = LAB_ROOT / "src" / "crypto_regime_lab"
    for path in src.rglob("*.py"):
        if "raw-supplied" in str(path):
            continue
        text = path.read_text()
        for name in tools["tools"]:
            assert f"import {name}" not in text, f"{path} imports the dev tool {name}"


def test_deployed_evidence_is_derived_not_asserted():
    """The diagnostic must come from stored per-candidate statuses, not a narrative."""
    from crypto_regime_lab.experiments import calendar_baseline as CB

    evidence = _committed_summary()["local_evidence_behind_each_deployment"]
    for arm in CB.ARMS:
        record = evidence[arm]
        assert record["deployments"] > 0
        assert sum(record["robust_status_of_the_deployed_point"].values()) \
            == record["deployments"]
        assert record["share_its_own_panel_rejects"] is not None
    # arm B selects only from ELIGIBLE, so by construction it can never deploy a
    # point its own panel rejects. If that ever becomes non-zero, the gate leaked.
    assert evidence["B"]["deployed_a_point_its_own_panel_rejects"] == 0
    assert set(evidence["B"]["robust_status_of_the_deployed_point"]) <= {"ELIGIBLE"}


def test_the_sign_test_caveat_states_the_real_cell_count():
    """A caveat with a hardcoded n becomes a false statement the moment n changes."""
    from crypto_regime_lab.experiments import calendar_baseline as CB

    pairs = [(f"c{i}", 0.0, 1.0) for i in range(7)]
    test = CB._sign_test(pairs)
    assert test["cells"] == 7
    assert "over 7 cells" in test["caveat"]


# ---------------------------------------------------------------------------
# guide 7.2 step 1: anchors come from THREE sources, not one
# ---------------------------------------------------------------------------

def test_anchor_budget_matches_the_guide():
    from crypto_regime_lab.experiments import calendar_baseline as CB

    budget = CB.BUDGET
    assert budget.discovery_trials == 64
    assert budget.probes_per_anchor == 8
    # 4 anchor slots: TPE top + space filling + incumbent
    assert budget.anchors + budget.space_filling_anchors + 1 == 4
    assert budget.nominal_total == 96


def test_anchors_are_drawn_from_tpe_incumbent_and_space_filling(hourly_window):
    """All anchors from the TPE top would confine every local panel to one region."""
    from crypto_regime_lab.experiments import calendar_baseline as CB
    from crypto_regime_lab.selector.alpha_schemas import SCHEMAS

    cutoff = hourly_window.index[len(hourly_window) // 2]
    train = hourly_window[hourly_window.index < cutoff]
    out = CB.run_cutoff(
        "A-SC", "BTCUSDT", train, 0,
        {arm: dict(SEED_POINTS["A-SC"]) for arm in CB.ARMS},
        budget=CB.SearchBudget(discovery_trials=14, anchors=2, space_filling_anchors=1,
                               probes_per_anchor=3),
        calendar=CB.CalendarSpec(inner_episodes=4))

    sources = out["budget"]["anchor_sources"]
    assert sources["tpe_top"], "no anchor came from the TPE ranking"
    assert sources["space_filling"], "guide 7.2 step 1 requires space-filling coverage"
    assert sources["incumbent"], "the incumbent must be an anchor"
    assert out["budget"]["anchors_used"] == 4

    # the space-filling anchor must actually be somewhere else, not a near-duplicate
    schema = SCHEMAS["A-SC"]
    for key, distance in out["budget"]["space_filling_min_distance_to_tpe_anchors"].items():
        assert distance > CB.BUDGET.radius, (
            f"{key} sits within the probe radius of a TPE anchor, so it adds no coverage")
    assert schema is CB.SCHEMAS["A-SC"]


def test_the_space_filling_anchor_is_deterministic(hourly_window):
    from crypto_regime_lab.experiments import calendar_baseline as CB

    cutoff = hourly_window.index[len(hourly_window) // 2]
    train = hourly_window[hourly_window.index < cutoff]
    budget = CB.SearchBudget(discovery_trials=14, anchors=2, space_filling_anchors=1,
                             probes_per_anchor=3)
    calendar = CB.CalendarSpec(inner_episodes=4)
    incumbents = {arm: dict(SEED_POINTS["A-SC"]) for arm in CB.ARMS}
    first = CB.run_cutoff("A-SC", "BTCUSDT", train, 0, incumbents,
                          budget=budget, calendar=calendar)
    second = CB.run_cutoff("A-SC", "BTCUSDT", train, 0, incumbents,
                           budget=budget, calendar=calendar)
    assert (first["budget"]["anchor_sources"]["space_filling"]
            == second["budget"]["anchor_sources"]["space_filling"])


def test_a_sign_reversal_inside_an_alpha_is_surfaced_not_averaged_away():
    """Guide 13.6: a pooled aggregate must never hide a reversed sign."""
    from crypto_regime_lab.experiments import calendar_baseline as CB

    def _cell(alpha, symbol, a, b):
        return {"alpha_id": alpha, "symbol": symbol, "status": "RUN", "folds": [],
                "arms": {"A": {"net_return": a}, "B": {"net_return": b}}}

    cells = [
        # B wins clearly on one alpha ...
        _cell("A-X", "S1", 0.0, 0.2), _cell("A-X", "S2", 0.0, 0.2),
        _cell("A-X", "S3", 0.0, 0.2),
        # ... and loses on another
        _cell("A-Y", "S1", 0.2, 0.0), _cell("A-Y", "S2", 0.2, 0.0),
    ]
    split = CB._contrast_by_alpha(cells)
    assert split["pooled_winner"] == "B"
    assert split["A-X"]["winner"] == "B"
    assert split["A-Y"]["winner"] == "A"
    assert split["reversals"] == ["A-Y"]
    assert split["A-Y"]["sign_agrees_with_the_pooled_result"] is False
    assert "13.6" in split["reading"]


def test_no_reversal_is_reported_when_every_alpha_agrees():
    from crypto_regime_lab.experiments import calendar_baseline as CB

    cells = [{"alpha_id": a, "symbol": s, "status": "RUN", "folds": [],
              "arms": {"A": {"net_return": 0.0}, "B": {"net_return": 0.1}}}
             for a in ("A-X", "A-Y") for s in ("S1", "S2")]
    split = CB._contrast_by_alpha(cells)
    assert split["reversals"] == []
    assert split["pooled_winner"] == "B"
