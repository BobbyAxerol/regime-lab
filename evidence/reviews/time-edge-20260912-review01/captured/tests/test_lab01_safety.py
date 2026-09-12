"""LAB-01 acceptance tests T01-T08 plus the strict-JSON gate T61.

Each test names the guide requirement it implements. Nothing here writes outside
LAB_ROOT and nothing probes the real protected trees for write access — the
protected-path rejection is exercised against a fake fixture (guide LAB-01 gate).
"""

from __future__ import annotations

import math
import os
import zipfile
from pathlib import Path

import pytest

from crypto_regime_lab.evidence.manifest import EvidenceWriter, NonFiniteValue, dumps_strict, sanitize_numeric
from crypto_regime_lab.safety import checks as checks_mod
from crypto_regime_lab.safety import process as process_mod
from crypto_regime_lab.safety.archive import (
    ALLOWED_ALPHA_FILES, assert_alpha_sources_ok, inspect_zip, verify_alpha_files,
)
from crypto_regime_lab.safety.paths import SafetyViolation, SandboxPolicy, realpath


# --- T01 -----------------------------------------------------------------

def test_t01_lab_root_outside_protected_roots(policy):
    assert policy.validate_lab_root() == []


def test_t01_lab_root_inside_protected_root_is_rejected(policy):
    inside = SandboxPolicy(
        lab_root=policy.protected_roots[0] / "pretend_lab",
        protected_roots=policy.protected_roots,
    )
    problems = inside.validate_lab_root()
    assert problems, "a LAB_ROOT nested in a protected root must be rejected"
    assert "inside protected root" in problems[0]
    with pytest.raises(SafetyViolation):
        inside.assert_lab_root_ok()


def test_t01_lab_root_containing_protected_root_is_rejected(policy):
    swallowing = SandboxPolicy(lab_root=realpath("/root/bobby/pool_alpha"), protected_roots=policy.protected_roots)
    assert any("is inside LAB_ROOT" in p for p in swallowing.validate_lab_root())


# --- T02 -----------------------------------------------------------------

def test_t02_write_target_escaping_lab_is_refused(policy):
    with pytest.raises(SafetyViolation):
        policy.resolve_write_target("/root/bobby/pool_alpha/quantbt/should_never_exist.txt")
    with pytest.raises(SafetyViolation):
        policy.resolve_write_target(policy.lab_root / ".." / "escape.txt")


def test_t02_symlinked_parent_cannot_smuggle_a_write(policy, tmp_path):
    """A not-yet-existing file under a symlinked parent resolves to its real target."""
    link = policy.lab_root / ".cache" / "t02_link"
    if link.exists() or link.is_symlink():
        link.unlink()
    link.symlink_to(tmp_path)  # tmp_path is outside LAB_ROOT
    try:
        with pytest.raises(SafetyViolation):
            policy.resolve_write_target(link / "sneaky.json")
    finally:
        link.unlink()


def test_t02_repo_has_no_aliasing_copies(policy):
    result = checks_mod.check_t02_no_alias_copies(policy)
    assert result["status"] == "PASS", result


# --- T03 -----------------------------------------------------------------

@pytest.fixture
def hostile_zip(tmp_path) -> Path:
    path = tmp_path / "hostile.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("../escape.py", "x = 1\n")
        zf.writestr("/abs/evil.py", "x = 1\n")
        info = zipfile.ZipInfo("link.py")
        info.external_attr = 0xA1FF << 16
        zf.writestr(info, "/etc/passwd")
        zf.writestr("unexpected_alpha.py", "x = 1\n")
    return path


def test_t03_hostile_zip_rejected_before_extraction(hostile_zip):
    inspection = inspect_zip(hostile_zip)
    codes = {r["code"] for r in inspection.rejections}
    assert {"PATH_TRAVERSAL", "ABSOLUTE_PATH", "SYMLINK_MEMBER", "NOT_IN_ALLOWLIST"} <= codes
    assert not inspection.admissible


def test_t03_duplicate_member_rejected(tmp_path):
    path = tmp_path / "dupe.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("vwap.py", "a\n")
        zf.writestr("vwap.py", "b\n")
    assert "DUPLICATE_ENTRY" in {r["code"] for r in inspect_zip(path).rejections}


def test_t03_benign_allowlisted_zip_is_admissible(tmp_path):
    path = tmp_path / "ok.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("vwap.py", "x = 1\n")
        zf.writestr("__MACOSX/._vwap.py", "junk")
    assert inspect_zip(path).admissible


# --- T04 -----------------------------------------------------------------

def test_t04_four_alpha_digests_match_guide(policy):
    source = next(p for p in policy.protected_roots if p.name == "alpha_to_tes_regime_model")
    verification = verify_alpha_files(source, policy)
    assert verification["status"] == "VERIFIED", verification["problems"]
    assert set(verification["files"]) == set(ALLOWED_ALPHA_FILES)
    for name, record in verification["files"].items():
        assert record["matches"], f"{name} digest drifted from the guide manifest"


def test_t04_digest_drift_is_a_stop_condition(policy, tmp_path):
    """A changed file, or a fifth file, must stop the lab rather than be adopted."""
    for name in ALLOWED_ALPHA_FILES:
        (tmp_path / name).write_text("# tampered\n", encoding="utf-8")
    fake_policy = SandboxPolicy(lab_root=policy.lab_root, protected_roots=(realpath(tmp_path),))
    verification = verify_alpha_files(tmp_path, fake_policy)
    assert verification["status"] == "STOP_REQUIRED"
    assert {p["code"] for p in verification["problems"]} == {"DIGEST_MISMATCH"}
    with pytest.raises(SafetyViolation):
        assert_alpha_sources_ok(verification)


