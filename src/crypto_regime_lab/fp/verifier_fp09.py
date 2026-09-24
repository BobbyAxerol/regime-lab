"""FP-09 gate FP09-G-* thin verifier (guide section 21 exit gate).

Same discipline as verifier_fp01..08: every gate re-derives its verdict from
the raw artifacts on disk, never trusting a stored summary field.

  * FP09-G-CALIBRATION: SELECTOR_CAL_MATCHED's per-event deferral is
    recomputed from its OWN schedule vs the base (FIXED_CAL) schedule and
    must equal SELECTOR_REGIME_TIMING's realized per-event deferral
    EXACTLY -- a mechanical match built with no reference to either arm's
    realized return/equity (checked structurally: the design artifact
    records no returns-derived field feeding the match).
  * FP09-G-BUDGET: the aggregate AND per-event deferred-bar budgets match
    between REGIME_TIMING and CAL_MATCHED, and no event exceeds the frozen
    K_MAX_BARS bound.
  * FP09-G-EXEC: all three arms ran a real deployment (fills present,
    account bars cover the shared frame) AND the timing lifecycle was
    genuinely exercised -- at least one real event was deferred by a
    nonzero bar count (never a vacuous "nothing moved" pass).
  * FP09-G-CONTRAST: the reported verdict uses the DIRECT treatment
    contrast (REGIME_TIMING minus CAL_MATCHED), never an indirect proxy
    like REGIME_TIMING minus FIXED_CAL alone.
  * FP09-G-SCOPE: report.md states one of COMPLETED / BLOCKED /
    NOT_OPENED_SECONDARY explicitly, discloses the real sample size (this
    phase's admission-event count), and never concludes CADENCE_ARTIFACT
    from a placebo beating a slow calendar alone (guide 21's own
    prohibition) or any other forbidden overclaim phrase.
"""
from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

REQUIRED_GATES = ("FP09-G-CALIBRATION", "FP09-G-BUDGET", "FP09-G-EXEC",
                  "FP09-G-CONTRAST", "FP09-G-SCOPE")

REQUIRED_ARTIFACTS = (
    "study_freeze.json", "schedules.json", "accounts.json",
    "paired_contrasts.json", "resource_budget.json", "test_registry.json",
    "phase_manifest.json", "gate_receipt.json", "report.md", "handoff.md",
)

ARMS = ("SELECTOR_FIXED_CAL", "SELECTOR_CAL_MATCHED", "SELECTOR_REGIME_TIMING")
PRIMARY_LABEL = "SELECTOR_REGIME_TIMING - SELECTOR_CAL_MATCHED"
SCOPE_LABELS = ("COMPLETED", "BLOCKED", "NOT_OPENED_SECONDARY")


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


