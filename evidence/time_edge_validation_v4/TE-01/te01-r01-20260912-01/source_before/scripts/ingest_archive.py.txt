#!/usr/bin/env python
"""LAB-01 L01.2 (completed): ingest the ORIGINAL alpha archive as provenance.

Supersedes the earlier fallback that copied the four loose files out of
alphas_storage. Provenance now runs archive -> extraction -> lab copy, and the
loose files in alphas_storage are cross-checked against the archive rather than
being the source of truth.
"""

from __future__ import annotations

import argparse
import os
import stat
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter  # noqa: E402
from crypto_regime_lab.safety.archive import (  # noqa: E402
    ALLOWED_ALPHA_FILES, EXPECTED_ARCHIVE_SHA256, inspect_zip, safe_extract, verify_alpha_files,
)
from crypto_regime_lab.safety.paths import SafetyViolation, SandboxPolicy, sha256_file  # noqa: E402


def _make_writable(path: Path) -> None:
    if path.exists():
        os.chmod(path, stat.S_IWUSR | stat.S_IRUSR)


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest the original alpha archive")
    parser.add_argument("--archive", default=None,
                        help="source archive; defaults to the supplied zip, then the retained copy")
    parser.add_argument("--study-id", default="crypto_regime_timeedge_v2")
    args = parser.parse_args()

    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=args.study_id)
    retained_path = policy.lab_root / "vendor_readonly" / "alpha_zip_original.zip"
    supplied_path = policy.lab_root / "alpha_to_tes_regime_model.zip"
    if args.archive:
        archive = Path(args.archive).resolve()
        archive_source = "explicit --archive"
    elif supplied_path.is_file():
        archive = supplied_path.resolve()
        archive_source = "user-supplied archive at LAB_ROOT"
    elif retained_path.is_file():
        archive = retained_path.resolve()
        archive_source = "retained copy in vendor_readonly (supplied archive no longer at LAB_ROOT)"
    else:
        raise SafetyViolation(
            "no archive found: neither the supplied zip at LAB_ROOT nor a retained copy in "
            "vendor_readonly. Re-supply alpha_to_tes_regime_model.zip before running LAB-01."
        )
    print(f"archive source          : {archive_source}")

    with writer.attempt("L01.2.inspect_archive") as att:
        inspection = inspect_zip(archive, policy)
        record = inspection.as_record()
        if not record["archive_sha256_matches_guide"]:
            raise SafetyViolation(
                f"archive digest {record['archive_sha256']} != guide {EXPECTED_ARCHIVE_SHA256}; stop"
            )
        if not inspection.admissible:
            raise SafetyViolation(f"archive rejected: {inspection.rejections}")
        att.detail = {"entries": record["entry_count"], "admissible": True}

    # Keep the original archive itself as immutable provenance inside the lab.
    with writer.attempt("L01.2.retain_archive") as att:
        retained = policy.resolve_write_target(
            policy.lab_root / "vendor_readonly" / "alpha_zip_original.zip"
        )
        _make_writable(retained)
        if retained.resolve() != archive.resolve():
            retained.write_bytes(archive.read_bytes())
        retained_digest = sha256_file(retained)
        if retained_digest != record["archive_sha256"]:
            raise SafetyViolation("retained archive digest differs from the source archive")
        os.chmod(retained, 0o444)
        att.detail = {"sha256": retained_digest}

    with writer.attempt("L01.2.extract_archive") as att:
        dest = policy.lab_root / "vendor_readonly" / "alphas_raw"
        for name in ALLOWED_ALPHA_FILES:
            _make_writable(dest / name)
        extraction = safe_extract(archive, dest, policy, inspection)
        att.detail = {"extracted": len(extraction["extracted"])}

    # Cross-check: the loose copies in alphas_storage must be byte-identical to
    # the archive members. A difference is a provenance question, not a detail.
    with writer.attempt("L01.2.crosscheck_loose_copies") as att:
        loose_root = next(p for p in policy.protected_roots if p.name == "alpha_to_tes_regime_model")
        loose = verify_alpha_files(loose_root, policy)
        mismatches = [
            name for name, rec in loose["files"].items()
            if rec["sha256"] != ALLOWED_ALPHA_FILES[name]
        ]
        att.detail = {"loose_status": loose["status"], "mismatches": mismatches}

    report = {
        "archive_inspection": record,
        "retained_archive": {"path": str(retained), "sha256": retained_digest},
        "extraction": extraction,
        "loose_copy_crosscheck": {
            "source_dir": loose["source_dir"],
            "status": loose["status"],
            "identical_to_archive": not mismatches,
            "mismatches": mismatches,
        },
        "archive_source": archive_source,
        "provenance_chain": "user archive -> sha256 verified vs guide 1.1 -> inspected -> extracted -> digest re-verified -> read-only lab copy",
        "idempotence": (
            "Re-running LAB-01 uses the retained read-only copy when the supplied zip is no longer "
            "at LAB_ROOT. The digest gate against guide 1.1 is applied either way, so a substituted "
            "archive still stops the phase."
        ),
        "supersedes": "alpha_source_snapshot.json from the bootstrap run, which sourced the loose files because the archive was not yet on this host",
    }
    art = writer.write_json("archive_ingestion.json", report, schema="crypto_regime_lab.archive_ingestion.v1")

    print(f"archive sha256          : {record['archive_sha256']}")
    print(f"matches guide 1.1       : {record['archive_sha256_matches_guide']}")
    print(f"entries / rejections    : {record['entry_count']} / {len(record['rejections'])}")
    print(f"extracted + verified    : {len(extraction['extracted'])} files")
    print(f"loose copies identical  : {not mismatches}")
    print(f"evidence -> {art['artifact_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
