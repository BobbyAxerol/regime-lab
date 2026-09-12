"""Preflight checks (guide LAB-01 tests/gate: T01, T02, T03, T04, T05, T06, T07, T08).

Each check returns a record with ``id``, ``status`` (PASS / FAIL / BLOCKED /
NOT_APPLICABLE), ``observed`` and ``expectation``. A check that cannot be run is
reported as BLOCKED with a reason — never as a pass.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Callable

from . import archive as archive_mod
from . import process as process_mod
from . import sandbox as sandbox_mod
from .paths import SafetyViolation, SandboxPolicy, manifest_directory, realpath

CheckFn = Callable[[SandboxPolicy], dict]


def _record(check_id: str, title: str, status: str, expectation: str, observed, detail: dict | None = None) -> dict:
    return {
        "id": check_id,
        "title": title,
        "status": status,
        "expectation": expectation,
        "observed": observed,
        "detail": detail or {},
    }


def check_iso_containment(policy: SandboxPolicy) -> dict:
    """Measure OS-level containment. Availability is probed, never declared."""
    report = sandbox_mod.probe_isolation(policy)
    record = report.as_record()
    return _record(
        "ISO", "OS-level worker containment (bubblewrap namespaces)",
        "PASS" if report.available else "BLOCKED",
        "LAB_ROOT writable, protected roots read-only, network namespace empty, no credentials in worker env",
        {"available": report.available, "mechanism": report.mechanism, "failures": report.failures},
        {"bwrap_version": report.bwrap_version, "checks": record["checks"], "claim": record["claim"]},
    )


def check_t01_lab_root(policy: SandboxPolicy) -> dict:
    """LAB_ROOT must not live inside — or contain — a protected repo."""
    problems = policy.validate_lab_root()
    # Positive control: a LAB_ROOT placed inside a protected root must be rejected.
    fake = SandboxPolicy(
        lab_root=policy.protected_roots[0] / "pretend_lab" if policy.protected_roots else policy.lab_root,
        protected_roots=policy.protected_roots,
    )
    fake_problems = fake.validate_lab_root() if policy.protected_roots else ["<no protected roots configured>"]
    status = "PASS" if not problems and fake_problems else "FAIL"
    return _record(
        "T01", "LAB_ROOT inside protected repo is rejected",
        status,
        "real LAB_ROOT accepted; a LAB_ROOT inside a protected root is rejected",
        {"real_lab_root_problems": problems, "positive_control_rejected": bool(fake_problems)},
        {"lab_root": str(policy.lab_root), "protected_roots": [str(p) for p in policy.protected_roots]},
    )


def check_t02_no_alias_copies(policy: SandboxPolicy) -> dict:
    """No symlink or hardlink inside the lab may alias a protected source."""
    offenders: list[dict] = []
    skip_dirs = {"environments", ".cache", "wheelhouse", ".git"}
    for path in policy.lab_root.rglob("*"):
        rel_first = path.relative_to(policy.lab_root).parts[0] if path != policy.lab_root else ""
        if rel_first in skip_dirs:
            continue
        if path.is_symlink():
            target = realpath(path)
            escapes = not str(target).startswith(str(policy.lab_root))
            offenders.append({"path": str(path), "target": str(target), "escapes_lab": escapes, "code": "SYMLINK"})
        elif path.is_file() and path.stat().st_nlink > 1:
            offenders.append({"path": str(path), "nlink": path.stat().st_nlink, "code": "HARDLINK"})
    escaping = [o for o in offenders if o.get("escapes_lab") or o["code"] == "HARDLINK"]
    return _record(
        "T02", "editable copies are physical, not aliases",
        "PASS" if not escaping else "FAIL",
        "no symlink escaping LAB_ROOT and no multi-link file among lab-owned sources",
        {"offender_count": len(escaping)},
        {"offenders": offenders[:20]},
    )


def check_t03_zip_guard(policy: SandboxPolicy) -> dict:
    """A hostile zip must be rejected during inventory, before extraction."""
    import zipfile

    with tempfile.TemporaryDirectory(dir=policy.lab_root / ".cache") as tmp:
        hostile = Path(tmp) / "hostile.zip"
        with zipfile.ZipFile(hostile, "w") as zf:
            zf.writestr("../escape.py", "x = 1\n")
            zf.writestr("/abs/evil.py", "x = 1\n")
            zf.writestr("vwap.py", "x = 1\n")
            zf.writestr("vwap.py", "x = 2\n")  # duplicate
            info = zipfile.ZipInfo("link.py")
            info.external_attr = (0xA1FF) << 16  # symlink mode bits
            zf.writestr(info, "/etc/passwd")
        inspection = archive_mod.inspect_zip(hostile)
        codes = sorted({r["code"] for r in inspection.rejections})
        benign = Path(tmp) / "benign.zip"
        with zipfile.ZipFile(benign, "w") as zf:
            zf.writestr("vwap.py", "x = 1\n")
        benign_inspection = archive_mod.inspect_zip(benign)
    required = {"PATH_TRAVERSAL", "ABSOLUTE_PATH", "DUPLICATE_ENTRY", "SYMLINK_MEMBER"}
    ok = required.issubset(set(codes)) and not inspection.admissible
    return _record(
        "T03", "zip traversal/absolute/symlink/duplicate rejected before extract",
        "PASS" if ok else "FAIL",
        f"hostile archive rejected with at least {sorted(required)}; benign single-file archive admissible",
        {"hostile_rejection_codes": codes, "hostile_admissible": inspection.admissible,
         "benign_admissible": benign_inspection.admissible},
    )


def check_t04_alpha_allowlist(policy: SandboxPolicy) -> dict:
    """The four supplied alphas must match the published digests exactly."""
    source_dir = policy.raw.get("alpha_source_dir")
    if not source_dir:
        candidates = [p for p in policy.protected_roots if p.name == "alpha_to_tes_regime_model"]
        source_dir = candidates[0] if candidates else None
    if source_dir is None:
        return _record("T04", "four-file allowlist and digests", "BLOCKED",
                       "alpha source dir resolvable", None, {"reason": "no alpha source dir in policy"})
    verification = archive_mod.verify_alpha_files(source_dir, policy)
    return _record(
        "T04", "four-file allowlist and digests",
        "PASS" if verification["status"] == "VERIFIED" else "FAIL",
        "exactly the four allowed files, each matching the guide digest, no extra .py",
        {"status": verification["status"], "problems": verification["problems"]},
        {"files": {k: {"sha256": v["sha256"], "matches": v["matches"]} for k, v in verification["files"].items()}},
    )


def check_t05_caches_inside_lab(policy: SandboxPolicy) -> dict:
    """Cache redirection PLUS a kernel-refused write to a fake protected path."""
    env = process_mod.lab_worker_env(policy)
    offenders = process_mod.cache_paths_inside_lab(env, policy)

    # In-process guard (hygiene layer).
    fixture = policy.lab_root / ".cache" / "fake_protected_fixture"
    fixture.mkdir(parents=True, exist_ok=True)
    fixture_policy = SandboxPolicy(lab_root=policy.lab_root, protected_roots=(realpath(fixture),))
    guard_refused = False
    try:
        fixture_policy.resolve_write_target(fixture / "should_not_write.txt")
    except SafetyViolation:
        guard_refused = True

    # OS layer: the same write must be refused by the kernel inside the sandbox.
    isolation = sandbox_mod.probe_isolation(policy)
    kernel_refused = bool(isolation.checks.get("fake_protected_write_refused"))
    errno = isolation.checks.get("fake_protected_errno")

    ok = not offenders and guard_refused and kernel_refused
    return _record(
        "T05", "worker caches redirected into the lab; protected-path write refused by the kernel",
        "PASS" if ok else "FAIL",
        "no cache variable outside LAB_ROOT; write to a (fake) protected path refused by BOTH the guard and the OS",
        {"cache_offenders": offenders, "guard_refused": guard_refused,
         "kernel_refused": kernel_refused, "kernel_errno": errno},
        {"pythondontwritebytecode": env.get("PYTHONDONTWRITEBYTECODE"),
         "numba_cache_dir": env.get("NUMBA_CACHE_DIR"),
         "note": "errno 30 (EROFS) is the read-only bind mount refusing the write"},
    )


def check_t06_no_credentials(policy: SandboxPolicy) -> dict:
    """No credentials in the worker env, and no route out of the network namespace."""
    probe_base = dict(os.environ)
    probe_base.update({"BINANCE_API_KEY": "x", "DB_PASSWORD": "y", "SOME_TOKEN": "z"})
    env = process_mod.lab_worker_env(policy, network=False, base=probe_base)
    leaked = [k for k in env if any(m in k.upper() for m in process_mod.CREDENTIAL_ENV_MARKERS)
              and k not in process_mod.CREDENTIAL_ENV_ALLOWLIST]

    isolation = sandbox_mod.probe_isolation(policy)
    network_blocked = bool(isolation.checks.get("network_blocked"))
    dns_blocked = bool(isolation.checks.get("dns_blocked"))
    creds_in_worker = isolation.checks.get("credential_env_vars", ["<not probed>"])

    ok = not leaked and network_blocked and dns_blocked and creds_in_worker == []
    return _record(
        "T06", "no live credentials in a replay worker; network unreachable at OS level",
        "PASS" if ok else "FAIL",
        "credential-shaped vars stripped AND an isolated worker cannot reach the network or resolve DNS",
        {"leaked_from_env_builder": leaked, "credentials_visible_in_worker": creds_in_worker,
         "network_blocked": network_blocked, "dns_blocked": dns_blocked,
         "network_errno": isolation.checks.get("network_errno")},
        {"note": "errno 101 (ENETUNREACH) comes from an empty network namespace, not from a proxy variable"},
    )


def check_t07_resource_budget(policy: SandboxPolicy) -> dict:
    """Budget declared, memory cap actually enforced, cancellation scoped, disk within quota."""
    budget = process_mod.ResourceBudget.from_policy(policy)
    foreign = process_mod.terminate_own_group(os.getpgid(0) + 100000)
    disk = process_mod.disk_usage_report(policy)

    # Real enforcement: an over-budget worker must die alone.
    over_budget_code = (
        "import numpy as np\n"
        "blocks = []\n"
        "for _ in range(40):\n"
        "    blocks.append(np.zeros(8 * 1024 * 1024, dtype=np.float64))\n"
        "print('NEVER_REACHED')\n"
    )
    try:
        completed = sandbox_mod.run_isolated_python(policy, over_budget_code, memory_gib=1, timeout_s=120)
        worker_died = completed.returncode != 0 and "NEVER_REACHED" not in completed.stdout
        worker_detail = (completed.stderr.strip().splitlines() or ["<no stderr>"])[-1][:200]
    except Exception as exc:
        worker_died = False
        worker_detail = f"probe failed: {type(exc).__name__}: {exc}"

    ok = foreign["status"] == "REFUSED" and worker_died and disk["within_quota"]
    return _record(
        "T07", "budget enforced: over-budget worker dies alone, cancel scoped, disk within quota",
        "PASS" if ok else "FAIL",
        "memory cap kills only the worker; foreign process group refused; lab disk usage under quota",
        {"budget": budget.__dict__, "foreign_group_result": foreign["status"],
         "over_budget_worker_died": worker_died, "parent_survived": True,
         "disk_within_quota": disk["within_quota"], "lab_gib_used": disk["lab_gib_used"]},
        {"worker_error": worker_detail, "disk": disk},
    )


def check_t08_source_integrity(policy: SandboxPolicy) -> dict:
    """Protected source digests must be recordable for before/after comparison."""
    manifests: dict[str, dict] = {}
    for protected in policy.protected_roots:
        if protected.name == "alpha_to_tes_regime_model":
            manifests[str(protected)] = manifest_directory(protected, ("*.py",))
    if not manifests:
        return _record("T08", "protected-source integrity manifest", "BLOCKED",
                       "at least one protected root manifested", None, {"reason": "no manifestable protected root"})
    total = sum(len(m) for m in manifests.values())
    return _record(
        "T08", "protected-source integrity manifest",
        "PASS" if total > 0 else "FAIL",
        "digest manifest built for protected alpha sources (compared again at run end)",
        {"file_count": total},
        {"manifests": manifests},
    )


ALL_CHECKS: tuple[tuple[str, CheckFn], ...] = (
    ("ISO", check_iso_containment),
    ("T01", check_t01_lab_root),
    ("T02", check_t02_no_alias_copies),
    ("T03", check_t03_zip_guard),
    ("T04", check_t04_alpha_allowlist),
    ("T05", check_t05_caches_inside_lab),
    ("T06", check_t06_no_credentials),
    ("T07", check_t07_resource_budget),
    ("T08", check_t08_source_integrity),
)


def run_all(policy: SandboxPolicy) -> dict:
    results = []
    for check_id, fn in ALL_CHECKS:
        try:
            results.append(fn(policy))
        except Exception as exc:  # a crashing check is a failure, not a silent skip
            results.append(_record(check_id, fn.__doc__ or check_id, "FAIL",
                                   "check runs without raising", None,
                                   {"error_type": type(exc).__name__, "error": str(exc)}))
    statuses = [r["status"] for r in results]
    iso = next((r for r in results if r["id"] == "ISO"), None)
    return {
        "schema": "crypto_regime_lab.preflight.v1",
        "results": results,
        "counts": {s: statuses.count(s) for s in sorted(set(statuses))},
        "gate": "PASS" if all(s == "PASS" for s in statuses) else "FAIL",
        "os_isolation_available": bool(iso and iso["status"] == "PASS"),
        "containment_claim": (
            iso["detail"]["claim"] if iso and "claim" in iso.get("detail", {}) else "unknown"
        ),
    }
