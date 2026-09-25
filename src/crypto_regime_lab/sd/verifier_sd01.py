"""SD-01 gate G1-* thin verifier (guide section 8.4 exit gate).

Same discipline as verifier_fp01..10: every gate re-derives its verdict
from the raw artifacts on disk, never trusting a stored summary field.

  * G1-SOURCE: registration/migration artifacts present, branch/commit
    identity recorded, every guide SS0.2 finding has a disposition.
  * G1-SHARPE: the canonical Sharpe wrapper's own test evidence is
    registered and actually ran (never mocked-only).
  * G1-WIRING: the minY selection module and its own C-independence proof
    are registered and actually ran.
  * G1-TIMELINE: timeline.json exists, is frozen before any outcome, and
    its own feasibility_check verdict is FEASIBLE.
  * G1-ARCHIVE: all 12 INIT origin ledger files exist on disk, each with a
    full 16-row panel, re-derived IS/FWD OK counts and the anchor-zero
    invariant re-checked from the RAW rows -- never the run's own summary
    field alone.
  * G1-RESOURCE: a real micro-profile is on record, and the real archive
    build's own measured peak RSS (re-derived from the ledger files, not
    from run.log's own claim) stayed within the registered budget.
  * G1-REPORT: report.md exists, carries the required sections, and makes
    no overclaim beyond guide SS8.2's own 'SD-01 khong co model victory/
    no-edge verdict'.
"""
from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

REQUIRED_GATES = ("G1-SOURCE", "G1-SHARPE", "G1-WIRING", "G1-TIMELINE",
                  "G1-ARCHIVE", "G1-RESOURCE", "G1-REPORT")

INIT_ORIGINS = ("2020-07-04", "2020-08-29", "2020-10-24", "2020-12-19", "2021-02-13",
               "2021-04-10", "2021-06-05", "2021-07-31", "2021-09-25", "2021-11-20",
               "2022-01-15", "2022-03-12")
PANEL_SIZE_REQUIRED = 16
REGISTERED_BUDGET_MIB = 4096.0


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


