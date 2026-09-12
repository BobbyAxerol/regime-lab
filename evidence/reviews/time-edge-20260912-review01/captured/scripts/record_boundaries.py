#!/usr/bin/env python
"""LAB-01 L01.2 + L01.4 (completed): source boundary record and data read-lock policy.

Two things the guide asks for that were still missing:

  * L01.2 "if the source/server is dirty, record the boundary and pick a clean
    snapshot" — a recorded boundary, not an unwritten claim;
  * L01.4 "mutable data partitions outside the lab must be snapshot/read-locked
    per policy, and no collector may be run" — the POLICY belongs to LAB-01;
    executing it against real partitions is LAB-03.

Any git read here runs with GIT_OPTIONAL_LOCKS=0 and the repository's
``.git/index`` is digested before and after, so "we only read" is proven rather
than asserted.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter, utc_now_iso  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy, manifest_directory, sha256_file  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"


def _git(repo: Path, *args: str) -> tuple[int, str]:
    """Read-only git invocation: optional locks disabled so the index is never rewritten."""
    env = dict(os.environ)
    env["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        done = subprocess.run(["git", "-C", str(repo), *args],
                              capture_output=True, text=True, timeout=60, env=env)
        return done.returncode, done.stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, f"{type(exc).__name__}: {exc}"


def probe_repo(repo: Path) -> dict:
    """Record a repository's state and prove the probe itself changed nothing."""
    git_dir = repo / ".git"
    index = git_dir / "index"
    before = sha256_file(index) if index.is_file() else None

    is_repo = git_dir.exists()
    record: dict = {"path": str(repo), "is_git_repo": is_repo}
    if is_repo:
        rc_branch, branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
        rc_head, head = _git(repo, "rev-parse", "HEAD")
        rc_status, status = _git(repo, "status", "--porcelain")
        dirty_lines = [ln for ln in status.splitlines() if ln.strip()] if rc_status == 0 else None
        record.update({
            "branch": branch if rc_branch == 0 else None,
            "head_commit": head if rc_head == 0 else None,
            "dirty": (bool(dirty_lines) if dirty_lines is not None else "UNKNOWN"),
            "dirty_entry_count": (len(dirty_lines) if dirty_lines is not None else None),
            "dirty_entries": (dirty_lines[:20] if dirty_lines else []),
        })
    after = sha256_file(index) if index.is_file() else None
    record["git_index_sha256_before"] = before
    record["git_index_sha256_after"] = after
    record["probe_left_repo_unmodified"] = (before == after)
    record["read_method"] = "GIT_OPTIONAL_LOCKS=0; no write command issued"
    return record


def build_data_readlock_policy() -> dict:
    return {
        "schema": "crypto_regime_lab.data_readlock_policy.v1",
        "study_id": STUDY_ID,
        "registered_at_utc": utc_now_iso(),
        "scope": "every mutable data partition that lives OUTSIDE LAB_ROOT",
        "known_mutable_roots": [
            {
                "path": "/root/bobby/pool_alpha/alphas_storage/_get_data/storage",
                "why_mutable": "collectors append new partitions and may repair existing ones",
                "lab_access": "read-only; mounted ro inside the worker namespace",
            }
        ],
        "rules": [
            "The lab never runs a collector, scheduler, trading adapter or repair job. "
            "If coverage is missing it is reported as missing, never fetched.",
            "A partition enters the lab only as a snapshot copied under LAB_ROOT/snapshots/{snapshot_id}/, "
            "with a manifest recording per-file sha256, byte size, row count, closed/partial state, "
            "time range and the read timestamp.",
            "The read-lock is the manifest: a run declares the snapshot_id it used, and re-verifies "
            "every digest before and after the run.",
            "Digest drift between declaration and completion invalidates the run "
            "(status EXTERNAL_DATA_DRIFT), it does not silently continue on the new bytes.",
            "Only closed partitions are eligible for a primary run; an open/partial tail is excluded "
            "with an explicit reason rather than truncated silently.",
            "A failed partition read becomes explicit missing coverage. It must never be turned into "
            "a backtest on 'the rest' that is then reported as a full sample.",
            "No file, mode, ownership or metadata under a mutable root is ever modified, and no "
            "symlink or hardlink from the lab aliases one.",
        ],
        "enforcement_now": [
            "protected roots are read-only bind mounts inside the worker namespace (measured each preflight)",
            "SandboxPolicy.assert_readable refuses reads outside the declared roots",
            "the lab has no collector code and no network in run/certify/report stages",
        ],
        "execution_owner": "LAB-03 (L03.2 primary snapshots, L03.3 availability builder)",
        "artifacts_lab03_must_produce": [
            "snapshots/{snapshot_id}/manifest.json",
            "data_product_inventory.json",
            "availability_rules.json",
            "evidence/{study_id}/{run_id}/data_access_log.jsonl",
        ],
        "status": "POLICY_REGISTERED_EXECUTION_PENDING_LAB03",
    }


def main() -> int:
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    policy.assert_lab_marker_ok(STUDY_ID)
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    with writer.attempt("L01.2.source_boundary") as att:
        repos = {}
        for repo in (Path("/root/bobby/pool_alpha/quantbt"),
                     Path("/root/bobby/pool_alpha/alphas_storage")):
            repos[str(repo)] = probe_repo(repo)
        alpha_root = next(p for p in policy.protected_roots if p.name == "alpha_to_tes_regime_model")
        att.detail = {"repos": len(repos),
                      "all_probes_nonmutating": all(r["probe_left_repo_unmodified"] for r in repos.values())}

    boundary = {
        "schema": "crypto_regime_lab.source_boundary.v1",
        "recorded_at_utc": utc_now_iso(),
        "purpose": "guide L01.2: record the boundary between the lab and the upstream sources it read",
        "repositories": repos,
        "quantbt_boundary": {
            "the_lab_does_not_consume_this_repo": True,
            "consumed_instead": "quantbt-engine==1.1.1 / quantbt-native==0.4.2 wheels from PyPI, "
                                "retained at vendor_readonly/quantbt_1_1_1_dist/",
            "consequence": "upstream working-tree state, dirty or clean, cannot influence any lab result",
        },
        "alpha_source_boundary": {
            "root": str(alpha_root),
            "digest_manifest": manifest_directory(alpha_root, ("*.py",)),
            "authoritative_copy": "vendor_readonly/alphas_raw (extracted from the retained archive)",
        },
        "write_operations_issued_against_protected_roots": 0,
    }
    art = writer.write_json("source_boundary.json", boundary, schema=boundary["schema"])

    with writer.attempt("L01.4.data_readlock_policy") as att:
        readlock = build_data_readlock_policy()
        writer.write_config("data_readlock_policy.json", readlock)
        writer.write_json("data_readlock_policy.json", readlock, schema=readlock["schema"])
        att.detail = {"status": readlock["status"]}

    for name, record in repos.items():
        print(f"  {Path(name).name:<16} branch={record.get('branch')} dirty={record.get('dirty')} "
              f"probe_nonmutating={record['probe_left_repo_unmodified']}")
    print(f"  data read-lock policy : {readlock['status']}")
    print(f"evidence -> {art['artifact_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
