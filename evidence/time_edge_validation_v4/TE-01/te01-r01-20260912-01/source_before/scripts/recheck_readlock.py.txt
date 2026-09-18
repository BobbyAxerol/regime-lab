#!/usr/bin/env python
"""Re-verify the read-lock before a phase runs, and record what drifted.

Run this at the start of any phase that consumes the snapshot. It is a gate, not
a report: a primary-core invalidation stops the phase.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.data.snapshot import verify_snapshot  # noqa: E402
from crypto_regime_lab.evidence.manifest import EvidenceWriter, utc_now_iso  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"
SNAPSHOT_ID = "server_core_v1"


def main() -> int:
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)
    manifest = json.loads((policy.lab_root / "snapshots" / SNAPSHOT_ID / "manifest.json").read_text())

    # deep=True: when a closed partition's digest moves, READ both files and
    # decide whether any measurement moved with it. A digest answers "same
    # bytes", not "same numbers", and the collector re-ingests closed months.
    with writer.attempt("readlock.recheck") as att:
        verification = verify_snapshot(manifest, deep=True)
        att.detail = {"status": verification["status"],
                      "primary_run_valid": verification["primary_run_valid"],
                      "products_invalidated": verification["products_invalidated"],
                      "content_revisions": len(verification["closed_partition_content_revisions"]),
                      "vintage_restamps": len(verification["closed_partition_vintage_restamps"])}
    verification["checked_at_utc"] = utc_now_iso()
    writer.write_config("readlock_verification.json", verification)
    writer.write_json("readlock_verification.json", verification,
                      schema=verification["schema"])

    print(f"status              : {verification['status']}")
    print(f"snapshot bytes      : "
          f"{'intact' if not verification['snapshot_files_changed'] else 'CHANGED'}")
    print(f"primary core products: {verification['primary_core_products']}")
    print(f"primary run valid   : {verification['primary_run_valid']}")
    for product, info in verification["drift_by_product"].items():
        print(f"  DRIFTED {product}: {info['closed_partitions_changed']} closed partitions "
              f"{info['partition_range'][0]}..{info['partition_range'][1]} "
              f"symbols={info['symbols']} in_primary_core={info['in_primary_core']}")
    restamps = verification["closed_partition_vintage_restamps"]
    revisions = verification["closed_partition_content_revisions"]
    if restamps or revisions:
        print(f"closed drift read   : {len(revisions)} content revisions, "
              f"{len(restamps)} ingest re-stamps (measurements proven identical)")
        for verdict in revisions:
            print(f"  REVISED {verdict['product_id']}/{verdict['symbol']} "
                  f"{verdict['partition']}: {verdict['reason']}")
    print(f"open trailing drift : {len(verification['open_partition_drift'])} "
          f"(expected: the collector appends)")
    print(f"rolling window drift: {len(verification['rolling_window_drift'])} "
          f"(expected: the product rewrites its own window)")
    print(f"evidence -> {writer.run_dir}")

    if not verification["primary_run_valid"]:
        print("GATE FAILED: a product the primary core reads drifted; re-register the snapshot")
        return 1
    if verification["products_invalidated"]:
        print("NOTE: cohorts reading the drifted products above are invalidated and must be "
              "re-registered before any claim that depends on them")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
