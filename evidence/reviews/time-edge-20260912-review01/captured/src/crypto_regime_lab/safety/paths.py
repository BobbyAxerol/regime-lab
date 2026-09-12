"""Path guards for the lab (guide LAB-01 / L01.1, tests T01, T02, T08).

These guards are *containment hygiene*, not an OS sandbox. They stop accidental
writes outside ``LAB_ROOT`` and refuse editable copies that alias a protected
source. They cannot stop a determined native extension. Anything that claims
stronger isolation must be backed by an OS mechanism, not by this module.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

SANDBOX_POLICY_RELPATH = "configs/sandbox_policy.json"
LAB_MARKER_RELPATH = ".lab_marker.json"


class SafetyViolation(RuntimeError):
    """Raised when an operation would leave the lab or alias a protected root."""


def realpath(path: str | os.PathLike[str]) -> Path:
    """Canonical, symlink-resolved absolute path. Never touches the filesystem state."""
    return Path(os.path.realpath(os.path.abspath(str(path))))


def _is_within(child: Path, parent: Path) -> bool:
    """True when ``child`` is ``parent`` or lives underneath it (both canonical)."""
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


@dataclass(frozen=True)
class SandboxPolicy:
    """Resolved, canonical view of what the lab may read and write.

    ``lab_root`` is the only writable root. ``protected_roots`` are read-only
    inputs; ``forbidden_read_roots`` are directories the guide bans from being
    mined for extra strategies (guide 0.2).
    """

    lab_root: Path
    protected_roots: tuple[Path, ...]
    forbidden_read_roots: tuple[Path, ...] = ()
    policy_path: Path | None = None
    raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def load(cls, policy_path: str | os.PathLike[str]) -> "SandboxPolicy":
        policy_path = realpath(policy_path)
        with open(policy_path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
        return cls(
            lab_root=realpath(raw["lab_root"]),
            protected_roots=tuple(realpath(p) for p in raw.get("protected_roots", [])),
            forbidden_read_roots=tuple(realpath(p) for p in raw.get("forbidden_read_roots", [])),
            policy_path=policy_path,
            raw=raw,
        )

    @classmethod
    def discover(cls, start: str | os.PathLike[str] | None = None) -> "SandboxPolicy":
        """Find ``configs/sandbox_policy.json`` from ``start`` upward."""
        current = realpath(start or Path.cwd())
        for candidate in [current, *current.parents]:
            policy = candidate / SANDBOX_POLICY_RELPATH
            if policy.is_file():
                return cls.load(policy)
        raise SafetyViolation(f"no {SANDBOX_POLICY_RELPATH} found from {current}")

    # -- validation -------------------------------------------------------

    def validate_lab_root(self) -> list[str]:
        """T01: LAB_ROOT must not sit inside, nor contain, any protected root."""
        problems: list[str] = []
        for protected in self.protected_roots:
            if _is_within(self.lab_root, protected):
                problems.append(f"LAB_ROOT {self.lab_root} is inside protected root {protected}")
            if _is_within(protected, self.lab_root):
                problems.append(f"protected root {protected} is inside LAB_ROOT {self.lab_root}")
        if not self.lab_root.is_dir():
            problems.append(f"LAB_ROOT {self.lab_root} is not an existing directory")
        return problems

    def assert_lab_root_ok(self) -> None:
        problems = self.validate_lab_root()
        if problems:
            raise SafetyViolation("; ".join(problems))

    def validate_lab_marker(self, study_id: str | None = None) -> list[str]:
        """L01.1: LAB_ROOT must be new, or already marked for the SAME study.

        Reusing an arbitrary directory — or a lab bootstrapped for a different
        study — would silently mix two studies' evidence under one root.
        """
        import json as _json

        problems: list[str] = []
        marker = self.lab_root / LAB_MARKER_RELPATH
        if not marker.is_file():
            occupied = [
                p.name for p in self.lab_root.iterdir()
                if p.name not in {LAB_MARKER_RELPATH, ".cache"} and not p.name.startswith(".")
            ]
            if occupied:
                problems.append(
                    f"LAB_ROOT {self.lab_root} already contains {len(occupied)} entries but has no "
                    f"{LAB_MARKER_RELPATH}; refusing to reuse an arbitrary directory"
                )
            return problems
        try:
            payload = _json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return [f"{LAB_MARKER_RELPATH} is unreadable: {exc}"]
        if payload.get("lab_root") and realpath(payload["lab_root"]) != self.lab_root:
            problems.append(
                f"marker was written for {payload['lab_root']}, not {self.lab_root}; the lab was moved or copied"
            )
        if study_id is not None and payload.get("study_id") != study_id:
            problems.append(
                f"marker study_id={payload.get('study_id')!r} != requested {study_id!r}; "
                "one LAB_ROOT holds exactly one study"
            )
        return problems

    def assert_lab_marker_ok(self, study_id: str | None = None) -> None:
        problems = self.validate_lab_marker(study_id)
        if problems:
            raise SafetyViolation("; ".join(problems))

    # -- write guard ------------------------------------------------------

    def resolve_write_target(self, path: str | os.PathLike[str]) -> Path:
        """Canonicalise a write target and prove it stays inside LAB_ROOT.

        Resolves the nearest existing ancestor so a not-yet-created file cannot
        smuggle a symlinked parent past the check.
        """
        target = Path(os.path.abspath(str(path)))
        anchor = target
        while not anchor.exists() and anchor != anchor.parent:
            anchor = anchor.parent
        canonical_anchor = realpath(anchor)
        suffix = target.relative_to(anchor) if anchor != target else Path()
        canonical = canonical_anchor / suffix if str(suffix) != "." else canonical_anchor
        if not _is_within(canonical, self.lab_root):
            raise SafetyViolation(f"write target {canonical} escapes LAB_ROOT {self.lab_root}")
        for protected in self.protected_roots:
            if _is_within(canonical, protected):
                raise SafetyViolation(f"write target {canonical} is inside protected root {protected}")
        return canonical

    def assert_readable(self, path: str | os.PathLike[str]) -> Path:
        """Reads are allowed inside LAB_ROOT and declared protected roots only."""
        canonical = realpath(path)
        for forbidden in self.forbidden_read_roots:
            if _is_within(canonical, forbidden):
                raise SafetyViolation(f"read of {canonical} is forbidden by policy root {forbidden}")
        allowed = (self.lab_root, *self.protected_roots)
        if not any(_is_within(canonical, root) for root in allowed):
            raise SafetyViolation(f"read of {canonical} is outside declared readable roots")
        return canonical


# -- copy helpers ---------------------------------------------------------


def assert_physical_copy(path: Path) -> None:
    """T02: an editable lab copy must not be a symlink or a hardlink to a source."""
    if path.is_symlink():
        raise SafetyViolation(f"{path} is a symlink; editable lab copies must be physical")
    if path.is_file() and path.stat().st_nlink > 1:
        raise SafetyViolation(f"{path} has st_nlink={path.stat().st_nlink}; hardlinked copies are forbidden")


def sha256_file(path: str | os.PathLike[str], chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def copy_readonly_snapshot(
    src: str | os.PathLike[str],
    dst: str | os.PathLike[str],
    policy: SandboxPolicy,
    expected_sha256: str | None = None,
) -> dict:
    """Copy one source file into the lab as a physical, read-only snapshot.

    Verifies the source digest before and after the copy so a mid-copy change is
    visible rather than silently snapshotted.
    """
    src_path = policy.assert_readable(src)
    dst_path = policy.resolve_write_target(dst)
    if src_path.is_symlink():
        raise SafetyViolation(f"source {src} is a symlink; refusing to snapshot an alias")
    src_digest_before = sha256_file(src_path)
    if expected_sha256 is not None and src_digest_before != expected_sha256:
        raise SafetyViolation(
            f"source digest mismatch for {src_path}: expected {expected_sha256}, got {src_digest_before}"
        )
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src_path, dst_path)  # copyfile, not copy2: never propagates source mode bits
    dst_digest = sha256_file(dst_path)
    src_digest_after = sha256_file(src_path)
    if not (src_digest_before == src_digest_after == dst_digest):
        raise SafetyViolation(f"unstable copy for {src_path}: source changed or copy differs")
    os.chmod(dst_path, 0o444)
    assert_physical_copy(dst_path)
    return {
        "source_path": str(src_path),
        "snapshot_path": str(dst_path),
        "sha256": dst_digest,
        "size_bytes": dst_path.stat().st_size,
        "source_mtime_utc": _mtime_iso(src_path),
    }


def _mtime_iso(path: Path) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def manifest_directory(root: str | os.PathLike[str], patterns: tuple[str, ...] = ("*",)) -> dict[str, str]:
    """T08 helper: {relative path -> sha256} for integrity comparison before/after a run."""
    root_path = realpath(root)
    out: dict[str, str] = {}
    for pattern in patterns:
        for path in sorted(root_path.rglob(pattern)):
            if path.is_file() and not path.is_symlink():
                out[str(path.relative_to(root_path))] = sha256_file(path)
    return out
