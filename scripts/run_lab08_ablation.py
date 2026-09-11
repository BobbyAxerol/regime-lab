#!/usr/bin/env python
"""L08.4 / L08.5 — the data-cohort ablation and the complexity ladder.

L08.4 asks whether the derivatives and liquidity cohorts buy anything the
server core does not already have, ON COMPARABLE INTERVALS. That last clause is
the whole difficulty: each cohort covers a different span and a different set of
symbols, so a naive comparison would credit a feature group for the window it
happens to cover. Every comparison here is run on the intersection.

L08.5 asks the same question about model complexity rather than data, and the
guide is explicit that a proposal must state its question, its expected failure
and its stop condition before it runs -- so each rung declares those.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter, utc_now_iso  # noqa: E402
from crypto_regime_lab.regime.ablation import variance_resolved  # noqa: E402
from crypto_regime_lab.regime.causality import apply_scaler, fit_scaler  # noqa: E402
from crypto_regime_lab.regime.jump_model import (  # noqa: E402
    forward_filter,
    loss_matrix,
    multi_start_fit,
)
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"
SNAPSHOT_ID = "server_core_v1"
CONFIGS = LAB_ROOT / "configs"
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT")
DEV_START, DEV_END = "2020-01-01", "2023-12-31"
SEEDS = (11, 23, 37, 51)

#: cohort -> (the feature COLUMNS it adds beyond the core, why the guide wants it)
#:
#: The liquidity tier holds two features with completely different provenance,
#: and merging them hides the finding. `g4_log_amihud_30` is computed from the
#: perpetual bars and exists for every symbol; `g4_spread_bps` is the only
#: order-book feature and has 127 rows on BTCUSDT and ZERO everywhere else,
#: because that product is a rolling 30-day window that cannot accumulate
#: history. Calling their union "server_liquidity" scored an impact proxy and
#: reported it as the order-book cohort.
COHORTS = {
    "server_core": ((), "price, path shape, activity and market coordination"),
    "server_derivatives": (("g3_dlog_oi", "g3_return_oi_interaction", "g3_basis"),
                           "adds leverage and crowding from open interest AND basis"),
    # basis needs a SPOT leg, and spot was only ever collected for BTCUSDT, so the
    # full derivatives cohort is a BTC-only cohort. Requiring all three features
    # dropped ETHUSDT entirely even though it has 10,399 rows of open interest --
    # a cohort silently narrowed by one missing product is a coverage artefact,
    # so the OI half is scored separately and the omission is named.
    "server_derivatives_oi_only": (("g3_dlog_oi", "g3_return_oi_interaction"),
                                   "open interest and its return interaction, without basis "
                                   "(basis needs spot, collected for BTCUSDT only)"),
    "server_liquidity_impact": (("g4_log_amihud_30",),
                                "adds an impact proxy computed from the perpetual bars"),
    "server_liquidity_book": (("g4_spread_bps",),
                              "adds the spread, the only feature the order book supplies"),
}

#: L08.5 — each rung declares its question, expected failure and stop condition
#: BEFORE it runs, because a ladder without those is a sweep (guide L08.5).
LADDER = [
    {"rung": "M0", "model": "rule-based volatility/direction/activity thresholds",
     "question": "does an explainable rule already separate the states a jump model finds?",
     "expected_failure": "M0 tracks volatility only and misses coordinated moves",
     "stop_condition": "if M0 resolves as much variance out of fold as M1, M1 is unjustified"},
    {"rung": "M1", "model": "regularized discrete jump model",
     "question": "does persistence-penalised clustering resolve out-of-fold variance?",
     "expected_failure": "states are volatility buckets with extra steps",
     "stop_condition": "if M1 does not beat M0 out of fold, the ladder stops here"},
    {"rung": "M1S", "model": "sparse or group-regularized features",
     "question": "with many blocks, does sparsity find the ones that matter?",
     "expected_failure": "with three blocks there is nothing to select",
     "stop_condition": ("guide 8.1 scopes M1S to 'many blocks'; with 3 it is not attempted, and "
                        "guide 8.3 forbids writing a naive sparse objective without a pinned "
                        "research implementation")},
    {"rung": "M2", "model": "small HMM or GMM comparator",
     "question": "is the structure specific to a jump model or to the features?",
     "expected_failure": "a different family finds the same partition",
     "stop_condition": ("guide 8.1 declines to make M2 mandatory and warns against sweeping "
                        "model families; not attempted")},
]


def load_panel(symbol: str) -> pd.DataFrame:
    panel = pd.read_parquet(LAB_ROOT / "snapshots" / SNAPSHOT_ID / "panels" / f"{symbol}.parquet")
    panel["time"] = pd.to_datetime(panel["time"])
    return panel.sort_values("time").reset_index(drop=True)


def cohort_columns(panel: pd.DataFrame, extra: tuple[str, ...]) -> list[str]:
    """The core columns plus this cohort's own, each named explicitly.

    Naming the columns rather than matching a `g4` prefix is what separates the
    order-book feature from the impact proxy that merely shares its tier.
    """
    schema = json.loads((CONFIGS / "feature_schema.json").read_text())
    columns = [f"z_{f}" for f in schema["primary_core_features"] if f"z_{f}" in panel.columns]
    for feature in extra:
        for candidate in (f"z_{feature}", feature):
            if candidate in panel.columns:
                columns.append(candidate)
                break
    return columns


def usable(panel: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    frame = panel[(panel["time"] >= DEV_START) & (panel["time"] <= DEV_END)]
    return frame.dropna(subset=columns)[["time", *columns]].reset_index(drop=True)


def score(values: np.ndarray, *, n_states: int = 3, lambda_jump: float = 1.0) -> dict:
    """Variance resolved OUT OF FOLD, the same measure LAB-05 used."""
    cutoff = len(values) // 2
    scaler = fit_scaler(values[:cutoff])
    z = apply_scaler(values, scaler)
    weights = np.full(z.shape[1], 1.0 / z.shape[1])
    fit = multi_start_fit(z[:cutoff], weights, n_states=n_states,
                          lambda_jump=lambda_jump, seeds=SEEDS)
    centroids = np.asarray(fit["centroids"], dtype=float)
    # assign the HELD-OUT block with the fitted centroids, then measure how much
    # weighted variance that assignment removes. Scale-free, so the number means
    # the same thing whether a cohort reads 8 features or 11.
    held = z[cutoff:]
    # online_states: the causal assignment, the one a live provider would emit
    states = forward_filter(loss_matrix(held, centroids, weights), lambda_jump).online_states
    return {
        "observations": int(len(values)),
        "features": int(z.shape[1]),
        "variance_resolved_out_of_fold": float(
            variance_resolved(held, centroids, np.asarray(states), weights)),
    }


def comparable_interval(frames: dict[str, pd.DataFrame]) -> tuple[pd.Timestamp, pd.Timestamp]:
    """The span every cohort in this comparison actually covers."""
    start = max(f["time"].min() for f in frames.values())
    end = min(f["time"].max() for f in frames.values())
    return start, end


def main() -> int:
    policy = SandboxPolicy.load(CONFIGS / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    results = []
    for symbol in SYMBOLS:
        panel = load_panel(symbol)
        frames, columns = {}, {}
        for cohort, (groups, _) in COHORTS.items():
            cols = cohort_columns(panel, groups)
            frame = usable(panel, cols)
            if len(frame) < 500:
                frames[cohort] = frame
                columns[cohort] = cols
                continue
            frames[cohort] = frame
            columns[cohort] = cols

        available = {c: f for c, f in frames.items() if len(f) >= 500}
        entry = {"symbol": symbol,
                 "cohorts_available": sorted(available),
                 "cohorts_unavailable": {
                     c: {"rows": int(len(f)), "features": columns[c],
                         "reason": ("fewer than 500 usable rows on the development window. The "
                                    "collector never covered this product for this symbol, or "
                                    "the product is a rolling window that by design cannot "
                                    "accumulate history (LAB-03)")}
                     for c, f in frames.items() if c not in available}}

        if len(available) > 1:
            start, end = comparable_interval(available)
            entry["comparable_interval"] = [str(start), str(end)]
            entry["scores"] = {}
            for cohort, frame in available.items():
                clipped = frame[(frame["time"] >= start) & (frame["time"] <= end)]
                entry["scores"][cohort] = {
                    **score(clipped[columns[cohort]].to_numpy(float)),
                    "interval_rows": int(len(clipped)),
                }
            core = entry["scores"].get("server_core", {}).get("variance_resolved_out_of_fold")
            entry["gain_over_core"] = {
                cohort: (values["variance_resolved_out_of_fold"] - core)
                for cohort, values in entry["scores"].items() if core is not None
            }
            entry["reading"] = (
                "every cohort scored on the SAME rows. Scoring each on its own longest window "
                "would credit a feature group for the period it happens to cover")
        else:
            entry["comparable_interval"] = None
            entry["scores"] = {}
            entry["reading"] = ("only one cohort has usable data for this symbol, so there is "
                                "nothing to compare it against")
        results.append(entry)

    with writer.attempt("L08.4.data_ablation") as att:
        att.detail = {"symbols": len(results)}

    gains = [(r["symbol"], cohort, value)
             for r in results for cohort, value in (r.get("gain_over_core") or {}).items()
             if cohort != "server_core"]
    document = {
        "schema": "crypto_regime_lab.lab08_data_ablation.v1",
        "generated_at_utc": utc_now_iso(),
        "cohorts": {c: {"groups": list(g), "why": why} for c, (g, why) in COHORTS.items()},
        "per_symbol": results,
        "cohort_gains_over_core": [
            {"symbol": s, "cohort": c, "gain": v} for s, c, v in gains],
        "any_cohort_beats_core": any(v > 0 for _, _, v in gains),
        "comparable_interval_rule": (
            "a cohort is only compared on rows every cohort in that comparison has. Guide L08.4 "
            "forbids attributing an improvement that comes from a short recent window to a "
            "feature group"),
        "complexity_ladder": LADDER,
        "ladder_rule": ("each rung states its question, its expected failure and its stop "
                        "condition BEFORE it runs. A ladder without those is a sweep "
                        "(guide L08.5)"),
        "ladder_implemented": ["M0", "M1"],
        "ladder_declared_unbuilt": ["M1S", "M2"],
        "tuning_stage": "development only; K, lambda, training memory and cadence are never "
                        "tuned against the outer window",
    }
    writer.write_config("lab08_data_ablation.json", document)
    writer.write_json("lab08_data_ablation.json", document, schema=document["schema"])

    for entry in results:
        print(f"  {entry['symbol']:<9} available={entry['cohorts_available']}")
        if entry.get("comparable_interval"):
            print(f"      comparable interval {entry['comparable_interval'][0][:10]} .. "
                  f"{entry['comparable_interval'][1][:10]}")
            for cohort, values in entry["scores"].items():
                gain = entry["gain_over_core"][cohort]
                print(f"      {cohort:<20} var_resolved={values['variance_resolved_out_of_fold']:+.5f}"
                      f"  gain_over_core={gain:+.5f}  rows={values['interval_rows']}")
        for cohort, why in entry["cohorts_unavailable"].items():
            print(f"      {cohort:<20} UNAVAILABLE ({why['rows']} usable rows)")
    print(f"\nany cohort beats the core: {document['any_cohort_beats_core']}")
    print(f"evidence -> {writer.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
