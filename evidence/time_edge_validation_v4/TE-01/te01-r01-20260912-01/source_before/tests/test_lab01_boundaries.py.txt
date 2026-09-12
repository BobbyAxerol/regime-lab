"""Boundary tests: unpacked raw alphas, source boundary, data read-lock policy."""

from __future__ import annotations

import json

import pytest

from crypto_regime_lab.safety.archive import ALLOWED_ALPHA_FILES
from crypto_regime_lab.safety.paths import sha256_file

RAW_SUPPLIED = "src/crypto_regime_lab/alphas/raw-supplied"


# --- unpacked alpha sources -------------------------------------------

def test_zip_was_removed_from_the_alphas_package(lab_root):
    assert not (lab_root / "src/crypto_regime_lab/alphas/alpha_to_tes_regime_model.zip").exists()


def test_retained_archive_still_provides_provenance(lab_root):
    retained = lab_root / "vendor_readonly" / "alpha_zip_original.zip"
    assert retained.is_file(), "deleting the zip is only safe while the retained copy exists"
    assert sha256_file(retained) == "57406dbb9ffdcf4617e4895925126fa73600a585a6541f996c6b2d980f6701ae"


def test_four_alphas_are_unpacked_read_only_with_guide_digests(lab_root):
    dest = lab_root / RAW_SUPPLIED
    for name, expected in ALLOWED_ALPHA_FILES.items():
        target = dest / name
        assert target.is_file(), f"{name} missing from {RAW_SUPPLIED}"
        assert sha256_file(target) == expected
        assert target.stat().st_mode & 0o222 == 0, f"{name} must stay read-only"


def test_unpacked_files_match_the_vendor_readonly_provenance_copies(lab_root):
    dest = lab_root / RAW_SUPPLIED
    raw = lab_root / "vendor_readonly" / "alphas_raw"
    for name in ALLOWED_ALPHA_FILES:
        assert sha256_file(dest / name) == sha256_file(raw / name)


def test_raw_supplied_cannot_be_imported(lab_root):
    """Guide L01.3: the original modules must not be runnable before containment.

    Two weaker guards were measured to be insufficient and are recorded here so
    nobody re-introduces them: a plain underscore directory without
    ``__init__.py`` is importable via PEP 420, and a hyphenated name only blocks
    the ``import`` statement's syntax, not ``importlib.import_module``.
    """
    import importlib

    dest = lab_root / RAW_SUPPLIED
    assert (dest / "DO_NOT_IMPORT.md").is_file()
    assert not dest.name.isidentifier(), "directory name must not be a valid Python identifier"
    assert (dest / "__init__.py").is_file(), "the raising guard must exist"

    with pytest.raises(ImportError):
        importlib.import_module("crypto_regime_lab.alphas.raw-supplied")
    with pytest.raises(ImportError):
        importlib.import_module("crypto_regime_lab.alphas.raw-supplied.vwap")
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("crypto_regime_lab.alphas.raw_supplied.vwap")


def test_underscore_namespace_layout_really_would_have_been_importable(lab_tmp):
    """Evidence for why the guard above is not paranoia."""
    import importlib.util
    import sys

    pkg = lab_tmp / "pkgprobe" / "alphas" / "raw_supplied"
    pkg.mkdir(parents=True)
    (pkg / "vwap.py").write_text("x = 1\n", encoding="utf-8")
    sys.path.insert(0, str(lab_tmp))
    try:
        assert importlib.util.find_spec("pkgprobe.alphas.raw_supplied.vwap") is not None
    finally:
        sys.path.remove(str(lab_tmp))
        for name in list(sys.modules):
            if name.startswith("pkgprobe"):
                del sys.modules[name]


def test_alpha_sources_have_no_module_level_side_effects(lab_root):
    """Static check: nothing outside imports/defs/literals runs at module level.

    Bounds the blast radius of the accidental import that happened while the
    guard above was being developed.
    """
    import ast

    inert = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Import, ast.ImportFrom)
    literal = (ast.Constant, ast.Dict, ast.List, ast.Tuple, ast.Name)
    findings = {}
    for path in sorted((lab_root / RAW_SUPPLIED).glob("*.py")):
        if path.name == "__init__.py":
            continue
        effects = []
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, inert):
                continue
            if isinstance(node, ast.Assign) and isinstance(node.value, literal):
                continue
            effects.append(f"L{node.lineno} {type(node).__name__}")
        findings[path.name] = effects
    assert findings["vwap.py"] == []
    assert findings["adaptive_hma_cpp.py"] == []
    assert findings["signal_combine.py"] == []
    assert findings["hash_momentum.py"] == ["L164 Expr"], findings["hash_momentum.py"]


def test_no_alpha_module_has_been_imported():
    import sys

    for name in ("vwap", "hash_momentum", "adaptive_hma_cpp", "signal_combine"):
        assert name not in sys.modules
        assert not any(mod.endswith(f".{name}") for mod in sys.modules)


# --- source boundary ---------------------------------------------------

@pytest.fixture(scope="module")
def boundary(lab_root):
    paths = sorted((lab_root / "evidence").rglob("source_boundary.json"))
    if not paths:
        pytest.skip("run scripts/record_boundaries.py")
    return json.loads(paths[-1].read_text())


def test_reading_upstream_repos_did_not_modify_them(boundary):
    for path, record in boundary["repositories"].items():
        assert record["probe_left_repo_unmodified"] is True, path
        assert record["read_method"].startswith("GIT_OPTIONAL_LOCKS=0")


def test_quantbt_repo_is_clean_and_not_consumed_by_the_lab(boundary):
    quantbt = boundary["repositories"]["/root/bobby/pool_alpha/quantbt"]
    assert quantbt["dirty"] is False
    assert quantbt["dirty_entry_count"] == 0
    assert boundary["quantbt_boundary"]["the_lab_does_not_consume_this_repo"] is True
    assert boundary["write_operations_issued_against_protected_roots"] == 0


def test_alpha_source_digests_are_recorded_in_the_boundary(boundary):
    manifest = boundary["alpha_source_boundary"]["digest_manifest"]
    assert set(manifest) == set(ALLOWED_ALPHA_FILES)
    for name, digest in manifest.items():
        assert digest == ALLOWED_ALPHA_FILES[name]


# --- data read-lock policy ---------------------------------------------

def test_data_readlock_policy_is_registered(lab_root):
    path = lab_root / "configs" / "data_readlock_policy.json"
    if not path.is_file():
        pytest.skip("run scripts/record_boundaries.py")
    doc = json.loads(path.read_text())
    assert doc["status"] == "POLICY_REGISTERED_EXECUTION_PENDING_LAB03"
    assert doc["execution_owner"].startswith("LAB-03")
    joined = " ".join(doc["rules"]).lower()
    assert "never runs a collector" in joined
    assert "external_data_drift" in joined
    assert "missing coverage" in joined
    assert doc["known_mutable_roots"], "the storage root must be named, not left implicit"
