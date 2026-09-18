#!/usr/bin/env python
"""Render reports/data_eligibility.md from the committed LAB-03 artifacts.

Reads only committed JSON. It never recomputes anything, so the document cannot
drift from the evidence it describes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))
CONFIGS = LAB_ROOT / "configs"


def load(name: str) -> dict:
    return json.loads((CONFIGS / name).read_text())


def main() -> int:
    inventory = load("data_product_inventory.json")
    eligibility = load("data_eligibility.json")
    schema = load("feature_schema.json")
    availability = load("availability_rules.json")
    enrichment = load("enrichment_inventory.json")
    registry = load("instrument_registry.json")
    effect = load("minimum_economic_effect.json")
    qualification = load("market_qualification.json")
    manifest = json.loads((LAB_ROOT / "snapshots" / "server_core_v1" / "manifest.json").read_text())

    lines: list[str] = []
    add = lines.append
    add("# Data eligibility — LAB-03")
    add("")
    add(f"Snapshot `{manifest['snapshot_id']}` · {manifest['file_count']} partitions · "
        f"{manifest['total_rows']:,} rows · {manifest['total_bytes'] / 1e6:.0f} MB · "
        f"{manifest['closed_partitions']} closed / {manifest['open_partitions']} open")
    add("")
    add("## 1. What the storage actually contains")
    add("")
    add("| Product | Symbols present | Symbols absent |")
    add("|---|---|---|")
    for pid, rec in inventory["products"].items():
        present = ", ".join(sorted(rec["coverage_by_symbol"])) or "—"
        absent = ", ".join(rec["trade_symbols_absent"]) or "—"
        add(f"| `{pid}` | {present} | {absent} |")
    add("")
    add("Products the cohorts wanted and that do **not** exist here:")
    add("")
    for name, rec in inventory["expected_but_absent"].items():
        add(f"- **`{name}`** — {rec['consequence']}")
    add("")
    add("## 2. Cohorts, reported separately")
    add("")
    add("| Cohort | Members | Common period | Status |")
    add("|---|---|---|---|")
    for name, rec in eligibility["cohorts"].items():
        period = " → ".join(rec["common_period"]) if rec["common_period"] else "—"
        add(f"| {name} | {rec['member_count']} ({', '.join(rec['members']) or '—'}) | {period} | "
            f"{rec['status']} |")
    add("")
    add(f"> {eligibility['no_intersection_collapse']}")
    add("")
    add("## 3. Usable interval per symbol")
    add("")
    add("| Symbol | Data starts | First decision bar (after warmup) | Ends |")
    add("|---|---|---|---|")
    for symbol, rec in eligibility["per_symbol"].items():
        add(f"| {symbol} | {rec['data_start']} | {rec['first_decision_bar']} | {rec['data_end']} |")
    add("")
    add(f"Five-symbol common period: **{' → '.join(eligibility['five_symbol_common_period'])}** "
        f"(it begins at SOLUSDT's listing). Each symbol's longest history is reported separately; "
        "returns are never back-filled with zeros before listing.")
    add("")
    add("## 4. Availability")
    add("")
    add("- Bar close is **derived** as `time + interval`. The stored `close_time` column is a "
        "diagnostic only.")
    add("- `available_at` = `bar_close + publication_delay`.")
    add("- Book snapshots use their real `sample_time`, not the hour label.")
    add(f"- Funding: **{availability['funding']['status']}** — {availability['funding']['policy']}")
    add("")
    add("## 5. Feature schema")
    add("")
    add(f"Regime observation interval: **{schema['regime_observation_interval']}**. "
        f"Primary core: **{schema['primary_core_count']} features** "
        f"(guide budget 8–12, respected = {schema['budget_respected']}).")
    add("")
    add("| Tier | Features | Coverage |")
    add("|---|---|---|")
    for tier, members in schema["feature_tiers"].items():
        active = [f for f in members if f in schema["scaler_active_features"]]
        if not active:
            continue
        cov = schema["coverage_by_feature"]
        symbols = sorted({s for f in active for s in cov[f]["symbols_with_any_data"]})
        add(f"| {tier} | {', '.join(active)} | {', '.join(symbols)} |")
    add("")
    add(f"> {schema['tier_rule']}")
    add("")
    if schema["dropped_features"]:
        add("Dropped by the scaler:")
        add("")
        for name, reason in schema["dropped_features"].items():
            add(f"- `{name}` — {reason}")
        add("")
    add(f"Scaler fitted on **{schema['scaler']['training_range'][0]} → "
        f"{schema['scaler']['training_range'][1]}** ({schema['scaler']['fitted_on_rows']:,} rows), "
        f"{schema['scaler']['policy']}.")
    add("")
    add("## 6. Instrument metadata (inferred from the snapshot)")
    add("")
    add("| Symbol | Tick sizes observed | Quantity steps observed | Stable? |")
    add("|---|---|---|---|")
    for symbol, rec in registry["instruments"].items():
        add(f"| {symbol} | {rec['tick_sizes_observed']} | {rec['qty_steps_observed']} | "
            f"tick={rec['tick_stable']}, qty={rec['qty_step_stable']} |")
    add("")
    add(f"Registry digest `{registry['registry_digest'][:24]}`. "
        f"Unstable quantity step: {registry['quantity_step_unstable_symbols']}.")
    add("")
    add("## 7. Minimum economic effect")
    add("")
    add(f"**{effect['minimum_daily_net_return_bps']:.3f} bps per day**, derived as "
        f"`{effect['derivation']['formula']}` from a {effect['derivation']['round_trip_cost'] * 1e4:.0f} bps "
        f"round trip, a {effect['derivation']['cost_uncertainty_per_round_trip'] * 1e4:.0f} bps "
        f"cost-stress band and {effect['derivation']['busiest_alpha_round_trips_per_day']:.3f} "
        f"round trips per day for the busiest alpha.")
    add("")
    add(f"> {effect['rule']}")
    add("")
    add("## 8. Market adapter qualification")
    add("")
    add(f"{qualification['cells_qualified']}/{qualification['cells_attempted']} cells qualified on "
        f"real bars from {qualification['slice_start']} "
        f"({qualification['slice_bars']} bars, {qualification['data_role']} role).")
    add("")
    add(f"> {qualification['slice_policy']}")
    add("")
    add("## 9. Enrichment")
    add("")
    add(f"Acquired: **{enrichment['acquired'] or 'none'}**. "
        f"Primary runs without it: {enrichment['primary_runs_without_it']}.")
    add("")
    for name, rec in enrichment["sources"].items():
        add(f"- `{name}` — {rec['status']}: {rec['usage_rule']}")
    add("")
    add("## 10. What this does not establish")
    add("")
    add("- No backtest has been run and no arm has been compared. Nothing here is evidence about edge.")
    add("- The liquidity cohort has no data inside the development window, so `g4_spread_bps` "
        "cannot be scaled and the cohort cannot enter the primary model.")
    add("- Funding does not exist in this storage; every primary run is a labelled no-funding cohort.")
    add("- Instrument metadata is INFERRED from observed granularity, not read from venue metadata.")
    add("")

    target = LAB_ROOT / "reports" / "data_eligibility.md"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {target} ({len(lines)} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
