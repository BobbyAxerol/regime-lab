#!/usr/bin/env python
"""Unpack the supplied archive to .py files under src/crypto_regime_lab/alphas/
and remove the zip, as instructed by the user.

The files land in a ``raw_supplied/`` subdirectory with no ``__init__.py`` so
they cannot be imported as ``crypto_regime_lab.alphas.<name>``. That matters:
guide L01.3 forbids running the original modules before containment, and
``hash_momentum.py`` raises NameError on import anyway (missing numpy).

Deleting the zip is safe because ``vendor_readonly/alpha_zip_original.zip``
retains it read-only with the guide digest.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter  # noqa: E402
from crypto_regime_lab.safety.archive import (  # noqa: E402
    ALLOWED_ALPHA_FILES, EXPECTED_ARCHIVE_SHA256, inspect_zip, safe_extract,
)
from crypto_regime_lab.safety.paths import SafetyViolation, SandboxPolicy, sha256_file  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"
ZIP_RELPATH = Path("src/crypto_regime_lab/alphas/alpha_to_tes_regime_model.zip")
# Hyphen is deliberate: "raw-supplied" is not a valid Python identifier, so these
# files cannot be reached as crypto_regime_lab.alphas.<pkg>.<name>. An underscore
# directory WOULD be importable via PEP 420 implicit namespace packages even with
# no __init__.py, which is exactly the accident guide L01.3 forbids.
DEST_RELPATH = Path("src/crypto_regime_lab/alphas/raw-supplied")

IMPORT_GUARD = '''"""Import guard for the raw_supplied alpha tier (guide L01.3).

Importing these modules executes the original alpha source, which guide L01.3
forbids before containment. Two weaker guards were measured to be insufficient:
no __init__.py (PEP 420 namespace packages still import it) and a hyphenated
directory name (blocks the import statement only, not importlib.import_module).
"""

raise ImportError(
    "crypto_regime_lab.alphas.raw-supplied holds original alpha source and must not be imported. "
    "Read it as text/AST via the LAB-02 adapters, or load one file by path inside safety.sandbox."
)
'''

NOTICE = """# raw_supplied — original alpha sources, do not import

These four files are the `raw_supplied` tier from guide section 2.1: original
bytes kept for provenance. They are read-only, and this directory is named with
a hyphen on purpose: `raw-supplied` is not a valid Python identifier, so no
import statement can reach them.

An underscore name with no `__init__.py` would NOT have been enough — PEP 420
implicit namespace packages make such a directory importable anyway. That was
verified, not assumed.

Do not import or execute them. `hash_momentum.py` raises `NameError: np` on
import, and guide L01.3 forbids running the original modules before
containment. LAB-02 builds versioned adapters that read these as text/AST; the
adapters are the only executable path.

