import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

import pytest

from crypto_regime_lab.safety.paths import SandboxPolicy


@pytest.fixture(scope="session")
def lab_root() -> Path:
    return LAB_ROOT


@pytest.fixture(scope="session")
def policy(lab_root) -> SandboxPolicy:
    return SandboxPolicy.load(lab_root / "configs" / "sandbox_policy.json")


@pytest.fixture
def lab_tmp(policy):
    """A scratch directory INSIDE LAB_ROOT.

    pytest's tmp_path lives outside the lab, where the read guard (correctly)
    refuses to open files, so fixtures that must be read through the guard
    belong here instead.
    """
    import shutil
    import uuid

    path = policy.lab_root / ".cache" / "pytest" / uuid.uuid4().hex[:10]
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