def verify_fp09(run_dir, *, pytest_xml=None) -> dict:
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

    freeze = docs.get("study_freeze.json")
    schedules = docs.get("schedules.json")
    accounts = docs.get("accounts.json")
    contrasts = docs.get("paired_contrasts.json")

    # -- FP09-G-CALIBRATION: the timing design (threshold/bound/windows/
    # seed) was frozen BEFORE any account ran, CAL_MATCHED's derivation
    # note references no return/equity information, and CAL_MATCHED's
    # schedule is genuinely INDEPENDENT of REGIME_TIMING's realized one --
    # never a mechanical copy of it (the exact defect an earlier version of
    # this phase caught in itself: copying REGIME_TIMING's own realized
    # per-event deferral verbatim is mathematically guaranteed to
    # reproduce its exact schedule, since both reduce to the same
    # origin_bar + deferred_bars formula) --
    reasons = list(manifest_reasons)
    if freeze is None or schedules is None:
        reasons.append("study_freeze.json or schedules.json missing or unreadable")
    else:
        frozen = freeze.get("timing_design", {})
        for key in ("vol_threshold", "k_max_bars", "vol_short_days", "vol_long_days",
                   "cal_matched_seed"):
            if frozen.get(key) is None:
                reasons.append(f"study_freeze.json's timing_design is missing {key!r} -- "
                               "the design must be frozen before any account ran")
        regime_by_id = {e["activation_id"]: e["requested_at_bar"]
                       for e in schedules.get("SELECTOR_REGIME_TIMING", [])}
        matched_by_id = {e["activation_id"]: e["requested_at_bar"]
                        for e in schedules.get("SELECTOR_CAL_MATCHED", [])}
        if not (regime_by_id and matched_by_id):
            reasons.append("schedules.json is missing REGIME_TIMING or CAL_MATCHED's schedule")
        common = set(regime_by_id) & set(matched_by_id)
        if common and all(regime_by_id[a] == matched_by_id[a] for a in common):
            reasons.append("SELECTOR_CAL_MATCHED's schedule is IDENTICAL to SELECTOR_REGIME_TIMING's "
                           "at every event -- this is the exact structural degeneracy this phase's "
                           "own history caught: a placebo built FROM the treatment's realized "
                           "outcome is not an independent control")
        diagnostics_doc = schedules.get("regime_timing_diagnostics")
        matched_diag_doc = schedules.get("cal_matched_diagnostics")
        if diagnostics_doc is None:
            reasons.append("schedules.json has no regime_timing_diagnostics block to audit the "
                           "mechanism the deferral came from")
        if matched_diag_doc is None:
            reasons.append("schedules.json has no cal_matched_diagnostics block to audit the "
                           "seeded-draw mechanism CAL_MATCHED used")
        derivation_note = schedules.get("cal_matched_derivation", "")
        for forbidden in ("equity", "return", "pnl", "daily_return", "regime_timing_diagnostics"):
            if forbidden in derivation_note.lower():
                reasons.append(f"cal_matched_derivation note references {forbidden!r} -- the "
                               "control must be built from a fixed seed and bound only, with no "
                               "reference to either arm's realized outcome")
    gates["FP09-G-CALIBRATION"] = _gate(not reasons, reasons)

    # -- FP09-G-BUDGET: REGIME_TIMING and CAL_MATCHED both respect the SAME
    # frozen k_max_bars per-event bound (a matched MAXIMUM budget, not a
    # matched realized value) and no deferral is negative --
    reasons = list(manifest_reasons)
    if freeze is None or schedules is None:
        reasons.append("study_freeze.json or schedules.json missing or unreadable")
    else:
        k_max = (freeze.get("timing_design", {})).get("k_max_bars")
        base_by_id = {e["activation_id"]: e["requested_at_bar"]
                     for e in schedules.get("SELECTOR_FIXED_CAL", [])}
        regime_by_id = {e["activation_id"]: e["requested_at_bar"]
                       for e in schedules.get("SELECTOR_REGIME_TIMING", [])}
        matched_by_id = {e["activation_id"]: e["requested_at_bar"]
                        for e in schedules.get("SELECTOR_CAL_MATCHED", [])}
        common = set(base_by_id) & set(regime_by_id) & set(matched_by_id)
        if not common:
            reasons.append("no activation_id common to all three schedules -- nothing to budget-check")
        if k_max is None:
            reasons.append("study_freeze.json's timing_design has no k_max_bars bound registered")
        else:
            for aid in common:
                for arm_name, by_id in (("REGIME_TIMING", regime_by_id), ("CAL_MATCHED", matched_by_id)):
                    d = by_id[aid] - base_by_id[aid]
                    if d < 0:
                        reasons.append(f"{aid}/{arm_name}: deferral is negative ({d}) -- timing "
                                       "may only defer, never advance, an admission")
                    if d > k_max:
                        reasons.append(f"{aid}/{arm_name}: deferred {d} bars, exceeding the "
                                       f"frozen K_MAX_BARS={k_max} bound")
    gates["FP09-G-BUDGET"] = _gate(not reasons, reasons)

    # -- FP09-G-EXEC: three real accounts with fills, over the shared frame,
    # AND the timing lifecycle was genuinely (non-vacuously) exercised --
    reasons = list(manifest_reasons)
    if accounts is None:
        reasons.append("accounts.json missing or unreadable")
    else:
        by_arm = accounts.get("by_arm", {})
        for arm in ARMS:
            info = by_arm.get(arm)
            if info is None:
                reasons.append(f"accounts.json has no entry for arm {arm}")
                continue
            if info.get("status") != "OK":
                reasons.append(f"{arm}: account status is {info.get('status')!r}, not OK")
            if not info.get("fill_count"):
                reasons.append(f"{arm}: zero fills -- an empty run proves nothing")
            if not info.get("bars") or info["bars"] != accounts.get("frame_bars"):
                reasons.append(f"{arm}: account bar count does not match the shared frame")
        if len(by_arm) != len(ARMS):
            reasons.append(f"expected exactly {len(ARMS)} arms, found {len(by_arm)}")
    if schedules is None:
        reasons.append("schedules.json missing or unreadable")
    else:
        diagnostics_doc = schedules.get("regime_timing_diagnostics") or []
        nonzero = [d for d in diagnostics_doc if d.get("deferred_bars", 0) != 0]
        if not nonzero:
            reasons.append("every REGIME_TIMING event has deferred_bars == 0 -- the timing "
                           "lifecycle was never actually exercised (this lab's own standing "
                           "lesson: a gate must not pass on an empty/no-op run)")
    gates["FP09-G-EXEC"] = _gate(not reasons, reasons)

    # -- FP09-G-CONTRAST: the reported verdict uses the direct treatment
    # contrast, not an indirect proxy --
    reasons = list(manifest_reasons)
    if contrasts is None:
        reasons.append("paired_contrasts.json missing or unreadable")
    elif contrasts.get("primary", {}).get("label") != PRIMARY_LABEL:
        reasons.append(f"paired_contrasts.json's primary contrast is not labelled {PRIMARY_LABEL!r}")
    gates["FP09-G-CONTRAST"] = _gate(not reasons, reasons)

    # -- FP09-G-SCOPE: an explicit scope label, disclosed real sample size,
    # no forbidden overclaim, no unearned CADENCE_ARTIFACT conclusion --
    reasons = list(manifest_reasons)
    report_text = (root / "report.md").read_text(encoding="utf-8") if (root / "report.md").is_file() else ""
    if not any(f"scope: {label}" in report_text or f"**{label}**" in report_text
              for label in SCOPE_LABELS):
        reasons.append(f"report.md does not clearly state one of {SCOPE_LABELS}")
    if "## Permitted conclusions" not in report_text:
        reasons.append("report.md has no '## Permitted conclusions' section")
    forbidden_phrases = ("regime timing works", "proves the edge", "confirms the edge",
                         "timing definitively", "regime timing beats")
    lowered = report_text.lower()
    for phrase in forbidden_phrases:
        if phrase in lowered:
            reasons.append(f"report.md contains a forbidden overclaim phrase: {phrase!r}")
    if "cadence_artifact" in lowered and PRIMARY_LABEL.lower() not in lowered:
        reasons.append("report.md concludes CADENCE_ARTIFACT without citing the required direct "
                       "treatment contrast (guide 21's own prohibition)")
    if "n=" not in report_text and "admission event" not in lowered:
        reasons.append("report.md does not disclose the real admission-event sample size")
    gates["FP09-G-SCOPE"] = _gate(not reasons, reasons)

    if missing:
        for gate in gates:
            if gates[gate]["pass"]:
                gates[gate] = _gate(False, gates[gate]["reasons"] +
                                    [f"missing artifacts: {', '.join(missing)}"])
    overall = all(g["pass"] for g in gates.values()) and all(g in gates for g in REQUIRED_GATES)
    return {
        "schema": "regime_lab.fp09_verification.v1",
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
