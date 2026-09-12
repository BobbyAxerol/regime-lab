#!/usr/bin/env python3
"""TE-01 audit/contracts/baseline only. Never launch optimization or an account run.

``audit`` creates an immutable evidence generation. ``report`` reads committed
evidence; ``runtime-gate`` fails until measured prerequisites are satisfied.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import inspect
import json
import os
from pathlib import Path
import re
import resource
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from crypto_regime_lab.experiments import time_edge_contracts as C  # noqa: E402

STUDY = "time_edge_validation_v4"
CONFIG = ROOT / "configs" / STUDY
REGISTER = CONFIG / "r01"
BASE = ROOT / "evidence" / STUDY / "TE-01"
PROTECTED = ROOT.parent / "quantbt"
FUP = ROOT / "evidence/corrective_mode4_v3/FUP-02"


def stamp():
    return datetime.now(timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def strict(data):
    def reject(value):
        raise ValueError(f"nonfinite JSON: {value}")
    return json.loads(data, parse_constant=reject)


def read(path):
    return strict(Path(path).read_bytes())


def write_bytes(path, data):
    path = Path(path)
    if path.exists():
        if path.read_bytes() == data:
            return
        raise ValueError(f"append-only artifact differs: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)


def write(path, payload):
    write_bytes(path, (json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode())


def git(*args, cwd=ROOT):
    subprocess.run(["git", "status", "--porcelain"], cwd=cwd, capture_output=True, check=True)
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=True).stdout


def record(out, name, value):
    write(out / name, {"study_id": STUDY, "phase_id": "TE-01", "lab_run_id": out.name,
                      "schema": "regime_lab.te01." + name.removesuffix(".json") + ".v1", **value})


def protected_inventory():
    rows = []
    for name in git("ls-files", "-z", cwd=PROTECTED).split(b"\0"):
        if name:
            path = PROTECTED / name.decode()
            if path.is_file():
                rows.append({"path": str(path), "sha256": file_hash(path)})
    registry = read(ROOT / "configs/alpha_registry.json")
    for alpha, data in registry["alphas"].items():
        path = ROOT.parent / "alphas_storage/alpha_to_tes_regime_model" / data["filename"]
        actual = file_hash(path)
        rows.append({"path": str(path), "sha256": actual, "alpha": alpha,
                     "matches_registered_original": actual == data["sha256"]})
    loader = ROOT.parent / "alphas_storage/_get_data/data_loader.py"
    rows.append({"path": str(loader), "sha256": file_hash(loader), "role": "static_reference_not_imported"})
    return rows


def source_capture(out):
    selected = [ROOT / "AGENTS.md", ROOT / "CLAUDE.md", ROOT.parent / ".agents/AGENTS.md",
                ROOT / "implementation and test_edge_plan.md", ROOT / "configs/api_binding_map.json",
                ROOT / "configs/alpha_registry.json", ROOT / "configs/feature_schema.json",
                ROOT / "configs/correction_ledger.json",
                ROOT / "configs/sandbox_policy.json", ROOT / "configs/lab05_full_emission_tape.json",
                ROOT / "configs/lab05_regime_model_registry.json", ROOT / "configs/requirements.lock"]
    selected += [ROOT / name for name in (
        "QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md",
        "REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md")]
    selected += sorted(CONFIG.rglob("*.json"))
    selected += [path for folder in ("src", "scripts", "tests")
                 for path in sorted((ROOT / folder).rglob("*.py")) if not path.is_symlink()]
    rows = []
    for path in dict.fromkeys(selected):
        data = path.read_bytes()
        relative = os.path.relpath(path, ROOT)
        archived = "parent_workspace_rules.txt" if relative.startswith("../") else relative + ".txt"
        copy = out / "source_before" / archived
        write_bytes(copy, data)
        rows.append({"path": relative, "sha256": digest(data), "bytes": len(data),
                     "captured_path": copy.relative_to(out).as_posix()})
    record(out, "source_data_manifest.json", {"captured_at_utc": stamp(),
           "git_head": git("rev-parse", "HEAD").decode().strip(),
           "git_status": git("status", "--porcelain").decode(), "files": rows,
           "scope": "Immutable source/config bytes; dirty external FUP files are snapshots, not claimed committed code."})
    return rows


def snapshot_verify(out):
    import pyarrow.parquet as pq
    path = ROOT / "snapshots/server_core_v1/manifest.json"
    manifest = read(path)
    rows, started = [], time.monotonic()
    for item in manifest["files"]:
        file = Path(item["snapshot_path"]).resolve()
        if not file.is_relative_to(ROOT / "snapshots/server_core_v1"):
            raise ValueError("snapshot path escapes pinned lab snapshot")
        if time.monotonic() - started > 60:
            raise TimeoutError("snapshot verification exceeded its 60-second T0 cap")
        meta = pq.read_metadata(file)
        actual = file_hash(file)
        rows.append({"path": str(file.relative_to(ROOT)), "product": item["product_id"],
                     "symbol": item["symbol"], "partition": item["partition"],
                     "bytes": file.stat().st_size, "rows": meta.num_rows, "sha256": actual,
                     "hash_match": actual == item["sha256"], "size_match": file.stat().st_size == item["bytes"],
                     "rows_match": meta.num_rows == item["rows"], "closed": item["closed"],
                     "role": "TRAIN_OR_DEVELOPMENT" if item["partition"] < "2024-01" and item["closed"]
                     else "OUTSIDE_V4_DEVELOPMENT_OR_OPEN"})
    panels = [{"path": str(p.relative_to(ROOT)), "sha256": file_hash(p), "bytes": p.stat().st_size,
               "rows": pq.read_metadata(p).num_rows} for p in sorted((path.parent / "panels").glob("*.parquet"))]
    record(out, "snapshot_verification.json", {"manifest_sha256": file_hash(path), "files": rows,
           "panels": panels, "files_verified": len(rows), "bytes_verified": sum(x["bytes"] for x in rows),
           "all_manifest_entries_match": bool(rows) and all(r["hash_match"] and r["size_match"] and r["rows_match"] for r in rows),
           "elapsed_seconds": time.monotonic()-started, "source_data_loaded_for_returns": False,
           "limits": "Hash + parquet metadata verification. No re-collection, no claim of row-level market correctness or untouched data. Panels require raw-column causal reuse; full-sample scaled columns remain excluded."})


def binding_report(out):
    import quantbt
    from quantbt.walkforward import WalkForwardConfig, WalkForwardEngine
    from quantbt.core.research_audit import RESEARCH_RETENTION_LEVELS_V1
    origin = Path(quantbt.__file__).resolve()
    if not origin.is_relative_to(ROOT / "environments/lab_venv"):
        raise ValueError("QuantBT import did not resolve to the lab install")
    supplement = read(CONFIG / "mode4_binding_r01.json")
    config = WalkForwardConfig(**supplement["resolved_config"])
    resolved = {key: getattr(config, key) for key in supplement["resolved_config"]}
    packages = []
    for name in ("quantbt-engine", "quantbt-native", "numba", "numpy", "pandas", "optuna", "pyarrow"):
        dist = metadata.distribution(name)
        location = Path(dist.locate_file("")).resolve()
        if not location.is_relative_to(ROOT / "environments/lab_venv"):
            raise ValueError(f"package outside lab: {name}")
        natives = []
        if name == "quantbt-native":
            for item in dist.files or []:
                if str(item).endswith(".so"):
                    p = Path(dist.locate_file(item))
                    natives.append({"path": str(p), "sha256": file_hash(p), "bytes": p.stat().st_size})
        packages.append({"name": name, "version": dist.version, "location": str(location), "native_files": natives})
    wheel_rows = [{"path": str(p.relative_to(ROOT)), "sha256": file_hash(p), "bytes": p.stat().st_size}
                  for pattern in ("quantbt_engine-*.whl", "quantbt_native-*.whl", "numba-*.whl", "optuna-*.whl")
                  for p in sorted((ROOT / "wheelhouse").glob(pattern))]
    package_root = origin.parent
    vfy = {
        "VFY01": ("endpoint.py", r"def pct_equity|def _run_pct_equity_transition_native"),
        "VFY02": ("endpoint.py", r"def walk_forward|mode_4_is_only_robust"),
        "VFY03": ("walkforward.py", r"evaluate_oos_candidates=False|def _run_per_fold_schedule"),
        "VFY04": ("endpoint.py", r'native_prepared_wfo.*off'),
        "VFY05": ("backends/native_wfo_public.py", r"_RUST_DIRECT_TIMING.*same_close"),
        "VFY06": ("endpoint.py", r"fee_rate.*fee|fee.*2\.0"),
        "VFY07": ("metrics/performance.py", r"def profit_factor|stats_returns"),
        "VFY08": ("walkforward.py", r"candidate_decay|trade_penalty"),
        "VFY09": ("walkforward.py", r"def build_folds"),
        "VFY10": ("endpoint.py", r"def prepare_reactive_walk_forward|reset.flat"),
        "VFY11": ("backends/native_wfo_public.py", r'"turnover"|"mean_return"|"volatility"'),
    }
    matches = []
    for key, (filename, pattern) in vfy.items():
        path = package_root / filename
        source = path.read_text()
        found = [{"line": n, "text": line.strip()} for n, line in enumerate(source.splitlines(), 1)
                 if re.search(pattern, line)]
        write_bytes(out / "installed_source" / (filename + ".txt"), source.encode())
        matches.append({"id": key, "path": str(path), "sha256": file_hash(path),
                        "source_anchors": found[:12], "status": "SOURCE_ANCHORED_RUNTIME_NOT_TESTED" if found else "NEEDS_SOURCE_REVIEW"})
    record(out, "quantbt_binding_report.json", {
        "sys_executable": sys.executable, "quantbt_import_origin": str(origin), "init_sha256": file_hash(origin),
        "packages": packages, "wheel_hashes": wheel_rows, "registered_config": supplement["resolved_config"],
        "resolved_config": resolved, "config_matches_registration": resolved == supplement["resolved_config"],
        "public_signatures": {"QuantBTEndpoint.walk_forward": str(inspect.signature(quantbt.QuantBTEndpoint.walk_forward)),
                              "WalkForwardEngine": str(inspect.signature(WalkForwardEngine))},
        "research_retention_values": sorted(RESEARCH_RETENTION_LEVELS_V1), "vfy01_to_11": matches,
        "source_or_metadata_only": True, "engine_runs": 0,
        "limits": "Actual installed imports/config constructor and source anchors; not runtime parity, native execution or performance proof. A .so file hash does not mean that backend executed."})


def capture_fup(out):
    names = ("paired_discovery_fullwindow.json", "attempts.jsonl", "trial_ledger.jsonl",
             "cell_coverage.json", "coverage_review.json", "budget_revision.json", "report.md", "report.json")
    stable = False
    for _ in range(3):
        captured = {name: (FUP / name).read_bytes() for name in names if (FUP / name).exists()}
        stable = all((FUP / name).read_bytes() == value for name, value in captured.items())
        if stable:
            break
    for name, data in captured.items():
        write_bytes(out / "fup_capture" / name, data)
    full = strict(captured["paired_discovery_fullwindow.json"])
    all_terminal = full.get("status") == "COMPLETE_ALL_CELLS"
    record(out, "fup02_intake.json", {"status": "SNAPSHOT_CAPTURED_FINAL_HANDOFF_PENDING",
           "checkpoint_at_utc": full.get("last_checkpoint_at_utc"), "checkpoint_status": full.get("status"),
           "all_cells_terminal_label": all_terminal, "final_handoff_verified": False,
           "stable_during_read": stable,
           "files": [{"path": name, "sha256": digest(data), "bytes": len(data)} for name, data in captured.items()],
           "coverage": dict(Counter(row["coverage_status"] for row in full["cells"])),
           "interrupted_attempts": [row for row in full.get("invocations", []) if not row.get("ended_at_utc")],
           "limitation": "No external process is controlled. Stable bytes and terminal labels do not constitute a final OpenCode source/report handoff."})
    return full


def map_findings(out):
    mapping = read(CONFIG / "finding_map_r01.json")
    for row in mapping["findings"]:
        anchors = []
        for kind in ("source_refs", "caller_refs", "existing_tests"):
            for reference in row[kind]:
                filename, _, symbol = reference.partition("::")
                path = ROOT / filename
                data = path.read_bytes()
                lines = []
                if symbol:
                    lines = [n.lineno for n in ast.walk(ast.parse(data))
                             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == symbol]
                    if not lines:
                        raise ValueError(f"missing mapped symbol: {reference}")
                anchors.append({"kind": kind, "reference": reference, "sha256": digest(data),
                                "lines": lines, "scope": "mapped_not_runtime_requalified"})
        row["verified_source_anchors"] = anchors
        row["economic_retest_required"] = True
    if len(mapping["findings"]) != 49 or len({r["id"] for r in mapping["findings"]}) != 49:
        raise ValueError("finding inventory must contain all 49 unique IDs")
    record(out, "finding_disposition.json", {"findings": mapping["findings"],
           "counts": dict(Counter(r["status"] for r in mapping["findings"])),
           "rule": "All 20 new findings remain OPEN; original repairs are scoped evidence references, not assumed financial validity."})


def isolation_probe(out):
    bwrap = shutil.which("bwrap")
    if not bwrap:
        record(out, "os_isolation.json", {"available": False, "reason": "bwrap not installed", "engine_permitted": False})
        return
    scratch = ROOT / ".cache/te01" / out.name
    fixture = scratch / "fake_protected"
    fixture.mkdir(parents=True, exist_ok=True)
    # Only a LAB-OWNED disposable fixture is used for a denied-write witness.
    code = """import json,os,socket
