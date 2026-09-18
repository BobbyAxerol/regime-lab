"""OS-level worker isolation (guide 0.2 — the containment the lab actually needs).

Path guards alone are hygiene. This module runs lab workers inside a bubblewrap
mount/network/pid namespace where:

  * ``LAB_ROOT`` is the only writable path;
  * every other filesystem path, including the protected roots, is a read-only
    bind — a write is refused by the kernel, not by our code;
  * the network namespace is empty, so a replay worker has no route out;
  * the environment is cleared and rebuilt, so no credential can leak in.

The capability is *probed*, never assumed. If bubblewrap is missing or the
namespaces cannot be created, ``probe_isolation`` says so and the lab must stay
at scaffold/synthetic scope rather than claim containment it does not have.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .paths import SandboxPolicy
from .process import lab_worker_env

BWRAP = "bwrap"
DEFAULT_TIMEOUT_S = 300


class IsolationUnavailable(RuntimeError):
    """Raised when isolated execution is requested but cannot be provided."""


@dataclass
class IsolationReport:
    """Measured containment capability. ``available`` is only ever set by a probe."""

    available: bool
    mechanism: str | None
    bwrap_path: str | None
    bwrap_version: str | None
    checks: dict = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)

    def as_record(self) -> dict:
        return {
            "schema": "crypto_regime_lab.os_isolation.v1",
            "available": self.available,
            "mechanism": self.mechanism,
            "bwrap_path": self.bwrap_path,
            "bwrap_version": self.bwrap_version,
            "checks": self.checks,
            "failures": self.failures,
            "claim": (
                "Worker writes outside LAB_ROOT are refused by the kernel (read-only bind mounts) "
                "and replay workers have an empty network namespace."
                if self.available
                else "No OS-level isolation: path guards are hygiene only and no containment is claimed."
            ),
        }


def bwrap_version() -> str | None:
    path = shutil.which(BWRAP)
    if not path:
        return None
    try:
        out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def build_bwrap_argv(
    policy: SandboxPolicy,
    argv: list[str],
    *,
    network: bool = False,
    extra_writable: tuple[Path, ...] = (),
    extra_readonly: tuple[Path, ...] = (),
    env: dict[str, str] | None = None,
) -> list[str]:
    """Compose the bubblewrap command line for one lab worker.

    ``--ro-bind / /`` makes the whole filesystem read-only, then ``LAB_ROOT`` is
    re-bound writable. Protected roots are re-stated as explicit read-only binds
    so the intent survives any later change to the base mount.
    """
    bwrap = shutil.which(BWRAP)
    if not bwrap:
        raise IsolationUnavailable("bubblewrap (bwrap) is not installed")
    worker_env = dict(env if env is not None else lab_worker_env(policy, network=network))

    cmd = [
        bwrap,
        "--ro-bind", "/", "/",
        "--dev", "/dev",
        "--proc", "/proc",
        "--tmpfs", "/tmp",
        "--bind", str(policy.lab_root), str(policy.lab_root),
    ]
    for extra in extra_writable:
        cmd += ["--bind", str(extra), str(extra)]
    for protected in policy.protected_roots:
        if protected.exists():
            cmd += ["--ro-bind", str(protected), str(protected)]
    # Applied last so a read-only subtree wins over the writable LAB_ROOT bind.
    for readonly in extra_readonly:
        if readonly.exists():
            cmd += ["--ro-bind", str(readonly), str(readonly)]
    cmd += ["--unshare-pid", "--unshare-ipc", "--unshare-uts", "--unshare-cgroup-try"]
    if not network:
        cmd += ["--unshare-net"]
    cmd += ["--die-with-parent", "--new-session", "--chdir", str(policy.lab_root), "--clearenv"]
    for key, value in sorted(worker_env.items()):
        cmd += ["--setenv", key, value]
    cmd += ["--"]
    cmd += argv
    return cmd


def run_isolated(
    policy: SandboxPolicy,
    argv: list[str],
    *,
    network: bool = False,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    env: dict[str, str] | None = None,
    extra_readonly: tuple[Path, ...] = (),
) -> subprocess.CompletedProcess:
    """Run ``argv`` inside the isolated namespace. Raises if isolation is unavailable."""
    cmd = build_bwrap_argv(policy, argv, network=network, env=env, extra_readonly=extra_readonly)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)


def run_isolated_python(
    policy: SandboxPolicy,
    code: str,
    *,
    network: bool = False,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    memory_gib: int | None = None,
    env: dict[str, str] | None = None,
    extra_readonly: tuple[Path, ...] = (),
) -> subprocess.CompletedProcess:
    """Run a Python snippet in the lab venv inside the isolated namespace.

    ``memory_gib`` applies an RLIMIT_AS inside the worker so an over-budget job
    dies in the worker and never takes the parent with it.
    """
    python = policy.lab_root / "environments" / "lab_venv" / "bin" / "python"
    prelude = ""
    if memory_gib is not None:
        prelude = (
            "import resource\n"
            f"_cap = {int(memory_gib)} * (1 << 30)\n"
            "resource.setrlimit(resource.RLIMIT_AS, (_cap, _cap))\n"
        )
    return run_isolated(
        policy, [str(python), "-c", prelude + code], network=network, timeout_s=timeout_s,
        env=env, extra_readonly=extra_readonly,
    )


def probe_isolation(policy: SandboxPolicy) -> IsolationReport:
    """Measure what containment this host actually provides.

    The protected-write probe deliberately targets a *fake* protected fixture
    inside the lab (guide LAB-01 gate: never probe the production repo for
    write access). Read-only status of the real protected roots is verified by
    reading the worker's own mountinfo instead of by attempting a write.
    """
    version = bwrap_version()
    path = shutil.which(BWRAP)
    report = IsolationReport(available=False, mechanism=None, bwrap_path=path, bwrap_version=version)
    if not path:
        report.failures.append("bwrap not installed")
        return report

    fixture = policy.lab_root / ".cache" / "fake_protected_fixture"
    fixture.mkdir(parents=True, exist_ok=True)
    (fixture / "sentinel.txt").write_text("do not modify\n", encoding="utf-8")

    probe_code = r"""
