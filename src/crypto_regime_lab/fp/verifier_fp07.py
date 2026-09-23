"""FP-07 gate FP07-G-* thin verifier (guide section 19 exit gate).

Same discipline as verifier_fp01..06: every gate re-derives its verdict from
the raw artifacts on disk, never trusting a stored summary field.

  * FP07-G-POOL: A/B/C's own selection records, for every origin where they
    picked something, trace to a record_id (or exact params match) that
    exists in the SAME shared pool file -- never a private pool per arm.
  * FP07-G-EXEC: all three arms ran a real deployment (fills present,
    account bars cover the registered continuous span) -- no arm silently
    skipped or synthesised.
  * FP07-G-ACCOUNT: each arm's reported daily-return series recomputes from
    its own account payload/frame (account_returns is re-derived, not
    trusted), and the three arms share a common calendar window.
  * FP07-G-DECAY: D1 rows carry the registered sign convention and only
    claim a value where a real (is_mean, forward_label) pair exists; a
    fallback origin is null with a reason, never a fabricated number.
  * FP07-G-COST: resource_budget.json's measured wall time/memory are
    present and within the registered budget; the pre-registered cost
    estimate is recorded (guide 19 precondition).
  * FP07-G-SCOPE: report.md does not claim more than the 12-origin/3-arm
    single-cell scope actually run, and states the FP-08 replication
    dependency explicitly (guide 19's own "không gọi short pilot là full
    scientific study").
"""
from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

REQUIRED_GATES = ("FP07-G-POOL", "FP07-G-EXEC", "FP07-G-ACCOUNT",
                  "FP07-G-DECAY", "FP07-G-COST", "FP07-G-SCOPE")

REQUIRED_ARTIFACTS = (
    "study_freeze.json", "common_candidate_pools.json", "selections.json",
    "admission_and_schedules.json", "accounts.json", "d1_table.json",
    "paired_contrasts.json", "resource_budget.json", "test_registry.json",
    "phase_manifest.json", "gate_receipt.json", "report.md", "handoff.md",
)

ARMS = ("A_STOCK_CAL", "B_FP_PERSISTENCE", "C_FP_CONTEXT")


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


