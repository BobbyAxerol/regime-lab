"""FUP-02 acceptance — expanded-budget full-window paired discovery.

Each guard has a denominator and can go red:

* the compute-budget revision is registered BEFORE any run: every run/invocation/
  attempt timestamp is later than ``budget_revision.json#/registered_at_utc``;
* a shard re-run is deterministic and the per-fold shard engine reproduces the
  canonical whole-arm fold selection exactly (same params, same digest) while
  declaring ``oos_used_for_selection=False``;
* the resume merge never overwrites a completed fold and is idempotent;
* ``cell_coverage.json`` covers all 20 primary cells with a status from the
  registered vocabulary, a reason and evidence refs;
* a non-run or budget-stopped cell carries null metrics with an exact reason,
  never a fabricated or zero-filled equity.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

LAB_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(LAB_ROOT / "scripts"))

import run_fup02 as R  # noqa: E402

from crypto_regime_lab.experiments.dynamic_fold_provider import CutoffSchedule  # noqa: E402

FUP02 = ("evidence", "corrective_mode4_v3", "FUP-02")
PRIMARY_ARMS = ("M4_CAL", "M4_REGIME")
SHARD_STATUS = {"PENDING", "COMPLETE", "BUDGET_STOPPED", "NOT_RUN_BUDGET", "FAILED",
                "INSUFFICIENT_DATA"}
COVERAGE_STATUS = {"RUN_VALID", "RUN_NOT_EVALUABLE", "BUDGET_STOPPED", "NOT_RUN_BUDGET",
                   "FAILED", "INSUFFICIENT_DATA", "BLOCKED_CAPABILITY", "NOT_RUN"}


def _load(lab_root: Path, run_dir: str, name: str) -> dict:
    return json.loads((lab_root / "evidence" / "corrective_mode4_v3" / run_dir
                       / name).read_text(encoding="utf-8"))


def _shipped(lab_root: Path) -> bool:
    return (lab_root / "evidence" / "corrective_mode4_v3" / "FUP-02"
            / "paired_discovery_fullwindow.json").is_file()


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


# ---------------------------------------------------------------------------
# budget registration order
# ---------------------------------------------------------------------------

def test_fup02_budget_revision_is_registered_before_every_run_timestamp(lab_root):
    if not _shipped(lab_root):
        pytest.skip("run scripts/run_fup02.py --register-budget first")
    budget = _load(lab_root, "FUP-02", "budget_revision.json")
    full = _load(lab_root, "FUP-02", "paired_discovery_fullwindow.json")
    registered = _parse(budget["registered_at_utc"])
    assert budget["status"] == "REGISTERED_BEFORE_THE_FUP02_RUNS"
    assert registered <= _parse(full["run_started_at_utc"]), (
        "the run started before the compute-budget revision was registered")
    checked_invocations = 0
    checked_shards = 0
    for invocation in full["invocations"]:
        assert registered <= _parse(invocation["started_at_utc"]), invocation
        checked_invocations += 1
    for cell in full["cells"]:
        for arm in PRIMARY_ARMS:
            first = cell["shards"][arm].get("first_attempt_at_utc")
            if first is not None:
                assert registered <= _parse(first), (cell["cell"], arm, first)
                checked_shards += 1
    assert checked_invocations >= 1, "no invocation was recorded"
    assert checked_shards >= 1, "no shard attempt was recorded"


def test_fup02_run_config_uses_registered_trials_seed_and_equal_arms(lab_root):
    if not _shipped(lab_root):
        pytest.skip("run scripts/run_fup02.py --register-budget first")
    budget = _load(lab_root, "FUP-02", "budget_revision.json")
    full = _load(lab_root, "FUP-02", "paired_discovery_fullwindow.json")
    assert full["run_config"]["trials_per_cutoff"] == \
        budget["trial_budget"]["executed_per_cutoff"]
    assert full["run_config"]["seed"] == budget["trial_budget"]["seed_policy"]["seed"]
    assert budget["trial_budget"]["equal_across_arms"] is True
    assert budget["resource_caps"]["per_shard_cap_seconds"] <= 900
    # both arms of every cell run the same schedule by construction; make sure the
    # artifact really repeats them and never a per-cell tuned list
    per_arm_cutoffs: dict[str, set] = {arm: set() for arm in PRIMARY_ARMS}
    for cell in full["cells"]:
        assert cell["route"] == "event", (
            f"{cell['cell']} is not on the qualified event route")
        for arm in PRIMARY_ARMS:
            cutoffs = tuple(cell["shards"][arm]["cutoffs"])
            assert cutoffs, (cell["cell"], arm)
            per_arm_cutoffs[arm].add(cutoffs)
    for arm, seen in per_arm_cutoffs.items():
        assert len(seen) == 1, (arm, "cells ran different cutoff lists")


# ---------------------------------------------------------------------------
# resume merge and non-run metrics
# ---------------------------------------------------------------------------

def test_fup02_resume_merge_is_idempotent_and_never_drops_a_completed_fold():
    cell = {"cell": "A-HMA/TEST", "alpha_id": "A-HMA"}
    schedule = CutoffSchedule(arm="M4_CAL", cutoffs=("2021-01-01T00:00:00+00:00",),
                              source="unit", train_memory_days=180)
    shard = R._new_shard(cell, "M4_CAL", schedule)
    folded = {
        "fold_id": 0, "cutoff": schedule.cutoffs[0], "status": "SCORED", "reason": None,
        "selected_params": {"a": 1}, "selected_digest": "pv-x",
        "selected_is_objective": 1.0, "candidate_count": 3,
        "event_account_runs": 2, "event_scorer_calls": 2,
    }
    R.merge_scored_fold(shard, folded)
    first = json.dumps(shard, sort_keys=True)
    R.merge_scored_fold(shard, folded)
    assert json.dumps(shard, sort_keys=True) == first, (
        "merging the same scored fold twice changed the shard state")
    assert shard["completed_fold_ids"] == [0]
    assert shard["params_by_fold"] == {"0": {"a": 1}}
    assert shard["oos_used_for_selection"] is False
    # an empty/incomplete resume view must never delete a completed fold
    empty = R._new_shard(cell, "M4_CAL", schedule)
    empty["completed_fold_ids"] = list(shard["completed_fold_ids"])
    empty["params_by_fold"] = dict(shard["params_by_fold"])
    assert empty["completed_fold_ids"] == [0]


def test_fup02_non_run_shard_keeps_null_metrics_and_exact_reason():
    cell = {"cell": "A-HMA/TEST", "alpha_id": "A-HMA"}
    schedule = CutoffSchedule(arm="M4_REGIME", cutoffs=("2021-01-01T00:00:00+00:00",),
                              source="unit", train_memory_days=180)
    shard = R._new_shard(cell, "M4_REGIME", schedule)
    R.mark_not_run_budget(shard, "the invocation budget of 10s was exhausted")
    assert shard["status"] == "NOT_RUN_BUDGET"
    assert shard["account"] is None
    assert "budget" in shard["stop_reason"].lower()
    for entry in shard["cutoff_results"]:
        assert entry["status"] == "NOT_RUN"
        assert entry["trials"] is None and entry["selected_params"] is None
        assert entry["wall_seconds"] is None
        assert "budget" in entry["reason"].lower()
    R.mark_insufficient(shard, "snapshot load failed")
    assert shard["status"] == "INSUFFICIENT_DATA"
    assert shard["account"] is None


# ---------------------------------------------------------------------------
# coverage
# ---------------------------------------------------------------------------

def test_fup02_coverage_has_20_cells_with_status_reason_and_evidence(lab_root):
    coverage = _load(lab_root, "FUP-02", "cell_coverage.json")
    cells = coverage["cells"]
    assert len(cells) == 20
    names = [cell["cell"] for cell in cells]
    assert len(set(names)) == 20
    expected = {f"{alpha}/{symbol}"
                for alpha in ("A-SC", "A-HMA", "A-VWAP", "A-HASH")
                for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT")}
    assert set(names) == expected
    assert set(coverage["status_vocabulary"]) == COVERAGE_STATUS
    for cell in cells:
        assert cell["coverage_status"] in COVERAGE_STATUS, cell
        assert cell["reason"].strip(), f"{cell['cell']} has no reason"
        assert cell["evidence_ref"].strip() and cell["evidence_refs"]
        assert set(cell["arm_status"]) == set(PRIMARY_ARMS)
        for status in cell["arm_status"].values():
            assert status in SHARD_STATUS, status


def test_fup02_no_fabricated_equity_on_non_run_or_stopped_cells(lab_root):
    full = _load(lab_root, "FUP-02", "paired_discovery_fullwindow.json")
    coverage = _load(lab_root, "FUP-02", "cell_coverage.json")
    checked_non_complete = 0
    checked_complete = 0
    for cell in full["cells"]:
        for arm in PRIMARY_ARMS:
            shard = cell["shards"][arm]
            if shard["status"] != "COMPLETE":
                assert shard["account"] is None, (cell["cell"], arm, "fabricated equity")
                assert (shard["account_reason"] or "").strip(), (cell["cell"], arm)
                checked_non_complete += 1
            else:
                assert shard["account"]["equity_last"] is not None, (cell["cell"], arm)
                assert shard["account"]["status"] == "EVALUATED"
                assert shard["account"]["fills_source"] == (
                    "integration.event_account.run_event_account")
                checked_complete += 1
    for cell in coverage["cells"]:
        if not cell["executed"]:
            assert cell["account_metrics"] is None, (
                f"{cell['cell']} carries equity for a non-executed cell")
            assert (cell["account_metrics_reason"] or "").strip()
            assert cell["contrast_status"] is None
        if cell["coverage_status"] in ("NOT_RUN", "NOT_RUN_BUDGET", "BUDGET_STOPPED"):
            assert cell["account_metrics"] is None or cell["account_metrics"] == {}
    assert checked_non_complete + checked_complete == 40, "the shard denominator collapsed"


# ---------------------------------------------------------------------------
# the per-fold shard engine reproduces the canonical fold exactly
# ---------------------------------------------------------------------------

def test_fup02_fold_shard_engine_matches_canonical_fold_and_is_deterministic(lab_root):
    """Same inputs -> identical selection, and the whole-arm fold is reproduced.

    A two-cutoff schedule on real BTCUSDT 4h bars is cheap enough for the suite;
    the engine, scorer and provider are the production ones.
    """
    snapshot_root = lab_root / "snapshots" / "server_core_v1"
    if not (snapshot_root / "crypto_binance_futures_1m" / "BTCUSDT").is_dir():
        pytest.skip("the registered snapshot is not present on this machine")
    frame = R.load_window_frame(snapshot_root, "BTCUSDT", "4h").loc[:"2021-12-31"]
    schedule = CutoffSchedule(
        arm="M4_CAL",
        cutoffs=("2021-01-01T00:00:00+00:00", "2021-06-30T00:00:00+00:00"),
        source="test fixture", train_memory_days=180)
    trials, seed = 4, 11
    import crypto_regime_lab.experiments.dynamic_fold_provider as dfp

    full = dfp.run_cutoff_walk_forward(
        "A-HMA", frame, schedule, param_ranges=R.engine_param_ranges("A-HMA"),
        strategy_class=dfp.ZeroSignalStrategy, optuna_trials=trials, seed=seed, route="event")
    assert full["ok"], full.get("error")
    first = R.run_one_fold("A-HMA", frame, schedule, 0, trials, seed)
    second = R.run_one_fold("A-HMA", frame, schedule, 0, trials, seed)
    last = R.run_one_fold("A-HMA", frame, schedule, 1, trials, seed)
    assert first["ok"], first.get("error")
    assert last["ok"], last.get("error")
    assert first["params_by_fold"] == second["params_by_fold"], (
        "re-running the same shard with unchanged inputs changed the selection")
    assert first["selected_digest"] == second["selected_digest"]
    for fold_id, shard in ((0, first), (1, last)):
        assert shard["ok"], shard.get("error")
        assert shard["params_by_fold"] == {str(fold_id): full["params_by_fold"][str(fold_id)]}, (
            f"fold {fold_id}: the shard engine did not reproduce the whole-arm selection")
        assert shard["oos_used_for_selection"] is False
        for row in shard["fold_selection_table"]:
            assert row["outer_oos_used_for_selection"] is False
        for record in shard["trial_records"]:
            metadata = record.get("selection_metadata") or {}
            assert metadata.get("oos_used_for_selection") is not True
            assert metadata.get("oos_seen_by_optuna") is not True
