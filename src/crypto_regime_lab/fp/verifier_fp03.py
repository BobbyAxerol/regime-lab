"""FP-03 gate FP03-G-* thin verifier (guide section 15 exit gate + section 26.3).

Behavioral by construction, same discipline as verifier_fp01/fp02: every
gate re-derives its verdict from the artifacts on disk, including
re-slicing the RAW per-origin trial records to independently prove
FP03-G-PREFIX (a lower checkpoint is a true prefix of a higher one) rather
than trusting the checkpoint summary's own bookkeeping. Never raises:
returns the gate matrix with reasons.
"""
from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

REQUIRED_GATES = ("FP03-G-SCHEMA", "FP03-G-PREFIX", "FP03-G-COVERAGE",
                  "FP03-G-CURVE", "FP03-G-FREEZE")

REQUIRED_ARTIFACTS = (
    "schema_qualification.json", "search_introspection.json", "origin_searches.json",
    "forward_comparison.json", "search_policy.json", "resource_budget.json",
    "test_registry.json", "phase_manifest.json", "gate_receipt.json",
    "report.md", "handoff.md",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _gate(ok: bool, reasons: list) -> dict:
    return {"pass": bool(ok), "reasons": list(reasons)}


def _load_json(path: Path, errors: list) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        errors.append(f"unreadable artifact {path.name}: {exc}")
        return None


def verify_fp03(run_dir, *, pytest_xml=None) -> dict:
    root = Path(run_dir)
    gates: dict = {}

    docs: dict = {}
    missing = [name for name in REQUIRED_ARTIFACTS if not (root / name).is_file()]
    for name in REQUIRED_ARTIFACTS:
        if name.endswith(".json") and (root / name).is_file():
            docs[name] = _load_json(root / name, [])

    reasons: list = []
    manifest = docs.get("phase_manifest.json")
    if manifest is None:
        reasons.append("phase_manifest.json missing or unreadable")
    else:
        for entry in manifest.get("artifacts", []):
            name = entry.get("path")
            if not name or name in ("phase_manifest.json", "gate_receipt.json"):
                continue
            target = root / name
            if not target.is_file():
                reasons.append(f"manifest lists {name} but it is not on disk")
                continue
            if entry.get("sha256") and entry["sha256"] != _sha256(target):
                reasons.append(f"manifest hash mismatch on {name}: bytes changed after writing")
    reg_tests = _check_tests(pytest_xml, docs.get("test_registry.json"), reasons)
    manifest_reasons = list(reasons)

    # -- FP03-G-SCHEMA --
    reasons = list(manifest_reasons)
    sq = docs.get("schema_qualification.json")
    if sq is None:
        reasons.append("schema_qualification.json missing or unreadable")
    else:
        mapping = sq.get("schema_mapping", [])
        if not mapping or not all(r.get("engine_mapping_consistent") for r in mapping):
            reasons.append("schema mapping is not fully consistent with the engine ranges")
        rejections = sq.get("unknown_value_rejections", [])
        if not rejections or not all(r.get("correctly_rejected") for r in rejections):
            reasons.append("not every out-of-schema probe was correctly rejected")
        fixed = sq.get("fixed_dimensions", [])
        if not fixed or not all(r.get("matches_declared") and r.get("engine_value_is_scalar")
                                for r in fixed):
            reasons.append("a fixed dimension does not match its declared value or is not scalar")
        fixtures = sq.get("behavioral_fixtures", [])
        if not fixtures:
            reasons.append("no behavioral-effect fixtures recorded")
        differs = [f for f in fixtures if f.get("outcome") == "BEHAVIOR_DIFFERS"]
        if not differs:
            reasons.append("no dimension showed BEHAVIOR_DIFFERS on any real fixture "
                           "(guide: do not conclude a parameter is inert from insufficient "
                           "evidence, but zero confirmed differences is itself unqualified)")
    gates["FP03-G-SCHEMA"] = _gate(not reasons, reasons)

    # -- FP03-G-PREFIX: re-slice RAW trial records and re-derive each
    # checkpoint's own claims from that slice, don't trust the checkpoint
    # summary. (An earlier version of this gate compared records[:lo] to
    # records[:hi][:lo] from the SAME single sorted list -- mathematically
    # identical by construction, so it could never fail. Found by writing
    # the test that was supposed to prove a broken prefix gets caught, and
    # could not: a vacuous check, the exact defect class this lab's own
    # history keeps finding in itself. Fixed to re-derive 'selected' and
    # 'n_attempted' independently instead of comparing a slice to itself.)
    reasons = list(manifest_reasons)
    origins = docs.get("origin_searches.json")
    if origins is None:
        reasons.append("origin_searches.json missing or unreadable")
    else:
        checked_any_checkpoint = False
        for origin in origins.get("origins", []):
            records = sorted(origin.get("trial_records", []), key=lambda r: r["trial_id"])
            for cp in origin.get("checkpoints", []):
                if cp.get("status") != "REACHED":
                    continue
                level = cp["level"]
                prefix = records[:level]
                checked_any_checkpoint = True
                if cp.get("coverage", {}).get("n_attempted") != len(prefix):
                    reasons.append(f"{origin.get('origin_cutoff')} checkpoint {level}: "
                                   f"coverage.n_attempted={cp.get('coverage', {}).get('n_attempted')} "
                                   f"disagrees with the raw prefix length {len(prefix)}")
                    continue
                completed = [r for r in prefix if not r.get("pruned")
                            and r.get("objective") is not None]
                if not completed:
                    continue
                best = max(completed, key=lambda r: r["objective"])
                selected = cp.get("selected") or {}
                if selected.get("trial_id") != best["trial_id"]:
                    reasons.append(
                        f"{origin.get('origin_cutoff')} checkpoint {level}: selected trial "
                        f"{selected.get('trial_id')} is not the best-objective trial within "
                        f"the first {level} raw records ({best['trial_id']}) -- this checkpoint "
                        "may be using information beyond its own budget")
                if selected.get("trial_id", -1) >= level:
                    reasons.append(
                        f"{origin.get('origin_cutoff')} checkpoint {level}: selected trial_id "
                        f"{selected.get('trial_id')} is outside this checkpoint's own budget "
                        f"(>= {level}) -- higher-budget information leaked into a lower checkpoint")
        if not checked_any_checkpoint:
            reasons.append("no REACHED checkpoint to independently re-derive and check")
    gates["FP03-G-PREFIX"] = _gate(not reasons, reasons)

    # -- FP03-G-COVERAGE --
    reasons = list(manifest_reasons)
    if origins is None:
        reasons.append("origin_searches.json missing or unreadable")
    else:
        checked_any = False
        for origin in origins.get("origins", []):
            for cp in origin.get("checkpoints", []):
                if cp.get("status") != "REACHED":
                    continue
                checked_any = True
                cov = cp.get("coverage") or {}
                raw = cov.get("raw_coverage_fraction")
                uniq = cov.get("unique_coverage_fraction")
                if raw is None or not (0.0 < raw <= 1.0):
                    reasons.append(f"{origin.get('origin_cutoff')} cp{cp['level']}: raw "
                                   f"coverage fraction {raw!r} not in (0,1]")
                if uniq is None or uniq > (raw or 1.0) + 1e-9:
                    reasons.append(f"{origin.get('origin_cutoff')} cp{cp['level']}: unique "
                                   "coverage exceeds raw coverage")
        if not checked_any:
            reasons.append("no reached checkpoint with a coverage measure to check")
    gates["FP03-G-COVERAGE"] = _gate(not reasons, reasons)

    # -- FP03-G-CURVE: at least one origin's search is REAL engine output,
    # reaching at least the first checkpoint level --
    reasons = list(manifest_reasons)
    if origins is None:
        reasons.append("origin_searches.json missing or unreadable")
    else:
        real_ok = [o for o in origins.get("origins", []) if o.get("wf_ok") is True
                  and len(o.get("trial_records", [])) >= 32]
        if not real_ok:
            reasons.append("no origin has a real (wf_ok=True), >=32-trial search recorded")
    gates["FP03-G-CURVE"] = _gate(not reasons, reasons)

    # -- FP03-G-FREEZE --
    reasons = list(manifest_reasons)
    policy = docs.get("search_policy.json")
    if policy is None:
        reasons.append("search_policy.json missing or unreadable")
    else:
        for key in ("B_search", "Q_probe", "representative_subset_size",
                    "startup_exploration_policy", "pruning_policy", "seed_policy"):
            if policy.get(key) in (None, ""):
                reasons.append(f"search_policy.json missing frozen field: {key}")
        if not policy.get("frozen_at_utc"):
            reasons.append("search_policy.json has no freeze timestamp")
    gates["FP03-G-FREEZE"] = _gate(not reasons, reasons)

    if missing:
        for gate in gates:
            if gates[gate]["pass"]:
                gates[gate] = _gate(False, gates[gate]["reasons"] +
                                    [f"missing artifacts: {', '.join(missing)}"])
    overall = all(g["pass"] for g in gates.values()) and all(g in gates for g in REQUIRED_GATES)
    return {
        "schema": "regime_lab.fp03_verification.v1",
        "run_dir": str(root),
        "gates": gates,
        "missing_artifacts": missing,
        "pytest": reg_tests,
        "overall": "PASS" if overall else "FAIL",
    }


def _check_tests(pytest_xml, registry: dict | None, reasons: list) -> dict | None:
    if pytest_xml is None or not Path(pytest_xml).is_file():
        reasons.append("pytest report missing: no test evidence, cannot PASS")
        return None
    try:
        suite = ET.parse(str(pytest_xml)).getroot()
        suites = suite.findall("testsuite") or [suite]
        tests = sum(int(s.get("tests", 0)) for s in suites)
        failures = sum(int(s.get("failures", 0)) for s in suites)
        errors = sum(int(s.get("errors", 0)) for s in suites)
        skipped = sum(int(s.get("skipped", 0)) for s in suites)
        node_ids = {
            f"{c.get('classname', '')}::{c.get('name', '')}"
            for s in suites for c in s.findall("testcase")
        }
    except ET.ParseError as exc:
        reasons.append(f"pytest report unparseable: {exc}")
        return None
    info = {"tests": tests, "failures": failures, "errors": errors, "skipped": skipped}
    if tests == 0:
        reasons.append("no-tests-collected cannot PASS")
    if failures or errors:
        reasons.append(f"test failures={failures} errors={errors} cannot PASS")
    if skipped:
        reasons.append(f"{skipped} skipped tests cannot PASS (no mandatory skip)")
    if registry:
        for wanted in registry.get("test_node_ids", []):
            if not any(wanted in got for got in node_ids):
                reasons.append(f"registered test not found in report: {wanted}")
                break
    return info
