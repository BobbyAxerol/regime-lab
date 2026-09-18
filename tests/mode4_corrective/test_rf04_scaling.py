"""RF-04.6 acceptance — scaled paired discovery and A-SC event-route fidelity.

Each guard has a denominator and can go red:

* the full artifact covers exactly the 10 runnable primary cells, unique, with
  both primary arms and an explicit route on every run/arm;
* every scored arm declares ``oos_used_for_selection=False`` at arm, fold and
  trial level;
* every valid A-SC event run carries a real per-fill ledger from the native
  event account, and the A-SC/BTCUSDT endpoint run is retained only as the
  registered route deviation;
* the 20-cell coverage has one explicit status per cell with a reason and an
  evidence ref, and a non-executed cell never carries an estimated or zero
  equity.
"""

from __future__ import annotations

import json

RF04 = ("evidence", "corrective_mode4_v3", "RF-04")
PRIMARY_ARMS = ("M4_CAL", "M4_REGIME")
STATUS_VOCABULARY = {"RUN_VALID", "RUN_NOT_EVALUABLE", "BLOCKED_CAPABILITY",
                     "NOT_RUN", "NOT_RUN_BUDGET", "INSUFFICIENT_DATA"}
EXPECTED_CELLS = {f"{alpha}/{symbol}" for alpha in ("A-SC", "A-HMA")
                  for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT")}
BLOCKED_ALPHAS = {"A-VWAP", "A-HASH"}


def _load(lab_root, name: str) -> dict:
    return json.loads((lab_root.joinpath(*RF04) / name).read_text(encoding="utf-8"))


def _primary_run(cell: dict) -> dict:
    matches = [run for run in cell["runs"] if run["route"] == cell["primary_route"]]
    assert len(matches) == 1, (
        f"{cell['cell']} has {len(matches)} runs on its primary route "
        f"{cell['primary_route']!r}")
    return matches[0]


def test_rf04_full_paired_artifact_covers_10_runnable_cells_with_both_arms(lab_root):
    full = _load(lab_root, "paired_discovery_full.json")
    assert full["status"] == "FULL_PAIRED_DISCOVERY_COMPLETE"
    cells = full["cells"]
    names = [cell["cell"] for cell in cells]
    assert len(names) == 10 and len(set(names)) == 10
    assert set(names) == EXPECTED_CELLS
    assert full["mode4_contract"]["oos_used_for_selection"] is False
    assert full["cohort"]["planned_cells"] == 20
    assert full["cohort"]["runnable_cells"] == 10
    for cell in cells:
        run = _primary_run(cell)
        assert run["route"] in ("endpoint", "event")
        assert run["route_role"]
        assert run["status"] == "RUN", (cell["cell"], run.get("status"))
        assert run["contrast"]["status"] == "VALID", (
            cell["cell"], run["contrast"].get("reasons"))
        assert run["contrast"]["route"] == run["route"]
        for arm_name in PRIMARY_ARMS:
            arm = run["arms"][arm_name]
            assert arm["route"] == run["route"], (
                f"{cell['cell']}:{arm_name} has no matching explicit route field")
            assert arm["ok"], (cell["cell"], arm_name, arm.get("error"))
            assert arm["fold_count"] >= 1
            assert len(arm["cutoffs"]) == arm["fold_count"]
            assert set(arm["params_by_fold"]) == {
                str(index) for index in range(arm["fold_count"])}
            assert arm["selected_digest"], f"{cell['cell']}:{arm_name} lacks a digest"
            assert arm["fold_selection_table"], f"{cell['cell']}:{arm_name} lacks folds"
            account = arm["account"] or {}
            assert account.get("equity_last") is not None, (
                f"{cell['cell']}:{arm_name} has no engine equity")
            report = account.get("engine_report") or {}
            trades = report.get("num_trades")
            if trades is None:
                trades = account.get("engine_fill_count")
            assert trades is not None, f"{cell['cell']}:{arm_name} has no trade count"


def test_rf04_full_runs_declare_oos_used_for_selection_false(lab_root):
    full = _load(lab_root, "paired_discovery_full.json")
    checked_folds = 0
    checked_trials = 0
    for cell in full["cells"]:
        for run in cell["runs"]:
            for arm_name in PRIMARY_ARMS:
                arm = run["arms"][arm_name]
                assert arm["oos_used_for_selection"] is False, (
                    f"{cell['cell']}:{run['route']}:{arm_name} selects on OOS")
                for row in arm["fold_selection_table"]:
                    assert row["outer_oos_used_for_selection"] is False
                    checked_folds += 1
                for trial in arm["trial_records"]:
                    metadata = trial.get("selection_metadata") or {}
                    assert metadata.get("oos_used_for_selection") is not True
                    assert metadata.get("oos_seen_by_optuna") is not True
                    if trial.get("objective") is not None:
                        assert (metadata.get("oos_used_for_selection") is False
                                or metadata.get("oos_seen_by_optuna") is False), (
                            f"{cell['cell']}:{run['route']}:{arm_name} trial "
                            f"{trial.get('trial_id')} does not declare OOS blindness")
                    checked_trials += 1
    assert checked_folds >= 10 * 2 * 3
    assert checked_trials >= 10 * 2 * 24


def test_rf04_asc_event_route_has_per_fill_ledger_and_registered_deviation(lab_root):
    full = _load(lab_root, "paired_discovery_full.json")
    coverage = _load(lab_root, "cell_coverage.json")
    asc_cells = [cell for cell in full["cells"] if cell["alpha_id"] == "A-SC"]
    assert len(asc_cells) == 5
    checked_fills = 0
    for cell in asc_cells:
        assert cell["primary_route"] == "event", (
            f"{cell['cell']} must run on the fidelity event route")
        run = _primary_run(cell)
        assert run["status"] == "RUN" and run["contrast"]["status"] == "VALID"
        trace = run["arms"]["M4_CAL"].get("evaluator_trace") or {}
        assert int(trace.get("event_account_runs", 0)) >= 1, (
            f"{cell['cell']} event scorer ran no QuantBT account")
        for arm_name in PRIMARY_ARMS:
            arm = run["arms"][arm_name]
            account = arm["account"]
            assert account.get("status") == "EVALUATED", (
                f"{cell['cell']}:{arm_name} event account status "
                f"{account.get('status')!r}")
            assert account.get("fills_source") == "integration.event_account.run_event_account"
            fills = account.get("fills")
            assert isinstance(fills, list) and fills, (
                f"{cell['cell']}:{arm_name} has a null/empty per-fill ledger")
            assert account.get("fill_count") == len(fills)
            assert account.get("engine_fill_count") == len(fills)
            for fill in fills:
                for key in ("bar_index", "side", "qty", "price", "fee"):
                    assert key in fill, f"{cell['cell']}:{arm_name} fill missing {key}"
            checked_fills += len(fills)
    assert checked_fills >= 5 * 2, "the per-fill ledger denominator collapsed"
    sc = next(cell for cell in full["cells"] if cell["cell"] == "A-SC/BTCUSDT")
    assert sc["registered_route"] == "endpoint"
    assert sc["primary_route"] == "event"
    deviations = [run for run in sc["runs"]
                  if run["route_role"] == "REGISTERED_DEVIATION"]
    assert len(deviations) == 1, "the registered endpoint deviation was not retained"
    endpoint = deviations[0]
    assert endpoint["route"] == "endpoint"
    assert endpoint["contrast"]["implementation_fidelity"] == "DEVIATED"
    endpoint_account = endpoint["arms"]["M4_CAL"]["account"]
    assert endpoint_account["fills_source"] == "engine_native_vectorized_no_per_fill_records"
    assert endpoint_account["fill_count"] == 0
    sc_coverage = next(cell for cell in coverage["cells"] if cell["cell"] == "A-SC/BTCUSDT")
    assert sc_coverage["coverage_status"] == "RUN_VALID"
    assert sc_coverage["route"] == "event"
    assert [d["route"] for d in sc_coverage["run_result"]["route_deviations"]] == [
        "endpoint"]


def test_rf04_coverage_20_unique_statuses_with_reasons_and_no_fabricated_equity(lab_root):
    coverage = _load(lab_root, "cell_coverage.json")
    full = _load(lab_root, "paired_discovery_full.json")
    cells = coverage["cells"]
    assert len(cells) == 20
    names = [cell["cell"] for cell in cells]
    assert len(set(names)) == 20
    assert set(coverage["status_vocabulary"]) == STATUS_VOCABULARY
    assert coverage["counts"]["planned_cells"] == 20
    assert sum(coverage["counts"][status] for status in STATUS_VOCABULARY) == 20
    full_cells = {cell["cell"]: cell for cell in full["cells"]}
    executed = {cell["cell"] for cell in cells if cell["executed"]}
    assert executed == set(full_cells)
    for cell in cells:
        assert cell["coverage_status"] in STATUS_VOCABULARY
        assert cell["reason"].strip(), f"{cell['cell']} has no reason"
        assert cell["evidence_ref"].strip() and cell["evidence_refs"]
        if cell["coverage_status"] == "NOT_RUN_BUDGET":
            assert "budget" in cell["reason"].lower(), (
                f"{cell['cell']} is NOT_RUN_BUDGET without a budget reason")
        if cell["coverage_status"] in ("NOT_RUN", "NOT_RUN_BUDGET"):
            assert cell["reason"].strip(), f"{cell['cell']} has no non-run reason"
        if not cell["executed"]:
            assert cell["run_result"] is None
            assert cell["account_metrics"] is None, (
                f"{cell['cell']} must not carry equity for a non-run")
            assert cell["account_metrics_reason"].strip()
            assert cell["run_result_reason"].strip()
            continue
        assert cell["account_metrics"] is not None
        artifact = full_cells[cell["cell"]]
        primary = _primary_run(artifact)
        for arm_name, metrics in cell["account_metrics"].items():
            if arm_name not in primary["arms"]:
                continue
            source_account = primary["arms"][arm_name]["account"] or {}
            assert metrics["equity_last"] == source_account["equity_last"]
            assert metrics["num_trades"] == (
                source_account.get("engine_report") or {}).get("num_trades")
    for cell in cells:
        alpha = cell["cell"].split("/")[0]
        if alpha in BLOCKED_ALPHAS:
            assert cell["coverage_status"] == "BLOCKED_CAPABILITY", (
                f"{cell['cell']} is not allowed to leave BLOCKED_CAPABILITY here")
            assert cell["account_metrics"] is None
