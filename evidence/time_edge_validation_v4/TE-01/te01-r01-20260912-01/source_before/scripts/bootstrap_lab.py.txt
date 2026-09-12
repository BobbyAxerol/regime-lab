#!/usr/bin/env python
"""LAB-01 bootstrap: snapshot sources, pin the baseline, build the API map.

Writes only inside LAB_ROOT. Reads only the declared protected roots. Never
imports from a protected source tree — QuantBT comes from the lab venv install.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter, environment_fingerprint, utc_now_iso  # noqa: E402
from crypto_regime_lab.quantbt_bridge.capabilities import InstalledQuantBT, build_api_binding_map_v2  # noqa: E402
from crypto_regime_lab.safety import archive as archive_mod  # noqa: E402
from crypto_regime_lab.safety.process import become_process_group_leader  # noqa: E402
from crypto_regime_lab.safety.paths import (  # noqa: E402
    SandboxPolicy, copy_readonly_snapshot, manifest_directory, sha256_file,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap the crypto regime lab (LAB-01)")
    parser.add_argument("--lab-root", default=str(LAB_ROOT))
    parser.add_argument("--study-id", default="crypto_regime_timeedge_v2")
    args = parser.parse_args()

    policy = SandboxPolicy.load(Path(args.lab_root) / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    policy.assert_lab_marker_ok(args.study_id)
    become_process_group_leader()
    writer = EvidenceWriter.open(policy, study_id=args.study_id)
    print(f"lab_run_id = {writer.lab_run_id}")

    alpha_src = next(p for p in policy.protected_roots if p.name == "alpha_to_tes_regime_model")

    # --- L01.2 snapshot the four alphas -------------------------------------
    with writer.attempt("L01.2.snapshot_alphas") as att:
        verification = archive_mod.verify_alpha_files(alpha_src, policy)
        archive_mod.assert_alpha_sources_ok(verification)
        snapshots = []
        for filename, record in verification["files"].items():
            snapshots.append(
                copy_readonly_snapshot(
                    record["path"],
                    policy.lab_root / "vendor_readonly" / "alphas_raw" / filename,
                    policy,
                    expected_sha256=archive_mod.ALLOWED_ALPHA_FILES[filename],
                )
            )
        att.detail = {"snapshot_count": len(snapshots)}
    alpha_snapshot_record = writer.write_json(
        "alpha_source_snapshot.json",
        {
            "verification": verification,
            "snapshots": snapshots,
            "archive_present_on_disk": False,
            "archive_note": (
                "The original alpha_to_tes_regime_model.zip is not present on this host; only the "
                "extracted four .py files are. Archive-level admission control (T03) is therefore "
                "exercised against synthetic hostile fixtures, and file-level identity (T04) is "
                "verified against the SHA-256 values published in guide section 1.1."
            ),
            "expected_archive_sha256": archive_mod.EXPECTED_ARCHIVE_SHA256,
        },
        schema="crypto_regime_lab.alpha_source_snapshot.v1",
    )

    # --- L01.2 snapshot the historical loader (read-only reference) ----------
    with writer.attempt("L01.2.snapshot_loader") as att:
        loader_src = next(p for p in policy.protected_roots if p.name == "_get_data")
        loader_snapshot = copy_readonly_snapshot(
            loader_src / "data_loader.py",
            policy.lab_root / "vendor_readonly" / "loader_snapshot" / "data_loader.py",
            policy,
        )
        att.detail = {"sha256": loader_snapshot["sha256"]}

    # --- L01.3 environment identity and wheelhouse digests -------------------
    with writer.attempt("L01.3.pin_environment") as att:
        wheelhouse = policy.lab_root / "wheelhouse"
        wheels = {p.name: sha256_file(p) for p in sorted(wheelhouse.glob("*")) if p.is_file()}
        installed = InstalledQuantBT.load()
        env_record = {
            "environment": environment_fingerprint(),
            "quantbt_identity": installed.identity(),
            "wheelhouse": wheels,
            "venv_path": str(policy.lab_root / "environments" / "lab_venv"),
            "shared_parent_venv_untouched": "/root/bobby/pool_alpha/.venv",
            "baseline_target_from_guide": {"core": "1.1.1", "native": "0.4.2"},
        }
        core = installed.distributions.get("quantbt-engine")
        native = installed.distributions.get("quantbt-native")
        env_record["baseline_matches_guide"] = (core == "1.1.1" and native == "0.4.2")
        att.detail = {"core": core, "native": native, "matches_guide": env_record["baseline_matches_guide"]}
    env_artifact = writer.write_json("environment_baseline.json", env_record,
                                     schema="crypto_regime_lab.environment_baseline.v1")

    # --- L01.6 actual API map ------------------------------------------------
    with writer.attempt("L01.6.api_binding_map") as att:
        api_map = build_api_binding_map_v2(
            installed, loader_path=policy.lab_root / "vendor_readonly" / "loader_snapshot" / "data_loader.py"
        )
        att.detail = {"unresolved": api_map["unresolved"],
                      "unknown_counts": api_map["unknown_counts"],
                      "wfo_modes": api_map["wfo_modes"]["optimization_modes_found_in_source"]}
    api_artifact = writer.write_json("api_binding_map.json", api_map,
                                     schema="crypto_regime_lab.api_binding_map.v1")
    writer.write_config("api_binding_map.json", api_map)

    # --- L01.4 source integrity baseline ------------------------------------
    with writer.attempt("L01.4.source_integrity_baseline") as att:
        integrity = {
            str(alpha_src): manifest_directory(alpha_src, ("*.py",)),
            str(policy.lab_root / "vendor_readonly" / "alphas_raw"): manifest_directory(
                policy.lab_root / "vendor_readonly" / "alphas_raw", ("*.py",)
            ),
        }
        att.detail = {"roots": len(integrity)}
    integrity_artifact = writer.write_json(
        "source_integrity_baseline.json",
        {"manifests": integrity, "taken_at_utc": utc_now_iso()},
        schema="crypto_regime_lab.source_integrity.v1",
    )

    # --- lab marker ----------------------------------------------------------
    marker = {
        "schema": "crypto_regime_lab.lab_marker.v1",
        "study_id": args.study_id,
        "lab_root": str(policy.lab_root),
        "created_at_utc": utc_now_iso(),
        "bootstrap_lab_run_id": writer.lab_run_id,
        "guide": "QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md",
        "guide_sha256": sha256_file(policy.lab_root / "QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md"),
        "quantbt_source_of_truth": "PyPI wheel installed in environments/lab_venv (NOT /root/bobby/pool_alpha/quantbt)",
    }
    marker_path = policy.resolve_write_target(policy.lab_root / ".lab_marker.json")
    import json

    marker_path.write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")

    summary = {
        "lab_run_id": writer.lab_run_id,
        "artifacts": {
            "alpha_source_snapshot": alpha_snapshot_record,
            "environment_baseline": env_artifact,
            "api_binding_map": api_artifact,
            "source_integrity_baseline": integrity_artifact,
        },
        "marker": str(marker_path),
    }
    writer.write_json("bootstrap_summary.json", summary, schema="crypto_regime_lab.bootstrap_summary.v1")
    print(json.dumps({"status": "BOOTSTRAPPED", **{k: v for k, v in summary.items() if k != "artifacts"}}, indent=2))
    print(f"evidence -> {writer.run_dir}")
    return 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    raise SystemExit(main())
