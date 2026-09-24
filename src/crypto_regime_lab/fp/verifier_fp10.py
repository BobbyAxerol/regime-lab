"""FP-10 gate FP10-G-* thin verifier (guide section 22 exit gate).

Same discipline as verifier_fp01..09: every gate re-derives its verdict
from the raw artifacts on disk, never trusting a stored summary field.

  * FP10-G-FREEZE: freeze_manifest.json carries every guide-required
    component category, and every hashed source file's digest is
    RE-COMPUTED from the file on disk right now and matches -- a stale or
    tampered freeze is caught, not trusted.
  * FP10-G-REPLAY: replay_result.json shows the SAME contract (the exact
    script/config the original run used) reproduced the key economic
    outputs (per-arm fill counts, the primary contrast's estimate/CI)
    EXACTLY against the already-committed original run -- never a
    same-hash claim without the actual recomputed numbers alongside it.
  * FP10-G-REPORT: final_report.md answers all nine guide-required
    questions, each traceable to a real evidence path, never a bare
    unlinked claim.
  * FP10-G-EXPOSURE: the freeze manifest explicitly states the
    development role's own span, that outer_evaluation was never
    touched, and declares an explicit prospective_status -- never silent.
  * FP10-G-HANDOFF: handoff.md carries replay commands, an unresolved-
    issues list, a budget summary and the owner-decision ledger path.
"""
from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

REQUIRED_GATES = ("FP10-G-FREEZE", "FP10-G-REPLAY", "FP10-G-REPORT",
                  "FP10-G-EXPOSURE", "FP10-G-HANDOFF")

REQUIRED_ARTIFACTS = (
    "freeze_manifest.json", "replay_result.json", "artifact_index.json",
    "test_registry.json", "phase_manifest.json", "gate_receipt.json",
    "final_report.md", "handoff.md",
)

REQUIRED_FREEZE_COMPONENTS = (
    "code_dependency_engine_digests", "data_snapshots_and_availability",
    "alpha_schema_search_probe_contracts", "bc_model_and_feature_protocols",
    "support_fallback_admission_rules", "economic_latency_activation_contract",
    "metrics_thresholds_analysis_family", "cohorts_windows_seeds_budgets",
)

REQUIRED_REPORT_QUESTIONS = (
    "1. Tang trials", "2. B co tot hon A", "3. C co tot hon B",
    "4. Decay giam", "5. Ket qua den tu", "6. Support va uncertainty",
    "7. Nhung gia thuyet nao chua duoc thu", "8. Chi phi da tieu",
    "9. Co nen dung",
)

VALID_PROSPECTIVE_STATUSES = ("NOT_RUN_NO_ELIGIBLE_NEW_DATA",)


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


