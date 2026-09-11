"""OS-level containment tests (guide 0.2) — the debt LAB-01 originally left open.

These assert that containment is provided by the kernel, not by our own code.
The protected-write probe uses a FAKE fixture; the real protected roots are
checked read-only via mountinfo, never by attempting a write against them.
"""

from __future__ import annotations

import shutil

import pytest

from crypto_regime_lab.safety import sandbox as sandbox_mod

pytestmark = pytest.mark.skipif(shutil.which("bwrap") is None, reason="bubblewrap not installed")


@pytest.fixture(scope="module")
def isolation(policy):
    return sandbox_mod.probe_isolation(policy)


def test_isolation_is_available_and_measured(isolation):
    assert isolation.available is True, isolation.failures
    assert isolation.bwrap_version and isolation.bwrap_version.startswith("bubblewrap")


def test_lab_root_is_writable_inside_the_sandbox(isolation):
    assert isolation.checks["lab_root_writable"] is True


def test_write_to_fake_protected_path_is_refused_by_the_kernel(isolation):
    assert isolation.checks["fake_protected_write_refused"] is True
    assert isolation.checks["fake_protected_errno"] == 30, "expected EROFS from a read-only bind"


def test_every_protected_root_is_mounted_read_only(isolation):
    mounts = isolation.checks["protected_mounts"]
    assert mounts, "no protected roots were inspected"
    for root, record in mounts.items():
        assert record["read_only"] is True, f"{root} is not read-only inside the worker"


def test_quantbt_repo_specifically_is_read_only(isolation):
    """The user's repo is the one path that must never be writable from a worker."""
    mounts = isolation.checks["protected_mounts"]
    quantbt = [r for r in mounts if r.endswith("/pool_alpha/quantbt")]
    assert quantbt, "the quantbt repo must be an explicitly declared protected root"
    assert mounts[quantbt[0]]["read_only"] is True


def test_replay_worker_has_no_network(isolation):
    assert isolation.checks["network_blocked"] is True
    assert isolation.checks["network_errno"] == 101, "expected ENETUNREACH from an empty netns"
    assert isolation.checks["dns_blocked"] is True


def test_worker_environment_carries_no_credentials(isolation):
    assert isolation.checks["credential_env_vars"] == []


def test_worker_cannot_see_the_host_process_table(isolation):
    assert isolation.checks["visible_pids"] <= 5, isolation.checks["visible_pids"]


def test_over_budget_worker_dies_without_taking_the_parent(policy):
    code = (
        "import numpy as np\n"
        "blocks = []\n"
        "for _ in range(40):\n"
        "    blocks.append(np.zeros(8 * 1024 * 1024, dtype=np.float64))\n"
        "print('NEVER_REACHED')\n"
    )
    completed = sandbox_mod.run_isolated_python(policy, code, memory_gib=1, timeout_s=120)
    assert completed.returncode != 0
    assert "NEVER_REACHED" not in completed.stdout
    assert "MemoryError" in completed.stderr or "Unable to allocate" in completed.stderr


def test_acquisition_stage_can_opt_into_network(policy):
    """Network is a deliberate, separate stage — not the default for workers."""
    argv_no_net = sandbox_mod.build_bwrap_argv(policy, ["/bin/true"], network=False)
    argv_net = sandbox_mod.build_bwrap_argv(policy, ["/bin/true"], network=True)
    assert "--unshare-net" in argv_no_net
    assert "--unshare-net" not in argv_net


def test_sandbox_clears_the_environment_before_setting_its_own(policy):
    argv = sandbox_mod.build_bwrap_argv(policy, ["/bin/true"])
    assert "--clearenv" in argv
    assert argv.index("--clearenv") < argv.index("--setenv")