Identity is verified against the SHA-256 values published in guide section 1.1.
The archive they came from is retained read-only at
`vendor_readonly/alpha_zip_original.zip`.
"""


def main() -> int:
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    policy.assert_lab_marker_ok(STUDY_ID)
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    zip_path = policy.lab_root / ZIP_RELPATH
    dest = policy.lab_root / DEST_RELPATH

    retained = policy.lab_root / "vendor_readonly" / "alpha_zip_original.zip"
    if not zip_path.is_file():
        # Idempotent rerun: the supplied zip is deleted by design after the first
        # pass, so verify the unpacked files instead, and fall back to the
        # retained archive if any of the four is missing or has drifted.
        intact = all(
            (dest / name).is_file() and sha256_file(dest / name) == expected
            for name, expected in ALLOWED_ALPHA_FILES.items()
        )
        if intact:
            print(f"zip already unpacked and removed; four files verified in {dest}")
            return 0
        if retained.is_file() and sha256_file(retained) == EXPECTED_ARCHIVE_SHA256:
            print(f"re-extracting from the retained archive {retained.name}")
            zip_path = retained
        else:
            raise SafetyViolation(
                f"no archive at {zip_path}, {dest} incomplete, and no verified retained copy"
            )

    with writer.attempt("L01.2.unpack_inplace") as att:
        digest = sha256_file(zip_path)
        if digest != EXPECTED_ARCHIVE_SHA256:
            raise SafetyViolation(f"archive digest {digest} != guide {EXPECTED_ARCHIVE_SHA256}; refusing")
        inspection = inspect_zip(zip_path, policy)
        if not inspection.admissible:
            raise SafetyViolation(f"archive rejected: {inspection.rejections}")
        for name in ALLOWED_ALPHA_FILES:
            target = dest / name
            if target.exists():
                os.chmod(target, stat.S_IWUSR | stat.S_IRUSR)
        extraction = safe_extract(zip_path, dest, policy, inspection)
        att.detail = {"extracted": len(extraction["extracted"])}

    notice_path = policy.resolve_write_target(dest / "DO_NOT_IMPORT.md")
    notice_path.write_text(NOTICE, encoding="utf-8")

    guard_path = policy.resolve_write_target(dest / "__init__.py")
    if guard_path.exists():
        os.chmod(guard_path, stat.S_IWUSR | stat.S_IRUSR)
    guard_path.write_text(IMPORT_GUARD, encoding="utf-8")
    os.chmod(guard_path, 0o444)

    # Cross-check against the vendor_readonly provenance copies before deleting.
    raw_dir = policy.lab_root / "vendor_readonly" / "alphas_raw"
    mismatches = [
        name for name in ALLOWED_ALPHA_FILES
        if sha256_file(dest / name) != sha256_file(raw_dir / name)
    ]
    if mismatches:
        raise SafetyViolation(f"unpacked files differ from vendor_readonly copies: {mismatches}")

    if not retained.is_file() or sha256_file(retained) != EXPECTED_ARCHIVE_SHA256:
        raise SafetyViolation("refusing to delete the zip: no verified retained copy exists")

    zip_deleted = False
    if zip_path.resolve() != retained.resolve():
        with writer.attempt("L01.2.remove_zip") as att:
            target = policy.resolve_write_target(zip_path)   # deletion stays inside LAB_ROOT
            target.unlink()
            zip_deleted = True
            att.detail = {"removed": str(target), "retained_copy": str(retained)}

    report = {
        "instruction": "user asked to unzip the archive into .py files and then delete the zip",
        "archive_path": str(zip_path),
        "archive_sha256": digest,
        "archive_sha256_matches_guide": True,
        "destination": str(dest),
        "destination_is_importable_package": False,
        "import_guard": "raw-supplied/__init__.py raises ImportError on any import attempt",
        "destination_rationale": (
            "directory name contains a hyphen so it is not a valid Python identifier and cannot be "
            "imported; files are mode 0444 and a DO_NOT_IMPORT.md sits beside them. Guide L01.3 "
            "forbids executing the original modules before containment."
        ),
        "why_not_an_underscore_name": (
            "verified in this session: PEP 420 implicit namespace packages made "
            "crypto_regime_lab.alphas.raw_supplied.vwap importable even with no __init__.py, "
            "so the underscore layout was replaced rather than trusted"
        ),
        "extracted": extraction["extracted"],
        "identical_to_vendor_readonly": True,
        "zip_deleted": zip_deleted,
        "source_used": str(zip_path),
        "deletion_was_safe_because": f"read-only provenance copy retained at {retained} with the guide digest",
        "not_a_second_source_of_truth": (
            "vendor_readonly/alphas_raw remains the provenance tier; these files are the same bytes "
            "placed where the user asked, and a test asserts the two stay identical"
        ),
    }
    art = writer.write_json("alpha_unpack_inplace.json", report, schema="crypto_regime_lab.alpha_unpack.v1")

    print(f"archive digest        : {digest}")
    print("matches guide 1.1     : True")
    print(f"unpacked to           : {dest}")
    for entry in extraction["extracted"]:
        print(f"    {entry['alpha_id']:<8} {entry['basename']:<22} {entry['sha256'][:16]}…")
    print("identical to vendor   : True")
    print(f"zip deleted           : {zip_deleted} (retained read-only at {retained.name})")
    print(f"evidence -> {art['artifact_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
