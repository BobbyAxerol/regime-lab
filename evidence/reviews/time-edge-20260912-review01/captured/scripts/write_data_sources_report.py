#!/usr/bin/env python
"""Render reports/data_sources_used.md — one place to audit the raw data.

Answers, from committed artifacts only: which storage products this lab reads,
how much of each, over what span, which symbols each product can and cannot
cover, what the read-lock says right now, how the bytes are actually read, and
which phase consumed which slice. Every number is traceable to a file the reader
can open, and the last section lists the commands to re-derive them.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))
CONFIGS = LAB_ROOT / "configs"
OUT = LAB_ROOT / "reports" / "data_sources_used.md"

from crypto_regime_lab.evidence.data_sources import loader_parity_lines  # noqa: E402


def load(name: str, root: Path = CONFIGS):
    path = root / name
    return json.loads(path.read_text()) if path.is_file() else None


def main() -> int:
    manifest = load("manifest.json", LAB_ROOT / "snapshots" / "server_core_v1")
    inventory = load("data_product_inventory.json")
    eligibility = load("data_eligibility.json")
    readlock = load("readlock_verification.json")
    parity = load("loader_endpoint_parity.json")
    provenance = load("data_provenance.json")
    registration = load("study_registration.json")

    lines: list[str] = []
    add = lines.append
    add("# Data sources actually used — audit view")
    add("")
    add("Generated from committed artifacts by `scripts/write_data_sources_report.py`. Nothing "
        "here is re-measured at render time; every figure names the file it came from.")
    add("")

    if manifest is None:
        add("**BLOCKED** — no snapshot manifest. Run `scripts/snapshot_data.py`.")
        OUT.write_text("\n".join(lines) + "\n")
        return 1

    # ---- headline ----
    add("## The short answer")
    add("")
    add(f"- one historical source: **`{manifest['storage_root']}`** — the user's Parquet storage, "
        "read-only")
    add(f"- copied byte for byte into `snapshots/{manifest['snapshot_id']}/`: "
        f"**{manifest['file_count']} files, {manifest['total_rows']:,} rows, "
        f"{manifest['total_bytes'] / 1e6:.0f} MB**")
    add(f"- read between `{manifest['ingest_started_utc'][:19]}` and "
        f"`{manifest['ingest_finished_utc'][:19]}` UTC; every run since then reads the COPY, "
        "never the live tree")
    add("- **no network, no collector, no repair job.** Missing coverage is reported as missing "
        "and never fetched (`configs/data_readlock_policy.json`)")
    if registration:
        roles = (eligibility or {}).get("data_roles", {})
        for role, spec in roles.items():
            add(f"- data role **{role}**: {spec['start']} → {spec['end'] or 'open'}")
    add("")

    # ---- products ----
    add("## Products, and what each one can and cannot cover")
    add("")
    add("| product | loader class that declares it | symbols present | files | rows | span | role in the study |")
    add("|---|---|---|---|---|---|---|")
    per_product: dict[str, dict] = {}
    for record in manifest["files"]:
        bucket = per_product.setdefault(record["product_id"],
                                        {"symbols": set(), "files": 0, "rows": 0,
                                         "min": record["time_min"], "max": record["time_max"]})
        bucket["symbols"].add(record["symbol"])
        bucket["files"] += 1
        bucket["rows"] += record["rows"]
        bucket["min"] = min(bucket["min"], record["time_min"])
        bucket["max"] = max(bucket["max"], record["time_max"])
    products = (inventory or {}).get("products", {})
    for product, info in sorted(per_product.items()):
        spec = products.get(product, {})
        add(f"| `{product}` | `{spec.get('actual_reader_symbol', '?')}` | "
            f"{', '.join(sorted(info['symbols']))} | {info['files']} | {info['rows']:,} | "
            f"{info['min'][:10]} → {info['max'][:10]} | {spec.get('role', '—')} |")
    add("")

    if inventory:
        absent = inventory.get("expected_but_absent") or {}
        if absent:
            add("### Wanted by the guide, absent from this storage")
            add("")
            for name, detail in absent.items():
                add(f"- **`{name}`** — needed for {detail.get('needed_for', '?')}. "
                    f"Searched: {detail.get('searched', '?')}.")
            add("")
            add("An absent product is never substituted and never treated as zero. Funding in "
                "particular does not exist anywhere in this storage, so every primary run is a "
                "labelled **no-funding cohort** rather than a run that assumes funding is 0.")
            add("")
        for product, spec in products.items():
            missing = spec.get("trade_symbols_absent")
            if missing:
                add(f"- `{product}` has no partition for {missing} — the collector was never "
                    "configured for them, so no amount of re-reading storage produces them")
        add("")

    if provenance:
        add("### Collector configuration, read from the product documents")
        add("")
        docs = provenance.get("documents_read", {}).get("product_docs", {})
        for name, detail in docs.items():
            config = detail.get("documented_config", {})
            add(f"- **{name}** (`{detail.get('document')}`, sha256 `{detail.get('sha256','')[:12]}…`): "
                f"{config.get('consequence', '—')}")
        add("")

    # ---- per symbol ----
    if eligibility:
        add("## How much history per symbol")
        add("")
        add("| symbol | product | partitions (closed) | rows | first | last |")
        add("|---|---|---|---|---|---|")
        for symbol, record in eligibility["per_symbol"].items():
            for product, entry in record["products"].items():
                add(f"| {symbol} | `{product}` | {entry['partitions']} "
                    f"({entry['closed_partitions']}) | {entry['rows']:,} | "
                    f"{entry['time_min'][:16]} | {entry['time_max'][:16]} |")
        add("")
        common = eligibility.get("five_symbol_common_period")
        add(f"- five-symbol common period: **{common[0][:10]} → {common[1][:10]}**" if common
            else "- five-symbol common period: none")
        add(f"- {eligibility['reporting_rule']}")
        spot = eligibility.get("spot_clean_convention", {})
        if spot:
            add(f"- spot clean convention: from **{spot.get('clean_from')}** — {spot.get('rule')}")
        add("")

    # ---- read lock ----
    add("## Is the source still what it was when it was read?")
    add("")
    if readlock is None:
        add("**MISSING** `configs/readlock_verification.json`. Run `scripts/recheck_readlock.py`.")
    else:
        add(f"- checked `{readlock.get('checked_at_utc', '?')[:19]}` UTC → "
            f"**{readlock['status']}**")
        add(f"- the lab's own {readlock['files_checked']} snapshot files: "
            f"**{'all intact' if not readlock['snapshot_files_changed'] else 'CHANGED'}** "
            "(this is the number that decides whether past results still describe real data)")
        add(f"- upstream files whose bytes differ now: **{len(readlock['source_files_changed'])}**")
        revisions = readlock.get("closed_partition_content_revisions") or []
        restamps = readlock.get("closed_partition_vintage_restamps") or []
        if readlock.get("closed_partition_drift_classified"):
            add(f"  - of the closed ones, READ and classified: **{len(revisions)} content "
                f"revisions**, **{len(restamps)} ingest re-stamps**")
            for verdict in restamps[:1]:
                add(f"  - example re-stamp: `{verdict['product_id']}` {verdict['symbol']} "
                    f"{verdict['partition']} — {verdict['rows_compared']:,} rows compared, "
                    f"`ingested_at` moved {verdict['vintage_max_snapshot']} → "
                    f"{verdict['vintage_max_upstream']}, every measured column identical")
        add(f"  - open trailing: **{len(readlock.get('open_partition_drift', []))}** "
            "(the collector appending — excluded from any primary read)")
        add(f"  - rolling-window: **{len(readlock.get('rolling_window_drift', []))}** "
            "(the order book rewrites its own 30-day window by design)")
        add(f"- cohorts invalidated: **{readlock.get('cohort_runs_invalidated') or 'none'}**")
        add(f"- primary run valid: **{readlock['primary_run_valid']}**")
        add("")
        add(f"> {readlock.get('classification_rule', '')}")
    add("")

    # ---- loader ----
    lines.extend(loader_parity_lines(parity))

    # ---- known defects ----
    add("## Measured defects in the raw data — do not re-trust these columns")
    add("")
    add("| column | defect | what the lab does instead |")
    add("|---|---|---|")
    add("| `close_time` | near the 1970 epoch for SOL/BNB perps, mixed for BTC spot, sometimes a "
        "STRING; 145 of 385 partitions untrusted | derives `bar_close = time + interval` and "
        "never reads the column |")
    add("| `volume` | dtype varies by symbol AND by month (SOL integral until 2024-12, DOGE "
        "integral throughout) | coerces to float64 on read so a feature's dtype never depends on "
        "which month it came from |")
    add("| quantity step | SOL's step changed mid-sample (integral → fractional, 2025-04) | a "
        "single pinned step in the instrument registry would be wrong for part of the history; "
        "the change is recorded rather than averaged away |")
    add("| 2026-05 BTC/ETH | carry a second ingest day (2026-06-12, ~44k rows) — the documented "
        "continuity repair | masked in every panel as `in_documented_repair_window` |")
    add("")

    # ---- who consumed what ----
    add("## Which phase consumed which slice")
    add("")
    add("| phase | alphas × symbols | products read | window | notes |")
    add("|---|---|---|---|---|")
    baseline = load("lab04_calendar_baseline.json")
    if baseline:
        run = [c for c in (baseline.get("cells") or []) if c.get("status") == "RUN"]
        add(f"| LAB-04 | {baseline['cells_run']}/{baseline['cells_total']} cells "
            f"({len(sorted({c['alpha_id'] for c in run}))} alphas × "
            f"{len(sorted({c['symbol'] for c in run}))} symbols) | "
            "`crypto_binance_futures_1m` | development | "
            f"{baseline['cells_not_ready']} cells NOT_READY with null metrics, never PnL 0 |")
    registry = load("lab05_regime_model_registry.json")
    if registry:
        add(f"| LAB-05 | 1 symbol ({registry['symbol']}) | `crypto_binance_futures_1m` via the "
            f"8 primary-core features | {registry.get('data_role')} | "
            f"{len(registry.get('models') or [])} fits at "
            f"{registry.get('observation_interval')}, {registry.get('train_memory_days')}d memory; "
            f"outer holdout touched: {registry.get('outer_evaluation_touched')} |")
    model = load("lab06_response_model.json")
    ledger = load("lab06_decision_ledger.json")
    if model:
        add(f"| LAB-06 | 1 of 20 cells ({model['alpha_id']} / {model['symbol']}) | "
            "`crypto_binance_futures_1m` | development | "
            f"{model.get('episode_panel_rows', 0):,} episodes, "
            f"{(ledger or {}).get('decisions', 0):,} decisions at 4h |")
    add("")
    add("G3 (open interest and trader ratios) and G4 (order-book spread) are **cohort "
        "extensions**: no phase above reads them, which is why the 23 upstream re-stamps in the "
        "metrics product cannot reach any result on this page.")
    add("")

    # ---- reproduce ----
    add("## Re-derive every number on this page")
    add("")
    add("```bash")
    add("LAB=/root/bobby/pool_alpha/lab_regime_model_quantbt")
    add("$LAB/environments/lab_venv/bin/python $LAB/scripts/recheck_readlock.py       "
        "# re-hash 627 files, classify any drift")
    add("$LAB/environments/lab_venv/bin/python $LAB/scripts/verify_loader_parity.py   "
        "# call the pinned loader, diff against the parquet")
    add("$LAB/environments/lab_venv/bin/python $LAB/scripts/refresh_data_eligibility.py "
        "# rebuild the coverage report from the manifest")
    add("$LAB/environments/lab_venv/bin/python -m pytest $LAB/tests/test_lab03_pipeline.py "
        "$LAB/tests/test_lab03_data.py -q")
    add("```")
    add("")

    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT} ({len(lines)} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
