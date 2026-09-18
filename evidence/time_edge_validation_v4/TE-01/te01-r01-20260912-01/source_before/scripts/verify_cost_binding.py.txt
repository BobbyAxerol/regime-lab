#!/usr/bin/env python
"""L09.6.1 — is the account charged the fee the study registered?

The study registers a ONE-WAY taker rate of 0.0004 ("Binance USD-M standard
taker rate"). The bridge passes it to the engine as `fee`. The installed
engine documents `fee` as a LEGACY ROUND-TRIP fee that it halves into the
canonical one-way `fee_rate`, and its default value happens to be 0.0004 as
well -- so the call looks right, runs without a warning, and charges half.

This is measured from real fills rather than read from the source, because the
source is what was already misread once. The measurement divides each fill's
recorded fee by its notional, which is the one-way rate the account actually
paid, and compares it to the registered rate.

Exit code is non-zero when they disagree. This is not a test of the engine --
the engine behaves exactly as documented -- it is a test of the lab's binding
to it.
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))
sys.path.insert(0, str(LAB_ROOT / "scripts"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter, utc_now_iso  # noqa: E402
from crypto_regime_lab.experiments import calendar_baseline as CB  # noqa: E402
from crypto_regime_lab.experiments.factorial import run_arm  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402
from run_lab08_factorial import bars_for, load  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"
#: one short, cheap window. The rate is a property of the account, not of the
#: window, so a probe does not need three years to measure it
PROBE = ("A-SC", "BTCUSDT", "2021-01-01", "2021-04-30")


def measure() -> dict:
    """Run one account and read the one-way fee rate off its fills."""
    alpha_id, symbol, start, end = PROBE
    protocol = load("lab08_pilot_protocol.json")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        bars = bars_for(alpha_id, symbol, protocol, {}, window=(start, end))
        result = run_arm("A", alpha_id, symbol, bars,
                         [{"cutoff": f"{start}T00:00:00+00:00",
                           "params": dict(CB.SEED_POINTS[alpha_id]), "point_id": "seed"}])
    fills = [f for f in result.fills if f["qty"] > 0 and f["price"] > 0]
    if not fills:
        return {"status": "NO_FILLS",
                "reason": "the probe window produced no fill, so nothing can be measured"}
    rates = sorted({round(f["fee"] / (f["qty"] * f["price"]), 10) for f in fills})
    equity_change = float(result.equity[-1] - result.equity[0])
    signed_cash = sum(f["side"] * f["qty"] * f["price"] for f in fills)
    total_fees = sum(f["fee"] for f in fills)
    gross = sum(f["qty"] * f["price"] for f in fills)
    residual = equity_change - (-signed_cash - total_fees)
    return {
        "status": "MEASURED",
        "probe": {"alpha_id": alpha_id, "symbol": symbol, "window": [start, end]},
        "fills": len(fills),
        "distinct_one_way_rates": rates,
        "measured_one_way_fee_rate": rates[0] if len(rates) == 1 else None,
        "gross_notional": gross,
        "total_fees_charged": total_fees,
        "cash_identity": {
            "equity_change": equity_change,
            "minus_signed_cash_minus_fees": -signed_cash - total_fees,
            "residual": residual,
            "relative_residual": abs(residual) / max(abs(equity_change), 1e-9),
            "identity": ("equity[-1] - equity[0] == -sum(side * qty * price) - sum(fee), with "
                         "side +1 for a buy. The account closes flat on the last bar, so there "
                         "is no open position to carry"),
            "holds": abs(residual) <= 1e-6 * max(abs(equity_change), 1.0),
        },
    }


def main() -> int:
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    registration = json.loads((LAB_ROOT / "configs" / "study_registration.json").read_text())
    declared = registration["execution"]["fee_funding_slippage_config"]
    registered_one_way = float(declared["taker_fee_rate"])

    with writer.attempt("L09.6.verify_cost_binding") as att:
        measurement = measure()
        att.detail = {"status": measurement["status"]}

    measured = measurement.get("measured_one_way_fee_rate")
    agrees = measured is not None and abs(measured - registered_one_way) <= 1e-12
    ratio = None if not measured else measured / registered_one_way

    document = {
        "schema": "crypto_regime_lab.cost_binding_verification.v1",
        "generated_at_utc": utc_now_iso(),
        "registered": {
            "one_way_taker_fee_rate": registered_one_way,
            "provenance": declared["fee_provenance"],
            "slippage": declared["slippage"],
            "source": "configs/study_registration.json, frozen at LAB-01",
        },
        "lab_binding": {
            "call": "run_intrabar(..., fee=ACCOUNT['taker_fee_rate'], slippage_bps=...)",
            "engine_semantic": ("quantbt endpoint docs: `fee` is a LEGACY ROUND-TRIP fee, "
                                "converted to the canonical one-way `fee_rate` at the endpoint "
                                "boundary when explicit `fee_rate` is omitted "
                                "(v2_fee_rate = fee / 2.0)"),
            "correct_binding_would_be": "fee_rate=<one-way rate>, or fee=2 * <one-way rate>",
        },
        "measurement": measurement,
        "verdict": {
            "binding_charges_the_registered_rate": bool(agrees),
            "measured_over_registered": ratio,
            "finding": (None if agrees else
                        "the account is charged HALF the registered one-way taker fee, because "
                        "the registered one-way rate is passed into a round-trip parameter. The "
                        "engine behaves exactly as documented; the lab's binding to it does not"),
            "direction": (None if agrees else
                          "flattering: every account in every phase paid less than the study "
                          "declared, so absolute returns are overstated"),
            "why_it_was_not_caught_earlier": (
                None if agrees else
                "the engine's default for `fee` is 0.0004, which is also the registered one-way "
                "rate, so the call looked correct and produced no warning. LAB-01 recorded the "
                "SIGNATURE in api_binding_map.json and never probed the SEMANTIC -- the exact "
                "failure the guide's 'never assume a signature' rule names"),
        },
    }
    writer.write_config("cost_binding_verification.json", document)
    writer.write_json("cost_binding_verification.json", document, schema=document["schema"])

    print(f"registered one-way taker fee : {registered_one_way}")
    print(f"measured one-way fee rate    : {measured}")
    print(f"ratio measured/registered    : {ratio}")
    print(f"cash identity holds          : {measurement.get('cash_identity', {}).get('holds')} "
          f"(residual {measurement.get('cash_identity', {}).get('residual')})")
    print(f"binding agrees               : {agrees}")
    if not agrees:
        print(f"  FINDING: {document['verdict']['finding']}")
    print(f"evidence -> {writer.run_dir}")
    return 0 if agrees else 2


if __name__ == "__main__":
    raise SystemExit(main())