import json, os, socket, sys
result = {}

# 1. LAB_ROOT must be writable.
lab = os.environ["CRYPTO_REGIME_LAB_ROOT"]
probe = os.path.join(lab, ".cache", "isolation_probe.tmp")
try:
    with open(probe, "w") as fh:
        fh.write("ok")
    os.remove(probe)
    result["lab_root_writable"] = True
except OSError as exc:
    result["lab_root_writable"] = False
    result["lab_root_error"] = str(exc)

# 2. A write to a FAKE protected fixture must be refused by the kernel.
fake = os.environ["LAB_FAKE_PROTECTED"]
try:
    with open(os.path.join(fake, "should_not_exist"), "w") as fh:
        fh.write("x")
    result["fake_protected_write_refused"] = False
except OSError as exc:
    result["fake_protected_write_refused"] = True
    result["fake_protected_errno"] = exc.errno
    result["fake_protected_error"] = str(exc)

# 3. Real protected roots must be mounted read-only. Verified from mountinfo,
#    never by attempting a write against the production tree.
roots = json.loads(os.environ["LAB_PROTECTED_ROOTS"])
mounts = {}
with open("/proc/self/mountinfo") as fh:
    for line in fh:
        parts = line.split()
        mount_point = parts[4]
        opts = parts[5].split(",")
        mounts[mount_point] = opts
def flags_for(target):
    best, best_opts = "", None
    for mp, opts in mounts.items():
        if target == mp or target.startswith(mp.rstrip("/") + "/"):
            if len(mp) > len(best):
                best, best_opts = mp, opts
    return best, best_opts
result["protected_mounts"] = {}
for root in roots:
    mp, opts = flags_for(root)
    result["protected_mounts"][root] = {"mount_point": mp, "read_only": bool(opts and "ro" in opts)}

# 4. Network namespace must have no route out.
try:
    socket.setdefaulttimeout(3)
    socket.create_connection(("1.1.1.1", 53))
    result["network_blocked"] = False
except OSError as exc:
    result["network_blocked"] = True
    result["network_errno"] = exc.errno
try:
    socket.gethostbyname("pypi.org")
    result["dns_blocked"] = False
except OSError:
    result["dns_blocked"] = True

# 5. No credential-shaped variable may exist in the worker environment.
markers = ("KEY", "SECRET", "TOKEN", "PASSWORD", "PASSWD", "CREDENTIAL")
result["credential_env_vars"] = [k for k in os.environ if any(m in k.upper() for m in markers)]

# 6. PID namespace: the worker must not see the host process table.
result["visible_pids"] = len([p for p in os.listdir("/proc") if p.isdigit()])

print(json.dumps(result))
"""
    env = lab_worker_env(policy, network=False)
    env["LAB_FAKE_PROTECTED"] = str(fixture)
    env["LAB_PROTECTED_ROOTS"] = json.dumps([str(p) for p in policy.protected_roots])
    try:
        completed = run_isolated_python(
            policy, probe_code, network=False, timeout_s=90, env=env, extra_readonly=(fixture,)
        )
    except (IsolationUnavailable, OSError, subprocess.SubprocessError) as exc:
        report.failures.append(f"probe failed to launch: {type(exc).__name__}: {exc}")
        return report
    if completed.returncode != 0:
        report.failures.append(f"probe exited {completed.returncode}: {completed.stderr.strip()[:400]}")
        return report
    try:
        checks = json.loads(completed.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        report.failures.append(f"probe produced unreadable output: {completed.stdout[:400]}")
        return report

    report.checks = checks
    required = {
        "lab_root_writable": checks.get("lab_root_writable") is True,
        "fake_protected_write_refused": checks.get("fake_protected_write_refused") is True,
        "network_blocked": checks.get("network_blocked") is True,
        "no_credential_env": checks.get("credential_env_vars") == [],
        "protected_roots_read_only": all(
            m.get("read_only") for m in checks.get("protected_mounts", {}).values()
        ) and bool(checks.get("protected_mounts")),
    }
    report.checks["required"] = required
    report.failures = [name for name, ok in required.items() if not ok]
    report.available = not report.failures
    report.mechanism = "bubblewrap mount+net+pid namespace, read-only root, LAB_ROOT writable"
    return report


