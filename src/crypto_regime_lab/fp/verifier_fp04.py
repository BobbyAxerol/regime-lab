"""FP-04 gate FP04-G-* thin verifier (guide section 16 exit gate).

Same discipline as verifier_fp01/02/03: every gate RE-DERIVES its verdict
from the raw artifacts on disk -- re-slicing origin_ledger.json's own
trial_records to independently recompute a region's medoid (FP04-G-REGION)
and re-summing resource_budget.json's own per-origin fields (FP04-G-REUSE)
rather than trusting a stored summary field. Never raises: returns the gate
matrix with reasons.
"""
from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

REQUIRED_GATES = ("FP04-G-LEDGER", "FP04-G-CAUSAL", "FP04-G-REGION",
                  "FP04-G-SUPPORT", "FP04-G-REUSE")

REQUIRED_ARTIFACTS = (
    "origin_ledger.json", "ledger_records.json", "region_policy.json",
    "resource_budget.json", "test_registry.json", "phase_manifest.json",
    "gate_receipt.json", "report.md", "handoff.md",
)

MIN_SUPPORT_FOR_MODEL_READY = 2


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _gate(ok: bool, reasons: list) -> dict:
    return {"pass": bool(ok), "reasons": list(reasons)}


def _load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _real_medoid(schema, members: list[dict]) -> dict:
    from .forward_ledger import region_medoid

    return region_medoid(schema, members)


