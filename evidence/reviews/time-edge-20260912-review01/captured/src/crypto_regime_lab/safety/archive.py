"""Archive inventory and admission control (guide L01.2, tests T03, T04).

The lab never extracts an archive it has not first inventoried. Every entry is
checked *before* any byte is written: absolute paths, traversal, symlinks,
duplicates, oversize and unexpected members are rejections, not warnings.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .paths import SafetyViolation, SandboxPolicy, sha256_file

# Guide 1.1: the only four admissible alpha files and their published digests.
ALLOWED_ALPHA_FILES: dict[str, str] = {
    "vwap.py": "ef9e7e8a998a68584e742fb698cfd06ee27ec8355f76566b480810b552376d84",
    "hash_momentum.py": "ab35d90680ea723440d8ad4d831029505e54bf2c2567350313b1cacbfea6c773",
    "adaptive_hma_cpp.py": "86c88f38e86b7e5b6e92108ef30704e5bdd3d69f6a9f9c07069fdff03ad958d2",
    "signal_combine.py": "d540deef7d4275d58033a283421edb09296a7df9032361e050512a02823fc504",
}
ALPHA_IDS: dict[str, str] = {
    "vwap.py": "A-VWAP",
    "hash_momentum.py": "A-HASH",
    "adaptive_hma_cpp.py": "A-HMA",
    "signal_combine.py": "A-SC",
}
EXPECTED_ARCHIVE_SHA256 = "57406dbb9ffdcf4617e4895925126fa73600a585a6541f996c6b2d980f6701ae"

MAX_MEMBER_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200.0


@dataclass
class ArchiveInspection:
    """Result of inspecting an archive without extracting it."""

    archive_path: Path
    archive_sha256: str
    entries: list[dict] = field(default_factory=list)
    rejections: list[dict] = field(default_factory=list)

    @property
    def admissible(self) -> bool:
        return not self.rejections

    def as_record(self) -> dict:
        return {
            "schema": "crypto_regime_lab.archive_inspection.v1",
            "archive_path": str(self.archive_path),
            "archive_sha256": self.archive_sha256,
            "archive_sha256_matches_guide": self.archive_sha256 == EXPECTED_ARCHIVE_SHA256,
            "entry_count": len(self.entries),
            "entries": self.entries,
            "rejections": self.rejections,
            "admissible": self.admissible,
        }


def _reject(rejections: list[dict], name: str, code: str, detail: str) -> None:
    rejections.append({"entry": name, "code": code, "detail": detail})


def inspect_zip(archive_path: str | Path, policy: SandboxPolicy | None = None) -> ArchiveInspection:
    """Inventory a zip and list every reason it must not be extracted."""
    path = Path(archive_path)
    if policy is not None:
        path = policy.assert_readable(path)
    inspection = ArchiveInspection(archive_path=path, archive_sha256=sha256_file(path))
    seen: set[str] = set()
    total = 0
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            name = info.filename
            entry = {
                "name": name,
                "size_bytes": info.file_size,
                "compressed_bytes": info.compress_size,
                "is_dir": info.is_dir(),
                "external_attr": info.external_attr,
            }
            inspection.entries.append(entry)
            if name.startswith("__MACOSX/") or Path(name).name.startswith("._"):
                entry["ignored_metadata"] = True
                continue
            if info.is_dir():
                continue
            normalized = name.replace("\\", "/")
            if normalized.startswith("/") or (len(normalized) > 1 and normalized[1] == ":"):
                _reject(inspection.rejections, name, "ABSOLUTE_PATH", "member uses an absolute path")
            if any(part == ".." for part in Path(normalized).parts):
                _reject(inspection.rejections, name, "PATH_TRAVERSAL", "member escapes the extraction root")
            # High 16 bits of external_attr hold the unix mode; 0xA000 marks a symlink.
            if (info.external_attr >> 16) & 0xF000 == 0xA000:
                _reject(inspection.rejections, name, "SYMLINK_MEMBER", "archive symlinks are never extracted")
            if normalized in seen:
                _reject(inspection.rejections, name, "DUPLICATE_ENTRY", "duplicate member name")
            seen.add(normalized)
            if info.file_size > MAX_MEMBER_BYTES:
                _reject(inspection.rejections, name, "OVERSIZE_MEMBER", f"{info.file_size} > {MAX_MEMBER_BYTES}")
            if info.compress_size > 0:
                ratio = info.file_size / info.compress_size
                if ratio > MAX_COMPRESSION_RATIO:
                    _reject(inspection.rejections, name, "COMPRESSION_BOMB", f"ratio {ratio:.1f}")
            total += info.file_size
            if Path(normalized).name not in ALLOWED_ALPHA_FILES:
                _reject(inspection.rejections, name, "NOT_IN_ALLOWLIST", "only the four supplied alpha files are admissible")
    if total > MAX_TOTAL_BYTES:
        _reject(inspection.rejections, "<archive>", "OVERSIZE_TOTAL", f"{total} > {MAX_TOTAL_BYTES}")
    return inspection


def safe_extract(
    archive_path: str | Path,
    dest_dir: str | Path,
    policy: SandboxPolicy,
    inspection: ArchiveInspection | None = None,
) -> dict:
    """Extract an inspected archive, flattening to basenames, read-only.

    Refuses to extract anything the inspection rejected, writes each member
    through the lab write guard, and verifies the extracted digest against the
    published manifest before the file is made read-only.
    """
    path = Path(archive_path)
    inspection = inspection or inspect_zip(path, policy)
    if not inspection.admissible:
        raise SafetyViolation(f"refusing to extract {path}: {inspection.rejections}")
    dest = policy.resolve_write_target(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    extracted: list[dict] = []
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            name = info.filename
            if info.is_dir() or name.startswith("__MACOSX/") or Path(name).name.startswith("._"):
                continue
            basename = Path(name.replace("\\", "/")).name
            if basename not in ALLOWED_ALPHA_FILES:
                raise SafetyViolation(f"member {name} is not in the four-file allowlist")
            target = policy.resolve_write_target(dest / basename)
            payload = zf.read(info)
            if len(payload) != info.file_size:
                raise SafetyViolation(f"declared size {info.file_size} != actual {len(payload)} for {name}")
            with open(target, "wb") as handle:
                handle.write(payload)
            digest = sha256_file(target)
            expected = ALLOWED_ALPHA_FILES[basename]
            if digest != expected:
                target.unlink()
                raise SafetyViolation(f"extracted {basename} digest {digest} != published {expected}")
            import os as _os

            _os.chmod(target, 0o444)
            extracted.append({
                "member": name,
                "basename": basename,
                "alpha_id": ALPHA_IDS[basename],
                "path": str(target),
                "sha256": digest,
                "size_bytes": target.stat().st_size,
            })
    missing = sorted(set(ALLOWED_ALPHA_FILES) - {e["basename"] for e in extracted})
    if missing:
        raise SafetyViolation(f"archive did not contain every allowed file; missing {missing}")
    return {
        "schema": "crypto_regime_lab.archive_extraction.v1",
        "archive_path": str(path),
        "archive_sha256": inspection.archive_sha256,
        "archive_sha256_matches_guide": inspection.archive_sha256 == EXPECTED_ARCHIVE_SHA256,
        "dest_dir": str(dest),
        "extracted": extracted,
        "status": "EXTRACTED_AND_VERIFIED",
    }


def verify_alpha_files(source_dir: str | Path, policy: SandboxPolicy) -> dict:
    """T04: confirm the four allowed files exist with the published digests.

    A digest mismatch or a missing file is a stop condition — the lab must never
    silently adopt a different alpha revision.
    """
    root = policy.assert_readable(source_dir)
    found: dict[str, dict] = {}
    problems: list[dict] = []
    for filename, expected in ALLOWED_ALPHA_FILES.items():
        candidate = root / filename
        if not candidate.is_file():
            problems.append({"file": filename, "code": "MISSING", "detail": f"not found under {root}"})
            continue
        if candidate.is_symlink():
            problems.append({"file": filename, "code": "SYMLINK_SOURCE", "detail": "source is a symlink"})
            continue
        actual = sha256_file(candidate)
        found[filename] = {
            "alpha_id": ALPHA_IDS[filename],
            "path": str(candidate),
            "sha256": actual,
            "expected_sha256": expected,
            "matches": actual == expected,
            "size_bytes": candidate.stat().st_size,
        }
        if actual != expected:
            problems.append({"file": filename, "code": "DIGEST_MISMATCH", "detail": f"{actual} != {expected}"})
    extra = sorted(
        p.name for p in root.glob("*.py") if p.name not in ALLOWED_ALPHA_FILES
    )
    if extra:
        problems.append({"file": None, "code": "UNEXPECTED_PY_FILES", "detail": ", ".join(extra)})
    return {
        "schema": "crypto_regime_lab.alpha_source_verification.v1",
        "source_dir": str(root),
        "files": found,
        "problems": problems,
        "status": "VERIFIED" if not problems else "STOP_REQUIRED",
    }


def assert_alpha_sources_ok(verification: dict) -> None:
    if verification["status"] != "VERIFIED":
        raise SafetyViolation(f"alpha source verification failed: {verification['problems']}")
