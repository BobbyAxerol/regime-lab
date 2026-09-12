#!/usr/bin/env python
"""LAB-03 L03.1 + L03.2 — inventory storage and freeze the declared snapshot."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.data.inventory import build_inventory  # noqa: E402
from crypto_regime_lab.data.snapshot import DEFAULT_SCOPE, take_snapshot, verify_snapshot  # noqa: E402
from crypto_regime_lab.evidence.manifest import EvidenceWriter  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"
SNAPSHOT_ID = "server_core_v1"
STORAGE = "/root/bobby/pool_alpha/alphas_storage/_get_data/storage"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repin", action="store_true",
        help="re-pin an existing snapshot. Without this a snapshot whose manifest still "
             "verifies is left alone: re-reading it while the collector appends produces a "
             "NEW manifest, which silently re-registers the read-lock the study is pinned to.")
    parser.add_argument("--study", default=None, help="accepted for the guide 13.5 CLI contract")
    args = parser.parse_args(argv)

    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    policy.assert_lab_marker_ok(STUDY_ID)
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    pinned = policy.lab_root / "snapshots" / SNAPSHOT_ID / "manifest.json"
    if pinned.is_file() and not args.repin:
        import json as _json

        existing = _json.loads(pinned.read_text())
        state = verify_snapshot(existing, check_sources=False)
        print(f"snapshot {SNAPSHOT_ID} is already pinned "
              f"({existing['file_count']} files, {existing['total_rows']:,} rows, ingested "
              f"{existing['ingest_finished_utc'][:19]}Z)")
        print(f"lab-side integrity : {state['status']} "
              f"({len(state['snapshot_files_changed'])} files changed, "
              f"{len(state['missing'])} missing)")
        print("REFUSED to re-pin. Re-reading the source while the collector appends writes a NEW "
              "manifest and re-registers the read-lock this study declares. Pass --repin to do "
              "it deliberately.")
        return 0 if state["status"] != "SNAPSHOT_CORRUPT" else 1

    with writer.attempt("L03.1.inventory") as att:
        inventory = build_inventory(
            STORAGE, policy.lab_root / "vendor_readonly" / "loader_snapshot" / "data_loader.py")
        att.detail = {"products": len(inventory["products"]),
                      "absent": list(inventory["expected_but_absent"])}
    writer.write_config("data_product_inventory.json", inventory)
    writer.write_json("data_product_inventory.json", inventory, schema=inventory["schema"])

    with writer.attempt("L03.2.snapshot") as att:
        manifest = take_snapshot(policy, STORAGE, SNAPSHOT_ID, scope=DEFAULT_SCOPE)
        att.detail = {"files": manifest["file_count"], "rows": manifest["total_rows"]}
    manifest_path = policy.resolve_write_target(
        policy.lab_root / "snapshots" / SNAPSHOT_ID / "manifest.json")
    import json

    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    writer.write_json(f"snapshots/{SNAPSHOT_ID}/manifest.json", manifest,
                      schema=manifest["schema"])

    with writer.attempt("L03.2.verify_read_lock") as att:
        verification = verify_snapshot(manifest)
        att.detail = {"status": verification["status"]}
    writer.write_json("snapshot_verification.json", verification, schema=verification["schema"])

    print(f"products inventoried : {len(inventory['products'])}")
    for pid, rec in inventory["products"].items():
        print(f"   {pid:<38} present={len(rec['coverage_by_symbol'])}/5 "
              f"absent={rec['trade_symbols_absent']}")
    print(f"absent products      : {list(inventory['expected_but_absent'])}")
    print(f"snapshot files       : {manifest['file_count']}  rows={manifest['total_rows']:,}  "
          f"{manifest['total_bytes'] / 1e6:.0f}MB")
    print(f"closed / open        : {manifest['closed_partitions']} / {manifest['open_partitions']}")
    print(f"read-lock            : {verification['status']}")
    print(f"evidence -> {writer.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