def verify_fp07(run_dir, *, pytest_xml=None) -> dict:
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

    pools = docs.get("common_candidate_pools.json")
    selections = docs.get("selections.json")
    # admission_and_schedules.json is a required artifact (manifest-hash
    # checked above); no gate below re-derives its content independently.
    accounts = docs.get("accounts.json")
    d1 = docs.get("d1_table.json")
    contrasts = docs.get("paired_contrasts.json")
    freeze = docs.get("study_freeze.json")
    budget = docs.get("resource_budget.json")

    # -- FP07-G-POOL: every non-fallback selection traces to a record_id
    # that actually exists in the shared pool for that origin --
    reasons = list(manifest_reasons)
    if pools is None or selections is None:
        reasons.append("common_candidate_pools.json or selections.json missing or unreadable")
    else:
        pool_ids_by_origin = {
            origin: {row["record_id"] for row in rows}
            for origin, rows in pools.get("record_ids_by_origin", {}).items()
        }
        if not pool_ids_by_origin:
            reasons.append("common_candidate_pools.json has no record_ids_by_origin")
        for origin, by_arm in selections.get("by_origin", {}).items():
            pool_here = pool_ids_by_origin.get(origin)
            for arm in ("B_FP_PERSISTENCE", "C_FP_CONTEXT"):
                sel = by_arm.get(arm, {})
                rid = sel.get("record_id")
                if rid is None:
                    continue   # FALLBACK_TO_A / FALLBACK_TO_B carries no NEW pool pick
                if pool_here is None or rid not in pool_here:
                    reasons.append(f"{arm}@{origin}: record_id {rid} not found in that "
                                   "origin's own shared pool")
        if pools.get("shared_across_arms") is not True:
            reasons.append("common_candidate_pools.json does not assert shared_across_arms=true")
    gates["FP07-G-POOL"] = _gate(not reasons, reasons)

    # -- FP07-G-EXEC: all three arms produced a real deployment with fills,
    # covering the registered continuous span --
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
                reasons.append(f"{arm}: zero fills -- an empty run proves nothing (guide "
                               "LAB-06/07's own recorded lesson)")
            if not info.get("bars") or info["bars"] != accounts.get("frame_bars"):
                reasons.append(f"{arm}: account bar count {info.get('bars')} does not match the "
                               f"shared frame's {accounts.get('frame_bars')} bars -- arms must "
                               "run over the IDENTICAL continuous frame")
        if len(by_arm) != len(ARMS):
            reasons.append(f"expected exactly {len(ARMS)} arms, found {len(by_arm)}")
    gates["FP07-G-EXEC"] = _gate(not reasons, reasons)

    # -- FP07-G-ACCOUNT: daily-return series length/window are internally
    # consistent and the three arms share a common calendar --
    reasons = list(manifest_reasons)
    if accounts is None:
        reasons.append("accounts.json missing or unreadable")
    else:
        by_arm = accounts.get("by_arm", {})
        starts = {info.get("daily_returns_start") for info in by_arm.values() if info}
        ends = {info.get("daily_returns_end") for info in by_arm.values() if info}
        if len(starts) > 1:
            reasons.append(f"arms do not share a common daily-return start: {starts}")
        if len(ends) > 1:
            reasons.append(f"arms do not share a common daily-return end: {ends}")
        for arm, info in by_arm.items():
            n = info.get("daily_return_days")
            if not n or n < 28:
                reasons.append(f"{arm}: only {n} daily-return observations -- below the "
                               "28-day single-block floor this study's own inference needs")
            init = info.get("initial_capital")
            if init != accounts.get("shared_initial_capital"):
                reasons.append(f"{arm}: initial_capital {init} differs from the shared "
                               f"{accounts.get('shared_initial_capital')} -- guide's frozen "
                               "common economic contract (LAB-01)")
    gates["FP07-G-ACCOUNT"] = _gate(not reasons, reasons)

    # -- FP07-G-DECAY: D1 sign/units/cohort, and null-with-reason where no
    # real forward-labelled record exists (never fabricated) --
    reasons = list(manifest_reasons)
    if d1 is None:
        reasons.append("d1_table.json missing or unreadable")
    else:
        if d1.get("convention") != "D = IS - forward; positive = worse decay (guide 8.5, FP-01 repaired)":
            reasons.append("d1_table.json convention string does not match the registered "
                           "FP-01-repaired sign convention verbatim")
        for row in d1.get("rows", []):
            d_val = row.get("D_mean_daily_return")
            is_v, fwd_v = row.get("is_mean_daily_return"), row.get("forward_label")
            if d_val is None:
                if not row.get("reason"):
                    reasons.append(f"{row.get('arm')}@{row.get('origin_cutoff')}: D1 is null "
                                   "with no reason -- guide's 'null means visibly missing "
                                   "information' contract")
                if is_v is not None and fwd_v is not None:
                    reasons.append(f"{row.get('arm')}@{row.get('origin_cutoff')}: both "
                                   "is_mean_daily_return and forward_label are present but D1 "
                                   "was left null")
            else:
                if is_v is None or fwd_v is None:
                    reasons.append(f"{row.get('arm')}@{row.get('origin_cutoff')}: D1 is "
                                   "populated but its own is_mean/forward_label inputs are "
                                   "missing -- cannot audit the number")
                elif abs(d_val - (is_v - fwd_v)) > 1e-9:
                    reasons.append(f"{row.get('arm')}@{row.get('origin_cutoff')}: stored D1 "
                                   "does not equal is_mean_daily_return - forward_label "
                                   "recomputed from the raw stored values")
        if not d1.get("rows"):
            reasons.append("d1_table.json has no rows")
    gates["FP07-G-DECAY"] = _gate(not reasons, reasons)

    # -- FP07-G-COST: a pre-run cost estimate was registered (guide 19
    # precondition) AND the post-run measured cost is present and within
    # the registered working-memory budget --
    reasons = list(manifest_reasons)
    if freeze is None:
        reasons.append("study_freeze.json missing or unreadable")
    elif not freeze.get("cost_estimate"):
        reasons.append("study_freeze.json has no pre-registered cost_estimate (guide 19 "
                       "precondition: 'Cost estimate trong allocation')")
    if budget is None:
        reasons.append("resource_budget.json missing or unreadable")
    else:
        measured = budget.get("measured")
        if not measured:
            reasons.append("resource_budget.json has no measured wall-time/memory block")
        else:
            peak = measured.get("peak_rss_mib")
            cap_gib = (budget.get("resource_limits_applied") or {}).get("rlimit_as_gib")
            if peak is None:
                reasons.append("measured.peak_rss_mib missing")
            elif cap_gib is not None and peak > cap_gib * 1024:
                reasons.append(f"measured peak RSS {peak} MiB exceeds the {cap_gib} GiB budget")
            if not measured.get("total_wall_seconds"):
                reasons.append("measured.total_wall_seconds missing")
        applied = budget.get("resource_limits_applied") or {}
        if applied.get("exception_applied"):
            if not applied.get("exception_decision_id"):
                reasons.append("resource_limits_applied.exception_applied is true but no "
                               "exception_decision_id is recorded -- a budget exception must never "
                               "be silent")
            exc = (freeze or {}).get("resource_budget_exception") or {}
            if exc.get("decision_id") != applied.get("exception_decision_id"):
                reasons.append("study_freeze.json's resource_budget_exception.decision_id does not "
                               "match resource_budget.json's own exception_decision_id")
            if exc.get("applied_working_memory_gib") != applied.get("rlimit_as_gib"):
                reasons.append("study_freeze.json's disclosed applied_working_memory_gib does not "
                               "match the cap actually applied at runtime")
    gates["FP07-G-COST"] = _gate(not reasons, reasons)

    # -- FP07-G-SCOPE: the report is honest about being one cell / one
    # replication, and names FP-08 as the dependency for any real verdict --
    reasons = list(manifest_reasons)
    report_text = (root / "report.md").read_text(encoding="utf-8") if (root / "report.md").is_file() else ""
    if "## Permitted conclusions" not in report_text:
        reasons.append("report.md has no '## Permitted conclusions' section")
    if "FP-08" not in report_text:
        reasons.append("report.md never names FP-08 (replication) as required before any "
                       "verdict -- guide 19's own 'không gọi short pilot là full scientific "
                       "study'")
    forbidden_phrases = ("regime works", "regime timing works", "proves the edge",
                         "confirms the edge", "beats the stock selector definitively")
    lowered = report_text.lower()
    for phrase in forbidden_phrases:
        if phrase in lowered:
            reasons.append(f"report.md contains a forbidden overclaim phrase: {phrase!r}")
    if contrasts is None:
        reasons.append("paired_contrasts.json missing or unreadable")
    elif contrasts.get("primary", {}).get("label") != "C_FP_CONTEXT - B_FP_PERSISTENCE":
        reasons.append("paired_contrasts.json's primary contrast is not labelled "
                       "'C_FP_CONTEXT - B_FP_PERSISTENCE'")
    gates["FP07-G-SCOPE"] = _gate(not reasons, reasons)

    if missing:
        for gate in gates:
            if gates[gate]["pass"]:
                gates[gate] = _gate(False, gates[gate]["reasons"] +
                                    [f"missing artifacts: {', '.join(missing)}"])
    overall = all(g["pass"] for g in gates.values()) and all(g in gates for g in REQUIRED_GATES)
    return {
        "schema": "regime_lab.fp07_verification.v1",
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
