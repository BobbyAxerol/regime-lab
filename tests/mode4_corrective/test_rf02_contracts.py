"""RF-02 contract tests — repairs made in this phase, asserted on the new code.

These are green-on-arrival guards: each one pins a repair so a later change
cannot quietly undo it. The failing-before versions of A05 and A07 live in
`test_rf01_before_repairs.py` and now pass.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from crypto_regime_lab.alphas.a_hma import AdaptiveHmaEventAdapterV1, InfeasibleConfiguration
from crypto_regime_lab.alphas.base import MarketSlice
from crypto_regime_lab.selector.alpha_schemas import SEED_POINTS


def _market(n: int = 8) -> MarketSlice:
    close = np.full(n, 100.0)
    return MarketSlice(open=close.copy(), high=close + 0.5, low=close - 0.5, close=close,
                       volume=np.full(n, 1000.0),
                       index=pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC"))


def test_a05_a_legacy_sl_input_alias_migrates_explicitly():
    params = dict(SEED_POINTS["A-HMA"])
    params["sl_input"] = "Zone Distance"
    adapter = AdaptiveHmaEventAdapterV1(params, _market())
    assert adapter.sl_input == "One Distance Zone"
    assert adapter.sl_input_migrated_from == "Zone Distance"


def test_a05_an_unknown_sl_input_is_rejected_not_defaulted():
    params = dict(SEED_POINTS["A-HMA"])
    params["sl_input"] = "some invented zone"
    with pytest.raises(InfeasibleConfiguration):
        AdaptiveHmaEventAdapterV1(params, _market())


def test_rf02_route_registry_carries_the_canonical_stop_modes_and_four_alphas(lab_root):
    registry = json.loads(
        (lab_root / "evidence" / "corrective_mode4_v3" / "RF-02" / "alpha_route_registry.json")
        .read_text(encoding="utf-8"))
    assert set(registry["alphas"]) == {"A-SC", "A-HMA", "A-VWAP", "A-HASH"}
    repair = registry["a05_stop_mode_repair"]
    assert repair["silent_default_removed"] is True
    assert set(repair["canonical_enum"]) == {"One Distance Zone", "Half Distance Zone",
                                             "Last High/Low", "ATR Only"}
    choices = registry["alphas"]["A-HMA"]["schema"]["params"]["sl_input"]["choices"]
    assert set(choices) == set(repair["canonical_enum"])
    for alpha in registry["alphas"].values():
        assert alpha["route_status"] == "PENDING_QUALIFICATION"
        assert len(alpha["cell_status"]) == 5


# --- A01: bound fee route -------------------------------------------------

def test_a01_bound_fee_kwargs_translate_one_way_exactly_once():
    from crypto_regime_lab.quantbt_bridge.routes import bound_fee_kwargs

    bound = bound_fee_kwargs(0.0004)
    assert bound == {"fee": 0.0008, "fee_rate": 0.0004}
    assert bound["fee"] == pytest.approx(2.0 * bound["fee_rate"])


def test_a01_the_bound_route_charges_the_registered_one_way_rate():
    from crypto_regime_lab.quantbt_bridge.intent_tape import TapeBuild
    from crypto_regime_lab.quantbt_bridge.routes import realized_fee_rate, run_intrabar_route

    n = 10
    frame = pd.DataFrame({"open": np.full(n, 100.0), "high": np.full(n, 101.0),
                          "low": np.full(n, 99.0), "close": np.full(n, 100.0),
                          "volume": np.full(n, 1000.0)},
                         index=pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC"))
    tape = TapeBuild(np.r_[1.0, np.zeros(n - 1)], np.r_[1.0, np.zeros(n - 1)],
                     np.full(n, np.nan), np.full(n, np.nan), np.zeros(n, dtype=bool))
    out = run_intrabar_route(frame, tape, backend="reference", one_way_fee=0.0004,
                             slippage_bps=0.0, sizing_mode="fixed_notional",
                             unit_notional=2000.0)
    assert len(out["fills"]) >= 2, "the fixture must actually trade or it proves nothing"
    for fill in out["fills"]:
        assert realized_fee_rate(fill) == pytest.approx(0.0004, rel=1e-9), (
            f"fill charged {realized_fee_rate(fill)} one-way against the registered 0.0004")
    assert out["contract"]["bound"] == {"fee": 0.0008, "fee_rate": 0.0004}

