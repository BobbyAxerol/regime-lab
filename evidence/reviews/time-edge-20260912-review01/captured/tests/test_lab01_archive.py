"""Real-archive provenance tests (guide L01.2, T03/T04) using the supplied zip."""

from __future__ import annotations

import zipfile

import pytest

from crypto_regime_lab.safety.archive import (
    ALLOWED_ALPHA_FILES, EXPECTED_ARCHIVE_SHA256, inspect_zip, safe_extract,
)
from crypto_regime_lab.safety.paths import SafetyViolation, sha256_file


@pytest.fixture(scope="module")
def archive(lab_root):
    path = lab_root / "vendor_readonly" / "alpha_zip_original.zip"
    if not path.is_file():
        pytest.skip("original archive not yet ingested; run scripts/ingest_archive.py")
    return path


def test_retained_archive_digest_matches_the_guide(archive):
    assert sha256_file(archive) == EXPECTED_ARCHIVE_SHA256


def test_real_archive_is_admissible_with_no_rejections(archive, policy):
    inspection = inspect_zip(archive, policy)
    assert inspection.admissible, inspection.rejections
    assert inspection.rejections == []


def test_real_archive_contains_exactly_the_four_allowed_files(archive):
    with zipfile.ZipFile(archive) as zf:
        members = [
            i.filename for i in zf.infolist()
            if not i.is_dir() and not i.filename.startswith("__MACOSX/")
        ]
    from pathlib import Path

    assert sorted(Path(m).name for m in members) == sorted(ALLOWED_ALPHA_FILES)


def test_extracted_copies_match_the_published_digests(lab_root):
    raw = lab_root / "vendor_readonly" / "alphas_raw"
    for name, expected in ALLOWED_ALPHA_FILES.items():
        target = raw / name
        assert target.is_file(), f"{name} not extracted"
        assert sha256_file(target) == expected
        assert target.stat().st_mode & 0o222 == 0, f"{name} must be read-only in the lab"


def test_read_guard_refuses_an_archive_from_outside_the_readable_roots(tmp_path, policy):
    """Reading a zip staged outside LAB_ROOT and the protected roots is refused."""
    import zipfile as _zf

    outside = tmp_path / "outside.zip"
    with _zf.ZipFile(outside, "w") as zf:
        zf.writestr("vwap.py", "x = 1\n")
    with pytest.raises(SafetyViolation, match="outside declared readable roots"):
        inspect_zip(outside, policy)


def test_extraction_refuses_an_archive_with_a_tampered_member(lab_tmp, policy):
    """A member whose bytes drift from the manifest must abort the extraction."""
    bad = lab_tmp / "tampered.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        for name in ALLOWED_ALPHA_FILES:
            zf.writestr(name, "# tampered\n")
    dest = lab_tmp / "tampered_extract"
    with pytest.raises(SafetyViolation, match="digest"):
        safe_extract(bad, dest, policy)


def test_extraction_refuses_an_incomplete_archive(lab_tmp, policy, lab_root):
    """Three of four files is not the supplied archive; refuse rather than proceed."""
    source = lab_root / "vendor_readonly" / "alphas_raw"
    partial = lab_tmp / "partial.zip"
    names = sorted(ALLOWED_ALPHA_FILES)[:3]
    with zipfile.ZipFile(partial, "w") as zf:
        for name in names:
            zf.writestr(name, (source / name).read_bytes())
    dest = lab_tmp / "partial_extract"
    with pytest.raises(SafetyViolation, match="missing"):
        safe_extract(partial, dest, policy)


def test_loose_copies_in_alphas_storage_are_identical_to_the_archive(policy, lab_root):
    """Provenance cross-check: the loose files are the same bytes as the archive."""
    loose = next(p for p in policy.protected_roots if p.name == "alpha_to_tes_regime_model")
    raw = lab_root / "vendor_readonly" / "alphas_raw"
    for name in ALLOWED_ALPHA_FILES:
        assert sha256_file(loose / name) == sha256_file(raw / name)
