"""Every public symbol must be reachable, and the ones kept must be pinned.

The lab has now shipped the same defect three times: a function written, wired
into nothing, and left looking like a deliverable. M0 was the first, then
``stress_overlay`` / ``source_transition_report`` / ``relabel_states``, then a
handful of helpers from the earlier phases. So the check is a test rather than a
habit.

Four superseded functions were REMOVED rather than pinned, because pinning dead
code just makes it look alive:

* ``alphas.golden.drive_with_fills`` — a single forward pass, which LAB-02 proved
  stalls after one staged entry because protective exits are the ENGINE's fills.
  ``drive_with_engine_fills`` replaced it and keeping the broken one invited its use.
* ``safety.process.apply_resource_limits`` — the budget is enforced inside the
  bwrap worker by ``sandbox.run_isolated_python(memory_gib=...)``, which is what
  T07 actually exercises.
* ``safety.sandbox.isolated_env_for_probe`` — superseded by ``lab_worker_env``.
* ``selector.schema_distance.pairwise_distances`` — written in LAB-04, never used.
"""

from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

LAB_ROOT = Path(__file__).resolve().parent.parent
PKG = LAB_ROOT / "src" / "crypto_regime_lab"

REMOVED = {
    "drive_with_fills": "alphas/golden.py",
    "apply_resource_limits": "safety/process.py",
    "isolated_env_for_probe": "safety/sandbox.py",
    "pairwise_distances": "selector/schema_distance.py",
}


def _referenced_names() -> set[str]:
    """Every NAME touched anywhere — catches tuples, defaults and ``fn=`` handoffs
    that a call-graph walk alone would miss."""
    names: set[str] = set()
    roots = [PKG, LAB_ROOT / "scripts", LAB_ROOT / "tests"]
    for root in roots:
        for path in root.rglob("*.py"):
            if "raw-supplied" in str(path):
                continue
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Name):
                    names.add(node.id)
                elif isinstance(node, ast.Attribute):
                    names.add(node.attr)
    return names


def test_no_public_symbol_is_unreachable():
    referenced = _referenced_names()
    orphans = []
    for path in PKG.rglob("*.py"):
        if path.name == "__init__.py" or "raw-supplied" in str(path):
            continue
        for node in ast.parse(path.read_text()).body:
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)) \
                    and not node.name.startswith("_") \
                    and node.name not in referenced:
                orphans.append(f"{path.relative_to(PKG)}:{node.name}")
    assert orphans == [], (
        "these public symbols are defined but nothing reaches them. Either wire them into a "
        f"runner, pin them with a test, or delete them: {orphans}")


def test_the_superseded_functions_are_gone_not_merely_unused():
    for name, where in REMOVED.items():
        source = (PKG / where).read_text()
        assert f"def {name}" not in source, (
            f"{name} is back in {where}; it was removed for a reason recorded in this file")


def test_the_replacement_for_the_removed_fill_driver_still_exists():
    """Deleting the broken driver is only safe while the working one is present."""
    source = (PKG / "alphas" / "golden.py").read_text()
    assert "def drive_with_engine_fills" in source
    assert "FIXED POINT" in source


# ---------------------------------------------------------------------------
# the helpers that were kept: pin what each one promises
# ---------------------------------------------------------------------------

def test_relative_spread_returns_nan_for_a_missing_snapshot():
    """Its docstring promises this: a missing snapshot is NaN, never a zero spread."""
    from crypto_regime_lab.data.features import relative_spread

    out = relative_spread(pd.Series([10.0, np.nan, 4.0]))
    assert np.isnan(out.iloc[1]), "a missing book snapshot must not read as a tight spread"
    assert out.iloc[0] == pytest.approx(10.0), "the input is already in basis points"
    assert out.dtype == np.float64, "the cast to float64 is the point: an int column would make "\
        "a missing snapshot impossible to represent"


def test_oi_notional_vs_quantity_separates_price_from_size():
    from crypto_regime_lab.data.features import oi_notional_vs_quantity

    quantity = pd.Series([100.0, 100.0, 200.0])
    value = pd.Series([100.0 * 50, 100.0 * 60, 200.0 * 60])
    implied = oi_notional_vs_quantity(quantity, value)
    assert implied.iloc[0] == pytest.approx(50.0)
    assert implied.iloc[1] == pytest.approx(60.0), "a pure price move must show in the ratio"
    assert implied.iloc[2] == pytest.approx(60.0), "a pure size move must NOT"


def test_range_over_volume_is_finite_and_masks_a_zero_denominator():
    from crypto_regime_lab.data.features import range_over_volume

    high = pd.Series([10.0, 10.0, 10.0, 10.0])
    low = pd.Series([9.0, 9.0, 9.0, 9.0])
    volume = pd.Series([0.0, 5.0, 5.0, 5.0])
    out = range_over_volume(high, low, volume, 2)
    assert not np.isinf(out).any(), "a zero denominator must be masked, not turned into inf"


def test_findings_accessors_agree_with_the_registry():
    from crypto_regime_lab.alphas.findings import (FINDINGS, SEMANTIC_DELTAS, deltas_for,
                                                   findings_for, findings_index)

    index = findings_index()
    assert len(index) == len(FINDINGS)
    for alpha in ("A-SC", "A-HMA", "A-VWAP", "A-HASH"):
        assert findings_for(alpha) == [f for f in FINDINGS if f.alpha_id == alpha]
        assert deltas_for(alpha) == [d for d in SEMANTIC_DELTAS if d.alpha_id == alpha]
    assert findings_for("A-HASH"), "A-HASH is the blocked alpha; it must carry findings"


def test_exit_reason_covers_the_engine_reasons_the_lab_reads():
    from crypto_regime_lab.alphas.contracts import ExitReason

    values = {e.value for e in ExitReason}
    for reason in ("stop_loss", "take_profit"):
        assert reason in values, (
            f"the evaluator classifies engine fills by '{reason}'; the enum must carry it")


def test_panel_tier_columns_only_returns_columns_that_exist():
    from crypto_regime_lab.data.panel import FEATURE_TIERS, tier_columns

    frame = pd.DataFrame({"g1_rv_6": [1.0], "not_a_feature": [2.0]})
    for tier in FEATURE_TIERS:
        columns = tier_columns(frame, tier)
        assert set(columns) <= set(frame.columns)
        assert "not_a_feature" not in columns


def test_symbol_panel_carries_its_symbol_and_frame():
    from crypto_regime_lab.data.panel import SymbolPanel

    panel = SymbolPanel(symbol="BTCUSDT", frame=pd.DataFrame({"g1_rv_6": [1.0]}))
    assert panel.symbol == "BTCUSDT"
    assert len(panel.frame) == 1
    assert panel.quality == [] and panel.notes == [], (
        "quality and notes default to empty lists, not to None: a panel with no recorded "
        "quality finding is different from a panel that was never checked")