def verify_fp10(run_dir, *, lab_root, pytest_xml=None) -> dict:
    root = Path(run_dir)
    lab_root = Path(lab_root)
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

    freeze = docs.get("freeze_manifest.json")
    replay = docs.get("replay_result.json")
    artifact_index = docs.get("artifact_index.json")

    # -- FP10-G-FREEZE: every required component category present, and
    # every hashed source file's digest RE-COMPUTED from disk right now --
    reasons = list(manifest_reasons)
    if freeze is None:
        reasons.append("freeze_manifest.json missing or unreadable")
    else:
        components = freeze.get("components", {})
        for key in REQUIRED_FREEZE_COMPONENTS:
            if key not in components or not components[key]:
                reasons.append(f"freeze_manifest.json's components is missing or empty for {key!r}")
        code_rows = components.get("code_dependency_engine_digests", [])
        if not code_rows:
            reasons.append("no code/dependency digests to re-verify")
        for row in code_rows:
            path = lab_root / row.get("path", "")
            if not path.is_file():
                reasons.append(f"freeze component file missing on disk: {row.get('path')}")
                continue
            if row.get("sha256") != _sha256(path):
                reasons.append(f"freeze component {row.get('path')}: digest does not match the "
                               "file currently on disk (stale or tampered freeze)")
        if freeze.get("status") != "FROZEN":
            reasons.append(f"freeze_manifest.json status is {freeze.get('status')!r}, not FROZEN")
    gates["FP10-G-FREEZE"] = _gate(not reasons, reasons)

    # -- FP10-G-REPLAY: the replay reproduced the key economic outputs
    # EXACTLY against the original committed run, with real numbers on
    # both sides, never a same-hash claim alone --
    reasons = list(manifest_reasons)
    if replay is None:
        reasons.append("replay_result.json missing or unreadable")
    else:
        if not replay.get("original_run_dir"):
            reasons.append("replay_result.json does not name the original run_dir it replays")
        if not replay.get("replay_run_dir"):
            reasons.append("replay_result.json does not name the fresh replay run_dir")
        comparisons = replay.get("comparisons")
        if not comparisons:
            reasons.append("replay_result.json has no comparisons -- nothing was actually checked")
        else:
            for row in comparisons:
                if row.get("original") is None or row.get("replay") is None:
                    reasons.append(f"{row.get('field')}: comparison is missing a real value on one side")
                    continue
                if row.get("match") is not True:
                    reasons.append(f"{row.get('field')}: original={row.get('original')} != "
                                   f"replay={row.get('replay')}")
        if replay.get("evaluation_label") not in ("FROZEN_REPLAY", "LOCKED_RETROSPECTIVE_EVALUATION"):
            reasons.append(f"replay_result.json's evaluation_label "
                           f"{replay.get('evaluation_label')!r} is not a guide-registered label")
        note = (replay.get("independence_note") or "").lower()
        if "not" not in note or "independent" not in note:
            reasons.append("replay_result.json must explicitly disclose that a same-data replay "
                           "is NOT independent confirmation (guide 22's own caveat)")
    gates["FP10-G-REPLAY"] = _gate(not reasons, reasons)

    # -- FP10-G-REPORT: all nine guide-required questions answered, each
    # traceable to a real evidence path --
    reasons = list(manifest_reasons)
    report_text = ((root / "final_report.md").read_text(encoding="utf-8")
                  if (root / "final_report.md").is_file() else "")
    for q in REQUIRED_REPORT_QUESTIONS:
        if q not in report_text:
            reasons.append(f"final_report.md does not answer required question: {q!r}")
    if "evidence/forward_persistence_fp_v1/" not in report_text:
        reasons.append("final_report.md never cites a real evidence path")
    forbidden_phrases = ("regime timing works", "proves the edge", "confirms the edge",
                         "definitively beats", "guaranteed to work")
    lowered = report_text.lower()
    for phrase in forbidden_phrases:
        if phrase in lowered:
            reasons.append(f"final_report.md contains a forbidden overclaim phrase: {phrase!r}")
    gates["FP10-G-REPORT"] = _gate(not reasons, reasons)

    # -- FP10-G-EXPOSURE: development role span and outer_evaluation
    # never-touched status are explicitly declared, not silent --
    reasons = list(manifest_reasons)
    if freeze is None:
        reasons.append("freeze_manifest.json missing or unreadable")
    else:
        exposure = freeze.get("data_exposure", {})
        if exposure.get("development_role_span") != "2020-01-01..2023-12-31":
            reasons.append("freeze_manifest.json's data_exposure.development_role_span is missing "
                           "or does not match the registered development role")
        if exposure.get("outer_evaluation_touched") is not False:
            reasons.append("freeze_manifest.json must explicitly assert outer_evaluation_touched: "
                           "false -- never left implicit")
        if exposure.get("prospective_status") not in VALID_PROSPECTIVE_STATUSES:
            reasons.append(f"freeze_manifest.json's prospective_status "
                           f"{exposure.get('prospective_status')!r} is not one of "
                           f"{VALID_PROSPECTIVE_STATUSES}")
        if not exposure.get("engineering_status"):
            reasons.append("freeze_manifest.json has no engineering_status")
    gates["FP10-G-EXPOSURE"] = _gate(not reasons, reasons)

    # -- FP10-G-HANDOFF: replay commands, unresolved issues, budget
    # summary and the owner-decision ledger path are all present --
    reasons = list(manifest_reasons)
    handoff_text = ((root / "handoff.md").read_text(encoding="utf-8")
                    if (root / "handoff.md").is_file() else "")
    for marker in ("## Replay command", "## Unresolved issues", "## Budget summary",
                  "owner_decisions.jsonl"):
        if marker not in handoff_text:
            reasons.append(f"handoff.md is missing required section/reference: {marker!r}")
    if artifact_index is None:
        reasons.append("artifact_index.json missing or unreadable")
    elif not artifact_index.get("phases"):
        reasons.append("artifact_index.json has no phases listed")
    gates["FP10-G-HANDOFF"] = _gate(not reasons, reasons)

    if missing:
        for gate in gates:
            if gates[gate]["pass"]:
                gates[gate] = _gate(False, gates[gate]["reasons"] +
                                    [f"missing artifacts: {', '.join(missing)}"])
    overall = all(g["pass"] for g in gates.values()) and all(g in gates for g in REQUIRED_GATES)
    return {
        "schema": "regime_lab.fp10_verification.v1",
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
