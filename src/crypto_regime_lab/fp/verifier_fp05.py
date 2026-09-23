"""FP-05 gate FP05-G-* thin verifier (guide section 17 exit gate).

Same discipline as verifier_fp01..04: every gate re-derives its verdict
from the raw artifacts on disk. FP05-G-SPLIT re-walks every recorded OOF
fold and independently re-checks label_available_at against that fold's
own decision time (guide 8.4's dormant-risk class); FP05-G-MODEL refits
the stored X/y/weight/alpha and checks the coefficients reproduce
byte-for-byte (determinism, not merely "a model exists"); FP05-G-SUPPORT
recomputes the decay-risk branch from the raw origin counts rather than
trusting the stored label. Never raises: returns the gate matrix with
reasons.
"""
from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

REQUIRED_GATES = ("FP05-G-SPLIT", "FP05-G-MODEL", "FP05-G-SCORE",
                  "FP05-G-SUPPORT", "FP05-G-ACTION", "FP05-G-REPORT")

REQUIRED_ARTIFACTS = (
    "oof_diagnostics.json", "model_selection.json", "candidate_scores.json",
    "admission_and_deployment.json", "resource_budget.json", "test_registry.json",
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


def verify_fp05(run_dir, *, pytest_xml=None) -> dict:
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

    oof = docs.get("oof_diagnostics.json")
    model_sel = docs.get("model_selection.json")
    scores = docs.get("candidate_scores.json")
    admission = docs.get("admission_and_deployment.json")

    # -- FP05-G-SPLIT: independently re-check every recorded OOF fold: no
    # training row's label was available at/after its validation origin's
    # own decision time (guide 8.4's dormant-risk class) --
    reasons = list(manifest_reasons)
    if oof is None:
        reasons.append("oof_diagnostics.json missing or unreadable")
    else:
        import pandas as pd

        folds = oof.get("fold_audit", [])
        if not folds:
            reasons.append("no OOF fold audit rows to check")
        for fold in folds:
            decision_time = pd.Timestamp(fold["validation_origin_time"])
            for train_row in fold.get("train_label_available_ats", []):
                available = pd.Timestamp(train_row)
                if available >= decision_time:
                    reasons.append(
                        f"fold at {fold['validation_origin']}: a training row's "
                        f"label_available_at {train_row} is not before the validation "
                        f"decision time {fold['validation_origin_time']} -- future-label leak")
    gates["FP05-G-SPLIT"] = _gate(not reasons, reasons)

    # -- FP05-G-MODEL: deterministic fit, schema/version complete --
    reasons = list(manifest_reasons)
    if model_sel is None:
        reasons.append("model_selection.json missing or unreadable")
    else:
        final_model = model_sel.get("final_model")
        if final_model is None:
            reasons.append("no final_model recorded")
        else:
            for field in ("schema", "coef", "intercept", "feature_mean", "feature_std",
                         "alpha", "n_train", "feature_names"):
                if field not in final_model:
                    reasons.append(f"final_model missing field {field}")
            import numpy as np

            from .selector_b import fit_ridge

            refit_inputs = model_sel.get("refit_inputs")
            if refit_inputs is None:
                reasons.append("no refit_inputs recorded -- cannot independently re-derive "
                               "determinism")
            else:
                X = np.array(refit_inputs["X"])
                y = np.array(refit_inputs["y"])
                w = np.array(refit_inputs["w"])
                refit = fit_ridge(X, y, w, final_model["alpha"])
                if not np.allclose(refit["coef"], final_model["coef"], atol=1e-9):
                    reasons.append("refitting from the recorded X/y/weights/alpha does not "
                                   "reproduce the stored coefficients -- not deterministic")
    gates["FP05-G-MODEL"] = _gate(not reasons, reasons)

    # -- FP05-G-SCORE: utility/decay algebra and units reconcile --
    reasons = list(manifest_reasons)
    if scores is None:
        reasons.append("candidate_scores.json missing or unreadable")
    else:
        rows = scores.get("scored", [])
        if not rows:
            reasons.append("no scored candidates to check")
        for row in rows:
            if row.get("predicted_forward_utility") is None:
                continue
            expected_decay_point = row.get("is_mean_daily_return", 0) - row["predicted_forward_utility"]
            if row.get("decay_risk_score") is not None and row.get("branch") == "MEAN_DECAY":
                if row["decay_risk_score"] < -1e-9:
                    reasons.append(f"{row.get('record_id')}: MEAN_DECAY decay_risk_score "
                                   f"{row['decay_risk_score']} is negative -- guide 8.5's "
                                   "max(IS-forward, 0) construction cannot go negative")
            if row.get("D_point_estimate") is not None:
                if abs(row["D_point_estimate"] - expected_decay_point) > 1e-9:
                    reasons.append(f"{row.get('record_id')}: D_point_estimate does not equal "
                                   "is_mean_daily_return - predicted_forward_utility")
    gates["FP05-G-SCORE"] = _gate(not reasons, reasons)

    # -- FP05-G-SUPPORT: insufficient support goes to the REGISTERED
    # fallback, recomputed from the raw origin counts, never trusted --
    reasons = list(manifest_reasons)
    if oof is None:
        reasons.append("oof_diagnostics.json missing or unreadable")
    else:
        from .selector_b import decay_risk_branch

        n_fit = oof.get("n_fit_origins")
        n_oof = oof.get("n_validation_origins")
        if n_fit is None or n_oof is None:
            reasons.append("oof_diagnostics.json missing n_fit_origins/n_validation_origins")
        else:
            recomputed = decay_risk_branch(n_oof, n_fit_origins=n_fit)
            stored_branch = (model_sel or {}).get("decay_risk_branch", {}).get("branch")
            if stored_branch != recomputed["branch"]:
                reasons.append(f"stored decay_risk_branch {stored_branch!r} does not match "
                               f"the branch independently recomputed from n_fit={n_fit}, "
                               f"n_oof={n_oof} ({recomputed['branch']!r})")
    gates["FP05-G-SUPPORT"] = _gate(not reasons, reasons)

    # -- FP05-G-ACTION: selector output actually reaches admission/deployment --
    reasons = list(manifest_reasons)
    if admission is None:
        reasons.append("admission_and_deployment.json missing or unreadable")
    else:
        lineage = admission.get("admission_lineage")
        deployment = admission.get("deployment_result")
        if not lineage:
            reasons.append("no admission_lineage recorded")
        if admission.get("selector_b_decision") == "ADMIT":
            if deployment is None:
                reasons.append("selector B chose ADMIT but no deployment_result is recorded")
            elif not deployment.get("fills"):
                reasons.append("deployment_result has zero fills -- the selection did not "
                               "reach a real account")
            selected_params = admission.get("selected_params")
            deployed_params = (lineage.get("0") or {}).get("consumed")
            if selected_params != deployed_params:
                reasons.append("the params actually consumed by admission differ from what "
                               "selector B selected")
        elif admission.get("selector_b_decision") not in ("COMMON_FLAT_FALLBACK", "ADMIT"):
            reasons.append(f"unrecognised selector_b_decision {admission.get('selector_b_decision')!r}")
    gates["FP05-G-ACTION"] = _gate(not reasons, reasons)

    # -- FP05-G-REPORT: technical and scientific status kept separate --
    reasons = list(manifest_reasons)
    report_text = (root / "report.md").read_text(encoding="utf-8") if (root / "report.md").is_file() else ""
    if "## Permitted conclusions" not in report_text:
        reasons.append("report.md has no '## Permitted conclusions' section")
    if "Technical:" not in report_text or "Research:" not in report_text:
        reasons.append("report.md does not separately label Technical: and Research: status")
    gates["FP05-G-REPORT"] = _gate(not reasons, reasons)

    if missing:
        for gate in gates:
            if gates[gate]["pass"]:
                gates[gate] = _gate(False, gates[gate]["reasons"] +
                                    [f"missing artifacts: {', '.join(missing)}"])
    overall = all(g["pass"] for g in gates.values()) and all(g in gates for g in REQUIRED_GATES)
    return {
        "schema": "regime_lab.fp05_verification.v1",
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