from pathlib import Path
fake=Path(os.environ['TE01_FAKE']); result={}
try:
    (fake/'write_probe').write_text('fixture only'); result['fake_write_denied']=False
except OSError:
    result['fake_write_denied']=True
mounts=[]
for line in Path('/proc/self/mountinfo').read_text().splitlines():
    fields=line.split(); mounts.append((fields[4],fields[5].split(',')))
def readonly(path):
    candidates=[r for r in mounts if path==r[0] or path.startswith(r[0].rstrip('/')+'/')]
    return bool(candidates and 'ro' in max(candidates,key=lambda r:len(r[0]))[1])
roots=json.loads(os.environ['TE01_PROTECTED'])
result['protected_mounts_readonly']={p:readonly(p) for p in roots}
result['non_loopback_interfaces']=[name for _,name in socket.if_nameindex() if name!='lo']
result['unexpected_environment']=[k for k in os.environ if k not in ('TE01_FAKE','TE01_PROTECTED','PYTHONDONTWRITEBYTECODE','LC_CTYPE')]
print(json.dumps(result))
"""
    protected = [str(PROTECTED), str(ROOT.parent / "alphas_storage/_get_data"),
                 str(ROOT.parent / "alphas_storage/alpha_to_tes_regime_model")]
    argv = [bwrap, "--ro-bind", "/", "/", "--bind", str(ROOT), str(ROOT), "--ro-bind", str(fixture), str(fixture),
            "--proc", "/proc", "--dev", "/dev", "--unshare-net", "--unshare-pid", "--die-with-parent",
            "--clearenv", "--setenv", "PYTHONDONTWRITEBYTECODE", "1", "--setenv", "TE01_FAKE", str(fixture),
            "--setenv", "TE01_PROTECTED", json.dumps(protected), "--", sys.executable, "-B", "-c", code]
    result = subprocess.run(argv, capture_output=True, text=True, timeout=20)
    checks = strict(result.stdout) if result.returncode == 0 else {}
    available = (result.returncode == 0 and checks.get("fake_write_denied") is True
                 and len(checks.get("protected_mounts_readonly", {})) == len(protected)
                 and all(checks["protected_mounts_readonly"].values())
                 and not checks.get("non_loopback_interfaces") and not checks.get("unexpected_environment"))
    record(out, "os_isolation.json", {"available": available, "exit_code": result.returncode,
           "checks": checks, "stderr": result.stderr, "engine_permitted_by_isolation_alone": False,
           "limits": "No writes attempted against protected sources. Namespace availability alone does not qualify economic execution."})


def test_run(out, filename, prefix):
    env = os.environ.copy()
    cache = ROOT / ".cache/te01" / out.name
    cache.mkdir(parents=True, exist_ok=True)
    env.update(PYTHONDONTWRITEBYTECODE="1", OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1",
               NUMBA_CACHE_DIR=str(cache / "numba"), MPLCONFIGDIR=str(cache / "matplotlib"))
    xml = out / (prefix + ".xml")
    argv = [sys.executable, "-B", "-m", "pytest", filename, "-q", "--tb=short", "-p", "no:cacheprovider",
            "--junitxml", str(xml), "--basetemp", str(cache / (prefix + "-tmp"))]
    start = time.monotonic()
    result = subprocess.run(argv, cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    write_bytes(out / (prefix + ".log"), (result.stdout + result.stderr).encode())
    if not xml.exists():
        raise RuntimeError(f"test process produced no XML: {prefix}")
    tree = ET.parse(xml)
    cases = []
    for case in tree.iter("testcase"):
        bad, skipped, error = case.find("failure"), case.find("skipped"), case.find("error")
        message = bad.get("message", "") if bad is not None else error.get("message", "") if error is not None else ""
        cases.append({"name": case.get("name"), "seconds": float(case.get("time", "0")),
                      "status": "ERROR" if error is not None else "FAIL" if bad is not None else "SKIP" if skipped is not None else "PASS",
                      "message": message,
                      "assertion_mismatch": bad is not None and (message.startswith("assert ") or message.startswith("AssertionError"))})
    payload = {"command": argv, "exit_code": result.returncode, "elapsed_seconds": time.monotonic()-start,
               "cases": cases, "counts": dict(Counter(c["status"] for c in cases)), "engine_runs": 0,
               "scope": "explicit before-repair source baseline" if prefix == "regression_baseline" else "contract arithmetic, mutations, installed config constructor; no simulation"}
    record(out, prefix + ".json", payload)
    return payload


def reuse_and_invalidation(out, full):
    rows = []
    for cell in full["cells"]:
        rows.append({"cell": cell["cell"], "fup02_status": cell["coverage_status"],
                     "arms": {arm: {"planned": True, "new_study_result": "NOT_RUN",
                                    "reuse_status": "DIAGNOSTIC_ONLY_OR_NOT_RUN_SEE_ORIGINAL_CELL"}
                              for arm in ("M4_CAL", "M4_REGIME", "M4_CAL_MATCHED")},
                     "source_data": "REUSABLE_IF_HASH_VERIFIED", "saved_accounts": "DIAGNOSTIC_ONLY_PENDING_EXECUTION_REQUALIFICATION",
                     "selection_cache": "CONDITIONAL_ON_EXACT_CUTOFF_SCORER_WARMUP_ECONOMICS_IDENTITY",
                     "model_tape": "QUARANTINED_FOR_NEW_DESIGN_CLAIMS",
                     "new_primary_result": "NEEDS_AFFECTED_CHAIN_RERUN_AFTER_TE02_TE03",
                     "report_only_recompute": "ALLOWED_AS_DIAGNOSTIC_NOT_REPAIRED_TIME_EDGE_PROOF",
                     "metrics": None, "reason": "TE-01 does not evaluate market outcomes; original status retained."})
    if len(rows) != 20:
        raise ValueError("reuse table must cover all 20 planned cells")
    record(out, "reuse_decision.json", {"policy_ref": "configs/time_edge_validation_v4/r01/reuse_policy.json",
           "cells": rows, "rule": "Recompute only the affected dependency chain; no automatic full backtest or blind old cache reuse."})
    record(out, "invalidation.json", {
        "status": "NEW_STUDY_INTERPRETATION_OVERLAY_ONLY", "historical_files_modified": False,
        "preserved_historical_conclusion": "LAB-09 FAILED_VALIDITY; RF-05 INCONCLUSIVE retained as recorded",
        "affected_scope": "RF/FUP market timing/decay claims relying on the audited window, old tape, scorer or delivery path",
        "economic_status_for_v4_reuse": "NOT_EVALUABLE", "invalidated_by": [f"TEF-{n:02d}" for n in (1,5,6,8,10,11,12,13,14)],
        "superseded_by": "time_edge_validation_v4 after its own phase gates; not yet an economic result",
        "secondary": "E/NEIGH and historical A..E prohibited in this registration; historical CLI runtime quarantine remains a later repair",
        "does_not_invalidate": "raw market bytes, measured capability witnesses, or unit tests in their actual limited scope",
        "retest_required": "mapped findings + before/after actual execution evidence + affected outputs; negative outcomes retained"})


def acceptance_coverage(out):
    guide = ROOT / "QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md"
    rows = []
    partial = {"T04": "protected_source_verification.json: original alpha bytes; archive extraction not exercised",
               "T22": "contract_tests.json: UTC/day-label rejection; raw ms/ns conversion not exercised",
               "T39": "regression_baseline.json: target-profile mutation red; no whole model fit qualification",
               "T45": "contract_tests.json + regression_baseline.json: outcome availability oracle and red training profile",
               "T49": "regression_baseline.json: model-ready scheduler red; no actual engine delivery",
               "T52": "regression_baseline.json: initial max-age red; full clock counters not qualified",
               "T53": "contract_tests.json: registered fees/units/budget; no actual all-arm execution",
               "T54": "quantbt_binding_report.json: Mode 4 config/source only; runtime ledger deferred",
               "T55": "contract_tests.json: daily common-date arithmetic; actual dynamic accounts deferred",
               "T59": "contract_tests.json: failed-attempt budget; optimizer ledger delivery deferred",
               "T61": "contract_tests.json: nonfinite registration rejected; audit queue not exercised",
               "T64": "source_data_manifest.json: source identities; report verification follows commit; no engine replay"}
    for line in guide.read_text().splitlines():
        match = re.match(r"\| (T\d{2}) \| ([^|]+) \| ([^|]+) \|", line)
        if not match:
            continue
        key, question, expected = match.groups()
        status, reason = "NOT_EXERCISED_IN_TE01", "Requires the relevant TE-02/03/04/05 runtime or acceptance fixture; no inherited pass assumed"
        if key in partial:
            status, reason = "PARTIAL_CONTRACT_OR_RED_BASELINE", partial[key]
        elif key == "T08":
            proof = read(out / "protected_source_verification.json")
            status = "PASS_MEASURED_IDENTITY" if not proof["changed_paths"] and proof["original_alphas_match"] else "FAIL_IDENTITY"
            reason = "protected_source_verification.json: actual before/after hashes, denominator retained"
        elif key in ("T05", "T06"):
            isolation = read(out / "os_isolation.json")
            status = "PARTIAL_ISOLATION_FIXTURE" if isolation["available"] else "BLOCKED_ISOLATION_UNAVAILABLE"
            reason = "os_isolation.json: lab-owned write-denial/network/environment probe; no market worker"
        rows.append({"id": key, "question": question.strip(), "expected": expected.strip(),
                     "status": status, "evidence_or_reason": reason})
    if len(rows) != 64 or len({row["id"] for row in rows}) != 64:
        raise ValueError("acceptance inventory must retain all 64 IDs")
    record(out, "acceptance_coverage.json", {"cases": rows, "counts": dict(Counter(r["status"] for r in rows)),
           "limits": "Acceptance IDs are not pytest counts. Partial/source witnesses never count as full runtime acceptance."})


def audit(out):
    if out.exists():
        raise SystemExit("audit output must be a fresh generation")
    start, cpu = time.monotonic(), time.process_time()
    bundle = C.load_registration(REGISTER)
    registration = C.validate_registration(bundle)
    out.mkdir(parents=True)
    record(out, "registration_validation.json", {"validation": registration,
           "registration_manifest_sha256": file_hash(REGISTER / "registration_manifest.json"),
           "binding_supplement_sha256": file_hash(CONFIG / "mode4_binding_r01.json")})
    protected_before = protected_inventory()
    source = source_capture(out)
    snapshot_verify(out)
    binding_report(out)
    full = capture_fup(out)
    map_findings(out)
    isolation_probe(out)
    contracts = test_run(out, "tests/time_edge_validation_v4/test_registration_contracts.py", "contract_tests")
    baseline = test_run(out, "tests/time_edge_validation_v4/before_repair_cases.py", "regression_baseline")
    reuse_and_invalidation(out, full)
    changed = [row["path"] for row in source if file_hash(ROOT / row["path"]) != row["sha256"]]
    protected_changed = [row["path"] for row in protected_before if file_hash(row["path"]) != row["sha256"]]
    record(out, "protected_source_verification.json", {"before": protected_before,
           "changed_paths": protected_changed, "quantbt_git_status": git("status", "--porcelain", cwd=PROTECTED).decode(),
           "original_alphas_match": all(r.get("matches_registered_original", True) for r in protected_before),
           "production_writes_attempted": False})
    acceptance_coverage(out)
    expected = {r["test"] for r in bundle["case_registry.json"]["cases"]}
    baseline_ok = (len(baseline["cases"]) == len(expected)
                   and {r["name"] for r in baseline["cases"]} == expected
                   and all(r["status"] == "PASS" or (r["status"] == "FAIL" and r["assertion_mismatch"]) for r in baseline["cases"]))
    binding = read(out / "quantbt_binding_report.json")
    versions = {p["name"]: p["version"] for p in binding["packages"]}
    binding_ok = (binding["config_matches_registration"] and versions["quantbt-engine"] == "1.1.1"
                  and versions["quantbt-native"] == "0.4.2"
                  and all(v["source_anchors"] for v in binding["vfy01_to_11"]))
    verified = (contracts["exit_code"] == 0 and bool(contracts["cases"])
                and all(case["status"] == "PASS" for case in contracts["cases"]) and baseline_ok
                and not changed and not protected_changed
                and all(r.get("matches_registered_original", True) for r in protected_before)
                and read(out / "fup02_intake.json")["stable_during_read"]
                and read(out / "snapshot_verification.json")["all_manifest_entries_match"]
                and binding_ok)
    elapsed = time.monotonic() - start
    if elapsed > bundle["compute_budget.json"]["phase_te01"]["total_wall_seconds"]:
        verified = False
    record(out, "phase_verdict.json", {
        "created_at_utc": stamp(), "registration_status": registration["status"] if verified else "VALIDATION_FAILED",
        "phase_status": "PARTIAL_TECHNICAL_CLOSURE_FINAL_FUP_HANDOFF_PENDING" if verified else "FAILED_TE01_VALIDATION",
        "full_phase_complete": False, "technical_registration_validated": verified,
        "task_status": {
            "TE01.1": "PINNED_CHECKPOINT_FINAL_FUP_HANDOFF_PENDING",
            "TE01.2": "MAPPED_49_FINDINGS_RUNTIME_RETESTS_REMAIN_OPEN",
            "TE01.3": "CONTRACT_VALIDATED" if contracts["exit_code"] == 0 else "CONTRACT_FAILED",
            "TE01.4": "REGISTERED_COST_FORMULA_NUMERIC_FREEZE_REQUIRED_BEFORE_TE04",
            "TE01.5": "REGISTERED_NOT_FITTED_OR_DEPLOYED",
            "TE01.6": "TE01_BUDGET_MEASURED_FUTURE_ENGINE_BUDGET_NOT_ALLOCATED",
            "TE01.7": "REUSE_AND_INVALIDATION_OVERLAY_RECORDED"},
        "baseline_correct_behavior_failures": baseline["counts"].get("FAIL", 0),
        "baseline_unexpected_errors": [r for r in baseline["cases"] if r["status"] not in ("PASS", "FAIL") or (r["status"] == "FAIL" and not r["assertion_mismatch"])],
        "source_changed_during_audit": changed, "new_findings_closed": 0,
        "runtime_ready": False, "runtime_gate": {**{key: False for key in (
            "fup02_final_handoff", "source_identity_verified", "os_isolation_verified", "economic_engine_qualified",
            "model_and_controls_qualified", "economic_threshold_materialized", "total_budget_allocated", "no_affected_p0")},
            "os_isolation_verified": read(out / "os_isolation.json")["available"]},
        "remaining": ["Final FUP-02 handoff and pin executable source before changing its imports/configs.",
                      "Actual engine/clock/scorer and model/control qualification belongs to TE-02/03.",
                      "Materialize registered cost threshold from qualified training-only traces before TE-04.",
                      "No new market job until measured isolation and total resource allocation pass."],
        "runtime": {"wall_seconds": elapsed, "cpu_seconds": time.process_time()-cpu,
                    "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                    "engine_runs": 0, "optimizer_runs": 0, "market_statistical_tests": 0},
        "claim": {"proof_status": "TECHNICAL_ONLY", "economic_status": "NOT_EVALUABLE", "deployment": "NOT_ASSESSED"}})
    record(out, "artifact_manifest.json", {"artifacts": [
        {"path": p.relative_to(out).as_posix(), "sha256": file_hash(p), "bytes": p.stat().st_size}
        for p in sorted(out.rglob("*")) if p.is_file()]})
    print(json.dumps({"output": str(out.relative_to(ROOT)), "verified": verified,
                      "contract_counts": contracts["counts"], "baseline_counts": baseline["counts"],
                      "phase_complete": False, "wall_seconds": elapsed}, ensure_ascii=False))
    return 0 if verified else 1


def report(out):
    manifest = read(out / "artifact_manifest.json")
    # Every source for report numbers must be committed and unchanged.
    for entry in manifest["artifacts"]:
        path = out / entry["path"]
        if file_hash(path) != entry["sha256"]:
            raise ValueError(f"evidence hash mismatch: {path}")
    inputs = {name: read(out / name) for name in (
        "phase_verdict.json", "registration_validation.json", "contract_tests.json", "regression_baseline.json",
        "source_data_manifest.json", "snapshot_verification.json", "quantbt_binding_report.json",
        "fup02_intake.json", "finding_disposition.json", "os_isolation.json", "reuse_decision.json",
        "protected_source_verification.json", "invalidation.json")}
    inputs["acceptance_coverage.json"] = read(out / "acceptance_coverage.json")
    for name in inputs:
        if git("show", "HEAD:" + (out / name).relative_to(ROOT).as_posix()) != (out / name).read_bytes():
            raise ValueError("report input not committed unchanged")
    v, ct, br = (inputs[n] for n in ("phase_verdict.json", "contract_tests.json", "regression_baseline.json"))
    snap, bind, fup = (inputs[n] for n in ("snapshot_verification.json", "quantbt_binding_report.json", "fup02_intake.json"))
    r = ["# TE-01 — Registration, nguồn sự thật và phạm vi tái sử dụng", "",
         f"Run `{out.name}`; thời điểm {v['created_at_utc']}. **{v['phase_status']}**.", "",
         "Đã kiểm chứng registration (bộ quy tắc được đăng ký trước phép thử) cho sửa chữa kỹ thuật. "
         "Chưa đóng toàn TE-01 vì chưa có bàn giao cuối FUP-02; chưa chạy mô phỏng hoặc kiểm định lợi thế thị trường.", "",
         "## 1. Phạm vi và chỉ mục", "",
         "Theo [central plan TE01.1–TE01.7](../../../../implementation%20and%20test_edge_plan.md#te-01); "
         "[G3 RF-01.1–RF-01.5, §4/6/7/8/10](../../../../REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md); "
         "[G2 §0/2/6/11/13](../../../../QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md). "
         "QuantBT gốc và alpha gốc chỉ đọc. Runner dùng venv lab, không import historical loader. "
         "Những ca trước sửa được giữ là FAIL thật; không đổi thành PASS hay xfail.", "",
         "## 2. Số đo và phép thử thực tế", "", "| Nội dung | Đo được |", "|---|---:|",
         f"| Contract tests PASS / FAIL / SKIP | {ct['counts'].get('PASS',0)} / {ct['counts'].get('FAIL',0)} / {ct['counts'].get('SKIP',0)} |",
         f"| Before-repair PASS / FAIL / unexpected errors | {br['counts'].get('PASS',0)} / {br['counts'].get('FAIL',0)} / {len(v['baseline_unexpected_errors'])} |",
         f"| Snapshot files / bytes đã đối chiếu hash và metadata | {snap['files_verified']} / {snap['bytes_verified']} |",
         f"| Nguồn/config đã giữ nguyên bytes | {len(inputs['source_data_manifest.json']['files'])} |",
         f"| Findings đã map / TEF được đóng | {len(inputs['finding_disposition.json']['findings'])} / {v['new_findings_closed']} |",
         f"| Wall / CPU giây | {v['runtime']['wall_seconds']:.3f} / {v['runtime']['cpu_seconds']:.3f} |",
         f"| Process peak RSS KiB | {v['runtime']['peak_rss_kib']} |",
         f"| Engine / optimizer / market statistical tests | {v['runtime']['engine_runs']} / {v['runtime']['optimizer_runs']} / {v['runtime']['market_statistical_tests']} |", "",
         "Hash verification (đối chiếu bytes) và metadata không chứng minh toàn bộ candle rows đúng hoặc point-in-time availability đúng; "
         "đây là danh tính dữ liệu, không là kết quả tài chính. CPU/RSS là process audit; subprocess tests có wall/exit/XML riêng.", "",
         "## 3. Baseline trước sửa", "", "| Ca yêu cầu hành vi đúng | Kết quả | Sai khác |", "|---|---|---|"]
    for case in br["cases"]:
        r.append(f"| {case['name']} | {case['status']} | {case['message'].replace('|','/').replace(chr(10),' ')[:500]} |")
    r += ["", "Log đầy đủ: [baseline log](regression_baseline.log), [baseline JSON](regression_baseline.json), "
          "[contract tests](contract_tests.json). Source probes (thử hàm nguồn cô lập) không phải full engine controls; "
          "ca target purge dùng centroid stub để cô lập logic profile, không nhận là kiểm chất lượng learned model.", "",
          f"Acceptance T01–T64: `{json.dumps(inputs['acceptance_coverage.json']['counts'])}`. "
          "[Bảng đủ 64 yêu cầu](acceptance_coverage.json) ghi ca chưa chạy và lý do; số pytest PASS không đồng nghĩa 64 yêu cầu đã đạt.", "",
          "## 4. Quyết định toán học và thiết kế", "",
          "Daily return giữ phí đầu account và previous mark, sau đó lọc [start,end); các age windows không chồng ngày biên. "
          "Sharpe dùng daily UTC, sqrt(365), sample standard deviation ddof=1. PF theo return observations khác PF theo trade; "
          "chỉ lỗ cho PF=0, không lỗ cho null kèm reason; không thêm epsilon.", "",
          "Đăng ký bốn hypotheses: H-TIMING, H-BUDGET, H-DECAY, H-MODEL-INFO. Holm dùng cả family 4; "
          "common calendar blocks giữ dependence giữa arms/cells. CI đồng thời Bonferroni tách khỏi CI 95% mô tả. "
          "Block length, seeds, support, false-positive/power calibration và stopping đã ghi trước; TE-01 chưa chạy inference này.", "",
          "δ kinh tế được đăng ký bằng công thức cost/account-turnover trên M4_CAL training-only đã qualify. "
          "Số δ phải materialize và freeze với trace hashes trước TE-04; chưa có số đó thì cấm claim kinh tế. "
          "Không kế thừa âm thầm MDE cũ khi execution/sizing đổi. MDE thống kê (effect có thể phát hiện ở power/alpha đã định) là đại lượng khác.", "",
          "D1 so cùng selected θ IS/OOS và ghi selection bias; D2 cùng θ qua H1/H2/H3, so cohort calendar/context có support; "
          "D3 là observed operational fold change. Không ghép ordinal fold #3 hai arms; D2 chưa loại được market-context confounding thì chỉ là association diagnostic.", "",
          "## 5. Model regime được dùng và đánh giá", "",
          "**INHERITED_FROZEN_INPUT, NOT_REEVALUATED_IN_TE01.** Model cũ chỉ là input đã pin; không fit thêm model để lấp báo cáo. "
          "Protocol mới đăng ký common BTC context, raw features G1/G2/G5, M0 + JM K2/K3 với lambda 0.5/1/2, inner-train scaler và purge theo outcome availability. "
          "Regime ID là ký hiệu trong namespace model, không mặc định bull/bear; mô tả nhãn chỉ từ train. "
          "TE-03 phải nối actual selected design → emitted tape → controller và báo model theo từng fold.", "",
          "Information target là future paired candidate utility từ cùng QuantBT/economics, không phải future return trừ trailing return. "
          "Full positive/null controls phải qua learned model và installed Mode 4; power chưa được chứng minh trong TE-01.", "",
          "## 6. QuantBT và chiến lược", "",
          f"Actual import: `{bind['quantbt_import_origin']}`. Installed config matches registered knobs: `{bind['config_matches_registration']}`. "
          "Bốn alpha giữ thesis, 10% current-equity allocation và initial capital đã đăng ký; protective/partial behavior không chuyển thành target-only để chạy nhanh. "
          "Primary execution 1m; coarse next-close cần cohort khác có tên và qualification, không tự coi factory name là actual clock.", "",
          "[Binding report](quantbt_binding_report.json) giữ public signatures, resolved knobs, wheels/.so hashes và VFY01–VFY11 source anchors. "
          "Đây là import/config/source qualification, chưa là public-path runtime parity hoặc Rust speedup.", "",
          "## 7. FUP-02, reuse và invalidation", "",
          f"FUP snapshot `{fup['checkpoint_status']}` tại `{fup['checkpoint_at_utc']}`; `{json.dumps(fup['coverage'])}`. "
          "Bàn giao cuối vẫn pending; không dừng/resume/sửa FUP thay OpenCode.", "",
          "| Cell | FUP status | Raw data | Account dùng cho claim mới |", "|---|---|---|---|"]
    for cell in inputs["reuse_decision.json"]["cells"]:
        r.append(f"| {cell['cell']} | {cell['fup02_status']} | hash-verified reuse | diagnostic only; affected chain retest |")
    r += ["", "[Reuse decision](reuse_decision.json) tách report recompute khỏi scorer/model/execution rerun. "
          "[Invalidation overlay](invalidation.json) chặn tái sử dụng financial claims bị ảnh hưởng; giữ nguyên raw curves và kết luận lịch sử. "
          "Không đưa pending/failed vào aggregate bằng số 0. [Finding disposition](finding_disposition.json) giữ đủ 49 IDs và source/caller/test references.", "",
          "## 8. Readiness và giới hạn còn lại", "",
          f"OS worker isolation measured available: `{inputs['os_isolation.json']['available']}`; "
          "[probe evidence](os_isolation.json). Việc đọc và kiểm hợp đồng được thực hiện trong sandbox hiện tại; "
          "không suy nó thành quyền chạy market workers thiếu containment theo lab policy.", ""]
    r.extend(f"- {item}" for item in v["remaining"])
    r += ["", "**Verdict:** TECHNICAL_ONLY; economic NOT_EVALUABLE; runtime gate CLOSED. "
          "Không có time-edge estimate mới. Các FAIL trước sửa là backlog đã tái hiện, không phải bằng chứng regime không có edge.", "",
          "## 9. Tái tạo và bằng chứng", "", "```bash",
          "PYTHONDONTWRITEBYTECODE=1 environments/lab_venv/bin/python -B scripts/run_te01.py audit --run-id FRESH_RUN_ID",
          f"PYTHONDONTWRITEBYTECODE=1 environments/lab_venv/bin/python -B scripts/run_te01.py report --run-id {out.name}",
          f"PYTHONDONTWRITEBYTECODE=1 environments/lab_venv/bin/python -B scripts/run_te01.py runtime-gate --run-id {out.name}",
          "```", "",
          "Commit audit inputs trước render. Runtime-gate phải trả lỗi ở trạng thái này; audit không chạy engine. "
          "[Artifact manifest](artifact_manifest.json), [phase JSON](phase_verdict.json), "
          "[protected-source verification](protected_source_verification.json), [snapshot verification](snapshot_verification.json).", "",
          "## 10. Thuật ngữ", "",
          "**Registration:** quy tắc/hypotheses đăng ký trước phép thử. **Gate:** điều kiện chặn bước sau khi chưa đủ evidence. "
          "**WFO/Mode 4:** tối ưu cuốn chiếu bằng bộ chọn robust IS của QuantBT. **IS/OOS:** khoảng dùng chọn tham số/khoảng đánh giá về sau. "
          "**θ:** bộ tham số cố định; **fold:** khoảng operational hoặc training đã định. "
          "**Regime/JM:** trạng thái model thị trường/jump model có penalty chuyển trạng thái. "
          "**Namespace:** danh tính nhãn riêng mỗi model vintage. **D1/D2/D3:** IS→OOS gap/age degradation/operational fold change. "
          "**PF:** tỷ lệ phần lãi trên độ lớn phần lỗ, luôn kèm sampling. **Sharpe:** mean return chia sample deviation, annualize đúng clock. "
          "**CI:** khoảng tin cậy; **δ:** ngưỡng cải thiện kinh tế; **Holm/Bonferroni:** điều chỉnh kiểm nhiều giả thuyết. "
          "**Power/false positive:** xác suất phát hiện hiệu ứng/xác suất báo có hiệu ứng khi null đúng. "
          "**Support:** lượng quan sát, recurrence và hành vi đủ để đánh giá; không chỉ đếm bars. "
          "**Bootstrap block:** lấy mẫu lại theo khối thời gian để giữ dependence. **Warmup:** lịch sử khởi tạo indicator, ngoài scoring. "
          "**Purge:** loại training targets chưa available trước cutoff. **Cutoff:** biên thông tin được phép dùng. "
          "**Hash/manifest:** mã băm bytes và danh mục nguồn. **Snapshot/checkpoint:** bản chụp dữ liệu/trạng thái tại thời điểm. "
          "**Runtime parity:** thực thi cùng contract cho trace tài chính khớp; metadata không thay thế được. "
          "**RSS/CPU/wall:** bộ nhớ cư trú/thời gian CPU/thời gian trôi qua. **Replay/retrospective:** mô phỏng tuần tự/đánh giá lịch sử đã được xem. "
          "**Thesis:** logic chiến lược gốc; **exposure:** mức vị thế thực; **turnover:** notional giao dịch chuẩn hóa vốn. "
          "**Native/.so:** backend biên dịch/thư viện nhị phân; có file không đồng nghĩa đã chạy backend đó.", ""]
    r += ["## 11. Từng task và hợp đồng có thể đọc trực tiếp", "", "| Task | Trạng thái / giới hạn |", "|---|---|"]
    r.extend(f"| {key} | {value} |" for key, value in v["task_status"].items())
    r += ["", "Các guide references của từng task nằm tại TE-01 trong central plan; "
          "bộ [registration manifest](../../../../configs/time_edge_validation_v4/r01/registration_manifest.json) khóa hash các hợp đồng dưới đây.", ""]
    for filename in sorted(C.load_registration(REGISTER)):
        r.append(f"- [{filename}](../../../../configs/time_edge_validation_v4/r01/{filename})")
    r += ["", "Corrections TE-01: thêm bộ hợp đồng chuẩn và overlay phạm vi sử dụng; chưa sửa caller RF/FUP. "
          "[Correction ledger](../../../../configs/correction_ledger.json) giữ lịch sử và chỉ mục TE-01. "
          "Không có kết quả thị trường bị ghi đè. Ngân sách audit không cho phép engine run.", ""]
    write_bytes(out / "report.md", "\n".join(r).encode())
    record(out, "report.json", {"verdict": v, "inputs": {name: file_hash(out / name) for name in inputs},
           "report_md_sha256": file_hash(out / "report.md"), "source_of_numbers": "committed audit artifacts only"})
    print(f"Rendered {out.relative_to(ROOT)}/report.md + report.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("audit", "report", "runtime-gate"))
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", args.run_id):
        raise SystemExit("run ID must be a single directory name")
    out = (BASE / args.run_id).resolve()
    if not out.is_relative_to(ROOT) or out.parent != BASE.resolve():
        raise SystemExit("evidence destination outside the lab TE-01 root")
    if args.operation == "audit":
        return audit(out)
    if args.operation == "report":
        report(out)
        return 0
    try:
        C.require_runtime_ready(read(out / "phase_verdict.json")["runtime_gate"], evidence_root=BASE)
    except C.ContractError as exc:
        print(str(exc))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