def verify_fp04(run_dir, *, pytest_xml=None) -> dict:
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

    ledger = docs.get("origin_ledger.json")
    records_doc = docs.get("ledger_records.json")
    policy = docs.get("region_policy.json")

    # -- FP04-G-LEDGER: an actual archive with real provenance, every
    # declared origin reported regardless of outcome --
    reasons = list(manifest_reasons)
    if ledger is None:
        reasons.append("origin_ledger.json missing or unreadable")
    else:
        origins = ledger.get("origins", [])
        declared = policy.get("origin_grid", []) if policy else []
        if declared and sorted(o["origin_cutoff"] for o in origins) != sorted(declared):
            reasons.append("origin_ledger.json does not cover exactly the frozen origin_grid "
                           "(every declared origin must be reported regardless of outcome)")
        for o in origins:
            for field in ("origin_cutoff", "wf_ok", "seed", "trials_requested",
                          "market_partitions_used", "load_start", "load_end"):
                if field not in o:
                    reasons.append(f"{o.get('origin_cutoff', '?')}: missing provenance field {field}")
            if o.get("wf_ok") and not o.get("trial_records"):
                reasons.append(f"{o['origin_cutoff']}: wf_ok=True but no trial_records archived")
        if not origins:
            reasons.append("origin_ledger.json has zero origins")
    gates["FP04-G-LEDGER"] = _gate(not reasons, reasons)

    # -- FP04-G-CAUSAL: re-derive maturity/discovery/censorship properties
    # from the raw records, never trust a stored summary field --
    reasons = list(manifest_reasons)
    if records_doc is None:
        reasons.append("ledger_records.json missing or unreadable")
    else:
        import pandas as pd

        records = records_doc.get("records", [])
        if not records:
            reasons.append("ledger_records.json has zero records to check causality on")
        for r in records:
            if r["maturity_state"] == "censored_or_failed_record":
                if r.get("label") is not None:
                    reasons.append(f"{r['record_id']}: censored record has a non-null label "
                                   f"{r['label']!r} (guide 7.1: outcome missing must never become "
                                   "a value, let alone zero)")
                if not r.get("censored_reason"):
                    reasons.append(f"{r['record_id']}: censored record has no reason recorded")
            if r["maturity_state"] == "matured_forward_record" and r.get("label") is None:
                reasons.append(f"{r['record_id']}: matured record has a null label")
            # re-derive label_available_at independently from origin_cutoff + horizon.
            # origin_cutoff is the plain join-key string (may be naive); normalise to
            # UTC before arithmetic so this compares against label_available_at's own
            # tz-aware form on equal terms.
            origin_ts = pd.Timestamp(r["origin_cutoff"])
            origin_ts = origin_ts.tz_localize("UTC") if origin_ts.tzinfo is None else origin_ts
            horizon = policy.get("forward_horizon_days") if policy else None
            if horizon is not None:
                expected = (origin_ts + pd.Timedelta(days=horizon)).isoformat()
                if r["label_available_at"] != expected:
                    reasons.append(f"{r['record_id']}: label_available_at {r['label_available_at']} "
                                   f"does not match origin_cutoff+forward_horizon_days ({expected})")
        # discovery independence: every record's medoid_trial_id must exist inside
        # ITS OWN origin's raw trial_records, never a different origin's
        if ledger is not None:
            trials_by_origin = {o["origin_cutoff"]: {t["trial_id"] for t in o.get("trial_records", [])}
                                for o in ledger.get("origins", [])}
            for r in records:
                own_trials = trials_by_origin.get(r["origin_cutoff"], set())
                if r["maturity_state"] != "censored_or_failed_record" and own_trials \
                        and r["medoid_trial_id"] not in own_trials:
                    reasons.append(f"{r['record_id']}: medoid_trial_id {r['medoid_trial_id']} does "
                                   f"not exist in this origin's own trial_records -- possible "
                                   "cross-origin leak")
    gates["FP04-G-CAUSAL"] = _gate(not reasons, reasons)

    # -- FP04-G-REGION: descriptors reconstruct from the raw candidate pool,
    # not merely echo a stored summary --
    reasons = list(manifest_reasons)
    if ledger is None or policy is None:
        reasons.append("origin_ledger.json or region_policy.json missing or unreadable")
    else:
        from ..selector.alpha_schemas import SCHEMAS

        schema = SCHEMAS.get(policy.get("alpha_id", "A-SC"))
        checked_any = False
        for o in ledger.get("origins", []):
            if not o.get("wf_ok"):
                continue
            trial_by_id = {t["trial_id"]: t for t in o.get("trial_records", [])}
            for region in o.get("regions", []):
                members = [trial_by_id[i] for i in region["member_candidate_ids"] if i in trial_by_id]
                if len(members) != len(region["member_candidate_ids"]):
                    reasons.append(f"{o['origin_cutoff']}/{region['region_id']}: a member_candidate_id "
                                   "is not present in this origin's own trial_records")
                    continue
                checked_any = True
                recomputed = _real_medoid(schema, members)
                if recomputed["trial_id"] != region["medoid_trial_id"]:
                    reasons.append(f"{o['origin_cutoff']}/{region['region_id']}: stored medoid "
                                   f"{region['medoid_trial_id']} does not match the medoid "
                                   f"independently recomputed from its own members "
                                   f"({recomputed['trial_id']})")
        if not checked_any:
            reasons.append("no region with reconstructible members to check")
    gates["FP04-G-REGION"] = _gate(not reasons, reasons)

    # -- FP04-G-SUPPORT: counts are honest; model-ready vs descriptive-only
    # separated, and the separation matches a fresh recount --
    reasons = list(manifest_reasons)
    if records_doc is None:
        reasons.append("ledger_records.json missing or unreadable")
    else:
        records = records_doc.get("records", [])
        summary = records_doc.get("support_summary")
        if summary is None:
            reasons.append("ledger_records.json has no support_summary")
        else:
            recount_model_ready = sum(
                1 for r in records if r["maturity_state"] == "matured_forward_record"
                and r.get("region_support_within_origin", 0) >= MIN_SUPPORT_FOR_MODEL_READY)
            recount_descriptive = len(records) - recount_model_ready
            if summary.get("model_ready_count") != recount_model_ready:
                reasons.append(f"support_summary.model_ready_count {summary.get('model_ready_count')} "
                               f"disagrees with a fresh recount ({recount_model_ready})")
            if summary.get("descriptive_only_count") != recount_descriptive:
                reasons.append(
                    f"support_summary.descriptive_only_count {summary.get('descriptive_only_count')} "
                    f"disagrees with a fresh recount ({recount_descriptive})")
            if summary.get("min_support_for_model_ready") != MIN_SUPPORT_FOR_MODEL_READY:
                reasons.append("support_summary.min_support_for_model_ready does not match the "
                               f"registered threshold ({MIN_SUPPORT_FOR_MODEL_READY})")
    gates["FP04-G-SUPPORT"] = _gate(not reasons, reasons)

    # -- FP04-G-REUSE: measured reuse is correct -- an origin marked reused
    # contributes ZERO fresh engine calls to the resource budget --
    reasons = list(manifest_reasons)
    budget = docs.get("resource_budget.json")
    if ledger is None or budget is None:
        reasons.append("origin_ledger.json or resource_budget.json missing or unreadable")
    else:
        origins = ledger.get("origins", [])
        fresh_trials = sum(len(o.get("trial_records", [])) for o in origins
                           if o.get("reused_from_cache") is None and o.get("wf_ok"))
        reused_origins = [o["origin_cutoff"] for o in origins if o.get("reused_from_cache") is not None]
        if budget.get("engine_calls_search_trials_fresh") != fresh_trials:
            reasons.append(
                f"resource_budget.engine_calls_search_trials_fresh "
                f"{budget.get('engine_calls_search_trials_fresh')} disagrees with a fresh "
                f"recount over non-reused origins ({fresh_trials})")
        if sorted(budget.get("reused_origins", [])) != sorted(reused_origins):
            reasons.append("resource_budget.reused_origins does not match origin_ledger.json's own "
                           "reused_from_cache markers")
    gates["FP04-G-REUSE"] = _gate(not reasons, reasons)

    if missing:
        for gate in gates:
            if gates[gate]["pass"]:
                gates[gate] = _gate(False, gates[gate]["reasons"] +
                                    [f"missing artifacts: {', '.join(missing)}"])
    overall = all(g["pass"] for g in gates.values()) and all(g in gates for g in REQUIRED_GATES)
    return {
        "schema": "regime_lab.fp04_verification.v1",
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