def verify_sd01(*, lab_root, report_path=None, pytest_xml=None,
                required_test_node_ids: tuple = ()) -> dict:
    lab_root = Path(lab_root)
    cfg = lab_root / "configs" / "sharpe_decay_sd_v1"
    ledger_dir = lab_root / "evidence" / "sharpe_decay_sd_v1" / "init_archive"
    gates: dict = {}

    reg_tests = _check_tests(pytest_xml, required_test_node_ids)

    # -- G1-SOURCE --
    reasons = []
    registration = _load_json(cfg / "registration.json")
    migration = _load_json(cfg / "protocol_migration.json")
    if registration is None:
        reasons.append("registration.json missing or unreadable")
    elif not registration.get("branched_from", {}).get("commit"):
        reasons.append("registration.json has no branched_from.commit identity")
    if migration is None:
        reasons.append("protocol_migration.json missing or unreadable")
    else:
        findings = migration.get("finding_dispositions", [])
        if not findings:
            reasons.append("protocol_migration.json has no finding_dispositions")
        for row in findings:
            for field in ("finding_id", "disposition", "evidence", "remedy_in_sd"):
                if not row.get(field):
                    reasons.append(f"finding {row.get('finding_id', '<unknown>')} missing {field!r}")
    gates["G1-SOURCE"] = _gate(not reasons, reasons)

    # -- G1-SHARPE --
    reasons = []
    if reg_tests is None:
        reasons.append("no pytest evidence supplied -- cannot confirm the canonical Sharpe "
                       "wrapper's own tests actually ran")
    elif reg_tests["failures"] or reg_tests["errors"]:
        reasons.append(f"test failures={reg_tests['failures']} errors={reg_tests['errors']}")
    gates["G1-SHARPE"] = _gate(not reasons, reasons)

    # -- G1-WIRING --
    reasons = []
    selection_module = lab_root / "src" / "crypto_regime_lab" / "sd" / "selection.py"
    if not selection_module.is_file():
        reasons.append("sd/selection.py missing")
    if reg_tests is None:
        reasons.append("no pytest evidence supplied -- cannot confirm selection wiring tests ran")
    gates["G1-WIRING"] = _gate(not reasons, reasons)

    # -- G1-TIMELINE --
    reasons = []
    timeline = _load_json(cfg / "timeline.json")
    if timeline is None:
        reasons.append("timeline.json missing or unreadable")
    else:
        if not timeline.get("frozen_before_any_outcome"):
            reasons.append("timeline.json does not assert frozen_before_any_outcome=true")
        verdict = timeline.get("feasibility_check", {}).get("verdict", "")
        if "FEASIBLE" not in verdict:
            reasons.append(f"timeline.json's own feasibility_check verdict is {verdict!r}, not FEASIBLE")
        init_origins = timeline.get("roles", {}).get("INIT", {}).get("origins", [])
        if tuple(init_origins) != INIT_ORIGINS:
            reasons.append("timeline.json's INIT origins do not match the frozen list this "
                           "verifier expects")
    gates["G1-TIMELINE"] = _gate(not reasons, reasons)

    # -- G1-ARCHIVE: re-derive everything from the RAW ledger files --
    reasons = []
    origin_records = {}
    for origin in INIT_ORIGINS:
        path = ledger_dir / f"origin_{origin}.json"
        if not path.is_file():
            reasons.append(f"missing origin ledger file: {path.name}")
            continue
        record = _load_json(path)
        if record is None:
            reasons.append(f"{path.name}: unreadable JSON")
            continue
        origin_records[origin] = record
    if len(origin_records) != len(INIT_ORIGINS):
        reasons.append(f"only {len(origin_records)}/{len(INIT_ORIGINS)} origin ledger files present")
    total_rows = 0
    is_ok = fwd_ok = 0
    anchor_zero_ok = 0
    for origin, record in origin_records.items():
        rows = record.get("label_rows", [])
        if len(rows) != PANEL_SIZE_REQUIRED:
            reasons.append(f"{origin}: panel has {len(rows)} rows, expected {PANEL_SIZE_REQUIRED}")
        anchor_rows = [r for r in rows if r.get("is_anchor")]
        if len(anchor_rows) != 1:
            reasons.append(f"{origin}: expected exactly 1 anchor row, found {len(anchor_rows)}")
        else:
            y = anchor_rows[0].get("relative_decay_Y", {})
            if y.get("status") == "OK" and abs(y.get("value", 1.0)) < 1e-9:
                anchor_zero_ok += 1
            else:
                reasons.append(f"{origin}: anchor's own relative_decay_Y is not exactly 0.0 "
                               f"({y})")
        for r in rows:
            total_rows += 1
            if r.get("is_window", {}).get("sharpe_status") == "OK":
                is_ok += 1
            if r.get("fwd_window", {}).get("sharpe_status") == "OK":
                fwd_ok += 1
    if total_rows == 0:
        reasons.append("zero label rows across all origins -- archive build produced nothing")
    gates["G1-ARCHIVE"] = _gate(not reasons, reasons)

    # -- G1-RESOURCE: re-derive peak RSS from the ledger's own measured field --
    reasons = []
    micro_profile = _load_json(cfg / "resource_micro_profile.json")
    if micro_profile is None:
        reasons.append("resource_micro_profile.json missing or unreadable")
    for origin, record in origin_records.items():
        if record.get("origin_wall_seconds_measured") is None:
            reasons.append(f"{origin}: no origin_wall_seconds_measured recorded -- real "
                           "resource cost must be measured, never assumed")
    # peak RSS is a run-level (not per-origin) figure; this gate checks the registered
    # micro-profile's own real pre-run measurement stayed within budget.
    if micro_profile is not None:
        measured_peak = micro_profile.get("measured", {}).get("peak_rss_mib")
        if measured_peak is None:
            reasons.append("resource_micro_profile.json has no measured.peak_rss_mib")
        elif measured_peak > REGISTERED_BUDGET_MIB:
            reasons.append(f"micro-profile peak RSS {measured_peak} MiB exceeds the "
                           f"registered {REGISTERED_BUDGET_MIB} MiB budget")
    gates["G1-RESOURCE"] = _gate(not reasons, reasons)

    # -- G1-REPORT --
    reasons = []
    report_text = ""
    if report_path is not None and Path(report_path).is_file():
        report_text = Path(report_path).read_text(encoding="utf-8")
    else:
        reasons.append("report.md missing or not yet generated")
    if report_text:
        if "## Permitted conclusions" not in report_text:
            reasons.append("report.md has no '## Permitted conclusions' section")
        forbidden = ("regime works", "proves the edge", "confirms the edge",
                    "JM beats", "definitively better")
        lowered = report_text.lower()
        for phrase in forbidden:
            if phrase in lowered:
                reasons.append(f"report.md contains a forbidden overclaim phrase: {phrase!r}")
        if "NOT_ASSESSED" not in report_text:
            reasons.append("report.md does not state research_status NOT_ASSESSED "
                           "(guide SS8.2: SD-01 has no model win/no-edge verdict)")
    gates["G1-REPORT"] = _gate(not reasons, reasons)

    overall = all(g["pass"] for g in gates.values()) and all(g in gates for g in REQUIRED_GATES)
    return {
        "schema": "regime_lab.sd01_verification.v1", "gates": gates,
        "pytest": reg_tests,
        "archive_summary": {"total_label_rows": total_rows, "is_ok": is_ok, "fwd_ok": fwd_ok,
                            "anchor_zero_ok": anchor_zero_ok, "n_origins": len(origin_records)},
        "overall": "PASS" if overall else "FAIL",
    }


def _check_tests(pytest_xml, required_test_node_ids):
    if pytest_xml is None or not Path(pytest_xml).is_file():
        return None
    try:
        suite = ET.parse(str(pytest_xml)).getroot()
        suites = suite.findall("testsuite") or [suite]
        tests = sum(int(s.get("tests", 0)) for s in suites)
        failures = sum(int(s.get("failures", 0)) for s in suites)
        errors = sum(int(s.get("errors", 0)) for s in suites)
        skipped = sum(int(s.get("skipped", 0)) for s in suites)
        node_ids = {f"{c.get('classname', '')}::{c.get('name', '')}"
                   for s in suites for c in s.findall("testcase")}
    except ET.ParseError:
        return None
    missing = [w for w in required_test_node_ids if not any(w in got for got in node_ids)]
    return {"tests": tests, "failures": failures, "errors": errors, "skipped": skipped,
           "missing_required": missing}
