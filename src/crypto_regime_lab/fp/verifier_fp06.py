"""FP-06 gate FP06-G-* thin verifier (guide section 9 / 18 exit gate).

Same discipline as verifier_fp01..05: every gate re-derives its verdict
from the raw artifacts on disk. FP06-G-ABLATION independently recomputes
C-B from the raw per-candidate predictions on both sides rather than
trusting a stored mean_diff; FP06-G-SUPPORT recomputes the fallback count
from the raw scored candidates' own source field; FP06-G-CLAIM greps the
report text for a forbidden 'JM-specific' claim whenever JM exposure is
recorded at zero. Never raises: returns the gate matrix with reasons.
"""
from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

REQUIRED_GATES = ("FP06-G-ABLATION", "FP06-G-CAUSAL", "FP06-G-SUPPORT",
                  "FP06-G-FREEZE", "FP06-G-CLAIM")

REQUIRED_ARTIFACTS = (
    "context_policy.json", "oof_diagnostics_c.json", "candidate_scores_c.json",
    "ablation.json", "exposure.json", "resource_budget.json", "test_registry.json",
    "phase_manifest.json", "gate_receipt.json", "report.md", "handoff.md",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _gate(ok: bool, reasons: list) -> dict:
    return {"pass": bool(ok), "reasons": list(reasons)}


def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def verify_fp06(run_dir, *, pytest_xml=None) -> dict:
    root = Path(run_dir)
    gates: dict = {}

    docs: dict = {}
    missing = [name for name in REQUIRED_ARTIFACTS if not (root / name).is_file()]
    for name in REQUIRED_ARTIFACTS:
        if name.endswith(".json") and (root / name).is_file():
            docs[name] = _load_json(root / name)

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

    context_policy = docs.get("context_policy.json")
    ablation = docs.get("ablation.json")
    exposure = docs.get("exposure.json")
    scores_c = docs.get("candidate_scores_c.json")

    # -- FP06-G-ABLATION: C-B is a context difference in the correct scope --
    reasons = list(manifest_reasons)
    if ablation is None:
        reasons.append("ablation.json missing or unreadable")
    else:
        b_preds = ablation.get("b_predictions")
        c_preds = ablation.get("c_predictions")
        diffs = ablation.get("diffs")
        if not b_preds or not c_preds:
            reasons.append("ablation.json missing b_predictions/c_predictions")
        else:
            shared = sorted(set(b_preds) & set(c_preds))
            if not shared:
                reasons.append("no shared candidate ids between B and C predictions -- not a "
                               "same-scope comparison")
            for rid in shared:
                expected = c_preds[rid] - b_preds[rid]
                if diffs is None or rid not in diffs or abs(diffs[rid] - expected) > 1e-9:
                    reasons.append(f"{rid}: stored diff does not equal c_predictions - "
                                   "b_predictions recomputed from the raw stored values")
            if set(diffs or {}) - set(shared):
                reasons.append("ablation.json's diffs include a record_id not shared by both "
                               "B and C -- guide FP06-T06 requires the same candidate pool")
    gates["FP06-G-ABLATION"] = _gate(not reasons, reasons)

    # -- FP06-G-CAUSAL: the temporal/context tests (guide FP06-T01/T02/T03) --
    reasons = list(manifest_reasons)
    required_causal_tests = (
        "test_fp06_t01_walk_forward_oof_with_the_default_builder_is_exactly_selector_b",
        "test_fp06_t02_relabeling_a_context_key_does_not_change_the_computed_interaction_value",
        "test_compute_context_features_never_reads_bars_after_the_frame_end",
    )
    registry = docs.get("test_registry.json") or {}
    registered = set(registry.get("test_node_ids", []))
    for wanted in required_causal_tests:
        if wanted not in registered:
            reasons.append(f"required causal test not in test_registry.json: {wanted}")
    if reg_tests and (reg_tests.get("failures") or reg_tests.get("errors")):
        reasons.append("pytest report shows failures/errors")
    gates["FP06-G-CAUSAL"] = _gate(not reasons, reasons)

    # -- FP06-G-SUPPORT: fallback/unknown policy has ACTUAL evidence,
    # recomputed from the raw scored candidates, never trusted --
    reasons = list(manifest_reasons)
    if scores_c is None or exposure is None:
        reasons.append("candidate_scores_c.json or exposure.json missing or unreadable")
    else:
        rows = scores_c.get("scored", [])
        recomputed_fallback = sum(1 for r in rows if r.get("source") == "FALLBACK_TO_B")
        recomputed_context = sum(1 for r in rows if r.get("source") == "CONTEXT_CONDITIONED")
        if exposure.get("fallback_to_b_count") != recomputed_fallback:
            reasons.append(f"exposure.fallback_to_b_count {exposure.get('fallback_to_b_count')} "
                           f"disagrees with a fresh recount ({recomputed_fallback})")
        if exposure.get("context_conditioned_count") != recomputed_context:
            reasons.append(
                f"exposure.context_conditioned_count {exposure.get('context_conditioned_count')} "
                f"disagrees with a fresh recount ({recomputed_context})")
        if recomputed_fallback + recomputed_context != len(rows):
            reasons.append("fallback_to_b_count + context_conditioned_count does not cover "
                           "every scored candidate")
        for field in ("jm_observations", "m0_observations", "unknown_stale_ambiguous"):
            if field not in exposure:
                reasons.append(f"exposure.json missing required field {field} (guide 9.4)")
    gates["FP06-G-SUPPORT"] = _gate(not reasons, reasons)

    # -- FP06-G-FREEZE: exactly one context-policy revision --
    reasons = list(manifest_reasons)
    if context_policy is None:
        reasons.append("context_policy.json missing or unreadable")
    else:
        for field in ("context_feature_names", "interaction_specs", "frozen_at_utc"):
            if not context_policy.get(field):
                reasons.append(f"context_policy.json missing frozen field {field}")
    gates["FP06-G-FREEZE"] = _gate(not reasons, reasons)

    # -- FP06-G-CLAIM: never call a generic context result JM-specific
    # unless JM was actually exercised and separated --
    reasons = list(manifest_reasons)
    report_text = (root / "report.md").read_text(encoding="utf-8") if (root / "report.md").is_file() else ""
    if exposure is not None and exposure.get("jm_observations", 0) == 0:
        forbidden = "jm-specific"
        if forbidden in report_text.lower():
            reasons.append("report.md uses a 'JM-specific' claim while exposure.json records "
                           "zero JM observations -- guide 9.5/FP06-G-CLAIM forbids this")
    if "## Permitted conclusions" not in report_text:
        reasons.append("report.md has no '## Permitted conclusions' section")
    gates["FP06-G-CLAIM"] = _gate(not reasons, reasons)

    if missing:
        for gate in gates:
            if gates[gate]["pass"]:
                gates[gate] = _gate(False, gates[gate]["reasons"] +
                                    [f"missing artifacts: {', '.join(missing)}"])
    overall = all(g["pass"] for g in gates.values()) and all(g in gates for g in REQUIRED_GATES)
    return {
        "schema": "regime_lab.fp06_verification.v1",
        "run_dir": str(root),
        "gates": gates,
        "missing_artifacts": missing,
        "pytest": reg_tests,
        "overall": "PASS" if overall else "FAIL",
    }


def _check_tests(pytest_xml, registry, reasons: list):
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