def test_t04_extra_python_file_is_flagged(policy, tmp_path):
    source = next(p for p in policy.protected_roots if p.name == "alpha_to_tes_regime_model")
    for name in ALLOWED_ALPHA_FILES:
        (tmp_path / name).write_bytes((source / name).read_bytes())
    (tmp_path / "fifth_alpha.py").write_text("x = 1\n", encoding="utf-8")
    fake_policy = SandboxPolicy(lab_root=policy.lab_root, protected_roots=(realpath(tmp_path),))
    verification = verify_alpha_files(tmp_path, fake_policy)
    assert "UNEXPECTED_PY_FILES" in {p["code"] for p in verification["problems"]}


# --- T05 -----------------------------------------------------------------

def test_t05_worker_caches_resolve_inside_lab(policy):
    env = process_mod.lab_worker_env(policy)
    assert process_mod.cache_paths_inside_lab(env, policy) == []
    assert env["PYTHONDONTWRITEBYTECODE"] == "1"


def test_t05_write_to_fake_protected_path_is_denied(policy, tmp_path):
    """Positive control on a FAKE protected root; the real trees are never probed."""
    fixture = tmp_path / "fake_protected"
    fixture.mkdir()
    guarded = SandboxPolicy(lab_root=policy.lab_root, protected_roots=(realpath(fixture),))
    with pytest.raises(SafetyViolation):
        guarded.resolve_write_target(fixture / "cache_entry.bin")


# --- T06 -----------------------------------------------------------------

def test_t06_credentials_stripped_from_worker_env(policy):
    base = dict(os.environ)
    base.update({"BINANCE_API_KEY": "k", "DB_PASSWORD": "p", "EXCHANGE_SECRET": "s", "SOME_TOKEN": "t"})
    env = process_mod.lab_worker_env(policy, network=False, base=base)
    for leaked in ("BINANCE_API_KEY", "DB_PASSWORD", "EXCHANGE_SECRET", "SOME_TOKEN"):
        assert leaked not in env
    assert env["CRYPTO_REGIME_LAB_NETWORK"] == "disabled"


def test_t06_acquisition_stage_is_labelled_differently(policy):
    env = process_mod.lab_worker_env(policy, network=True)
    assert env["CRYPTO_REGIME_LAB_NETWORK"] == "acquisition_stage"


# --- T07 -----------------------------------------------------------------

def test_t07_cancel_refuses_foreign_process_group(policy):
    foreign = process_mod.terminate_own_group(os.getpgid(0) + 100000)
    assert foreign["status"] == "REFUSED"


def test_t07_budget_matches_policy(policy):
    budget = process_mod.ResourceBudget.from_policy(policy)
    assert budget.workers == 1 and budget.cpu_limit == 2 and budget.working_memory_gib == 4
    env = process_mod.lab_worker_env(policy)
    assert env["OMP_NUM_THREADS"] == "2"


# --- T08 -----------------------------------------------------------------

def test_t08_protected_sources_unchanged_since_bootstrap(policy, lab_root):
    """Digest the protected alphas now and compare against the bootstrap baseline."""
    import json

    baselines = sorted((lab_root / "evidence").rglob("source_integrity_baseline.json"))
    assert baselines, "bootstrap must have written a source integrity baseline"
    recorded = json.loads(baselines[-1].read_text())["manifests"]
    from crypto_regime_lab.safety.paths import manifest_directory

    for root, expected in recorded.items():
        assert manifest_directory(root, ("*.py",)) == expected, f"protected source drifted under {root}"


# --- T61 (strict JSON), enforced from LAB-01 onward -----------------------

def test_t61_nan_and_inf_are_refused_by_the_writer():
    with pytest.raises(NonFiniteValue):
        dumps_strict({"metric": float("nan")})
    with pytest.raises(NonFiniteValue):
        dumps_strict({"metric": float("inf")})


def test_t61_sanitize_numeric_yields_null_plus_status():
    assert sanitize_numeric(float("nan")) == (None, "NAN")
    assert sanitize_numeric(float("inf")) == (None, "POS_INF")
    assert sanitize_numeric(float("-inf")) == (None, "NEG_INF")
    assert sanitize_numeric(1.5) == (1.5, None)
    assert not math.isnan(1.5)


def test_evidence_writer_is_atomic_and_ledgered(policy):
    writer = EvidenceWriter.open(policy, study_id="selftest")
    with writer.attempt("selftest.op") as att:
        att.detail = {"k": 1}
        record = writer.write_json("probe.json", {"value": 1})
    assert Path(record["artifact_path"]).is_file()
    ledger = (writer.run_dir / "attempts.jsonl").read_text().strip().splitlines()
    assert len(ledger) == 2 and '"STARTED"' in ledger[0] and '"SUCCESS"' in ledger[1]
    assert not list(writer.run_dir.glob("*.tmp-*")), "no temp file may survive an atomic write"


def test_evidence_writer_records_failed_attempts(policy):
    writer = EvidenceWriter.open(policy, study_id="selftest")
    with pytest.raises(RuntimeError):
        with writer.attempt("selftest.failing"):
            raise RuntimeError("deliberate")
    ledger = (writer.run_dir / "attempts.jsonl").read_text()
    assert '"FAILED"' in ledger and "deliberate" in ledger
