#!/usr/bin/env python
"""Rebuild data_eligibility.json from the PINNED snapshot manifest.

Why this exists. ``configs/data_eligibility.json`` was written by
``build_feature_panels.py`` during the LAB-03 run, from the snapshot pass that
was current at that moment. ``server_core_v1`` was read three times while the
collector was still appending to the open 2026-09 partitions, so the eligibility
document ended up describing the 20:03:51 pass while the study pins the 20:12:26
manifest. Every CLOSED partition is identical between them -- the difference is
42 rows in open trailing partitions that no primary run may read -- so no result
moves. But an artifact that names a snapshot and does not reproduce from it is a
provenance defect, and this lab has already been bitten once by an artifact that
reported its own inputs wrongly (LAB-04's ``_observed_budget``).

Rebuilding is a pure function of the manifest, so this rewrites the document
without touching the 1.4 GB panels, and ``test_data_eligibility_reproduces_from_
the_pinned_manifest`` keeps it honest from here on.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.data.eligibility import cohort_report  # noqa: E402
from crypto_regime_lab.data.panel import MARKET_SYMBOLS  # noqa: E402
from crypto_regime_lab.data.provenance import DOCUMENTED_REVISIONS  # noqa: E402
from crypto_regime_lab.evidence.manifest import EvidenceWriter  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402

sys.path.insert(0, str(LAB_ROOT / "scripts"))
from build_feature_panels import DATA_ROLES, SNAPSHOT_ID, STUDY_ID, WARMUP_BARS  # noqa: E402


def build(manifest: dict) -> dict:
    """Exactly what build_feature_panels.py assembles, from the manifest alone."""
    eligibility = cohort_report(manifest, list(MARKET_SYMBOLS), WARMUP_BARS)
    eligibility["data_roles"] = DATA_ROLES
    eligibility["documented_revisions"] = DOCUMENTED_REVISIONS
    eligibility["repair_mask_column"] = "in_documented_repair_window"
    return eligibility


def main() -> int:
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    policy.assert_lab_marker_ok(STUDY_ID)
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    manifest = json.loads(
        (policy.lab_root / "snapshots" / SNAPSHOT_ID / "manifest.json").read_text())
    stale = json.loads((policy.lab_root / "configs" / "data_eligibility.json").read_text())
    fresh = build(manifest)

    with writer.attempt("L03.6.refresh_eligibility") as att:
        att.detail = {
            "manifest_ingest_finished_utc": manifest["ingest_finished_utc"],
            "was_stale": stale.get("manifest_total_rows") != manifest["total_rows"],
        }
    writer.write_config("data_eligibility.json", fresh)
    writer.write_json("data_eligibility.json", fresh, schema=fresh["schema"])

    print(f"manifest pinned    : {manifest['ingest_finished_utc']}  rows={manifest['total_rows']:,}")
    for symbol in MARKET_SYMBOLS:
        before = stale["per_symbol"][symbol]["products"]["crypto_binance_futures_1m"]["rows"]
        after = fresh["per_symbol"][symbol]["products"]["crypto_binance_futures_1m"]["rows"]
        flag = "" if before == after else f"  <- corrected {after - before:+d}"
        print(f"  {symbol:<9} perp 1m rows {before:>10,} -> {after:>10,}{flag}")
    print(f"evidence -> {writer.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
