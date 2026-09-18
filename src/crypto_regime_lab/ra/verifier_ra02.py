"""Thin RA-02 verifier (RA-GUIDE-1.0 §6, gates G02-SEM/NUM/COUNT/LEDGER).

Same discipline as the RA-01 verifier: required artifacts exist, hash-match
their manifest, mandatory tests really ran (parsed from the junit XML), and
each gate has a machine-checkable criterion fed by actual artifacts — never
by self-declared status strings. A JSON artifact reporting BLOCKED cannot
ride a PASS. Exit code 0 alone is never evidence.
"""

from __future__ import annotations

from pathlib import Path

from .verifier import _gate, _load_json, _sha256

REQUIRED_GATES = ("G02-SEM", "G02-NUM", "G02-COUNT", "G02-LEDGER")
REQUIRED_ARTIFACTS = (
    "cache_contract.json",
    "dependency_manifest.json",
    "cache_test_matrix.json",
    "actual_cross_run_reuse.json",
    "resume_parity.json",
    "counters.json",
    "resource_envelope.json",
    "phase_gate.json",
    "phase_manifest.json",
    "report.md",
    "handoff.md",
)
CASE_IDS = tuple(f"C{i:02d}" for i in range(1, 11))
COUNTER_FIELDS = ("requested_trials", "unique_evaluations", "cache_hits",
                  "cache_misses", "new_engine_runs", "visited_bars",
                  "unique_evaluation_requests")
GATE_SCHEMA = "regime_lab.ra_phase_gate.v1"
# Verdict-bearing files are finalized after the verifier has seen them (the
# receipt carries the verdict); they are structurally validated at verify
# time but stay outside the content-hash manifest. Their integrity rides the
# recorded final verdict plus the scoped commit — the same discipline RA-01
# uses for report.md/handoff.md.
VERDICT_BEARING = ("phase_manifest.json", "phase_gate.json",
                   "report.md", "handoff.md")


def _nonneg_int(value) -> bool:
    return (isinstance(value, int) and not isinstance(value, bool)
            and value >= 0)


def verify_ra02(run_dir: str | Path, *, pytest_xml: str | Path | None,
                protected_status_after: str) -> dict:
    """Verify one RA-02 run directory. Returns the gate matrix (never raises)."""
    root = Path(run_dir)
    gates: dict[str, dict] = {}

    missing = [name for name in REQUIRED_ARTIFACTS if not (root / name).is_file()]
    docs: dict[str, dict | None] = {}
    for name in REQUIRED_ARTIFACTS:
        if name.endswith(".json") and (root / name).is_file():
            docs[name] = _load_json(root / name, [])

    # -- G02-SEM: all ten cases ran and passed; cross-run reuse is real -------
    reasons: list[str] = []
    if missing:
        reasons.append(f"missing artifacts: {missing}")
    node_ids: set[str] = set()
    junit_info: dict | None = None
    if pytest_xml is None or not Path(pytest_xml).is_file():
        reasons.append("pytest report missing: no test evidence, cannot PASS")
    else:
        try:
            import xml.etree.ElementTree as ET

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
            junit_info = {"tests": tests, "failures": failures,
                          "errors": errors, "skipped": skipped}
        except Exception as exc:
            reasons.append(f"pytest report unparseable: {exc}")
        if junit_info is not None:
            if junit_info["tests"] == 0:
                reasons.append("no-tests-collected cannot PASS")
            if junit_info["failures"] or junit_info["errors"]:
                reasons.append(f"test failures={junit_info['failures']} "
                               f"errors={junit_info['errors']} cannot PASS")
            if junit_info["skipped"]:
                reasons.append("skipped mandatory tests cannot PASS")

    matrix = docs.get("cache_test_matrix.json")
    if matrix is None:
        reasons.append("cache_test_matrix.json missing or unreadable")
    else:
        cases = {row.get("case_id"): row for row in matrix.get("cases", [])}
        for case_id in CASE_IDS:
            row = cases.get(case_id)
            if row is None:
                reasons.append(f"{case_id} missing from the test matrix")
                continue
            if not row.get("test_node_ids"):
                reasons.append(f"{case_id} has no registered test")
                continue
            for wanted in row["test_node_ids"]:
                if not any(wanted in got for got in node_ids):
                    reasons.append(f"{case_id} test missing from the junit report: {wanted}")
                    break
            if row.get("passed") is not True:
                reasons.append(f"{case_id} not recorded as passed")
    reuse = docs.get("actual_cross_run_reuse.json")
    if reuse is None:
        reasons.append("actual_cross_run_reuse.json missing or unreadable")
    else:
        first = reuse.get("first_computation") or {}
        second = reuse.get("cross_run_reuse") or {}
        if not first.get("producer") or not second.get("producer"):
            reasons.append("cross-run reuse receipt missing producer ids")
        elif first["producer"] == second["producer"]:
            reasons.append("cross-run reuse used the same producer run id")
        if first.get("engine_runs") != 1 or not first.get("engine_wall_seconds"):
            reasons.append("first computation did not record a real engine run")
        if second.get("status") != "HIT" or second.get("new_engine_runs") != 0:
            reasons.append("second run was not a pure cache HIT (new_engine_runs must be 0)")
        if not first.get("payload_sha256") or first.get("payload_sha256") != second.get("payload_sha256"):
            reasons.append("reused payload digest missing or differs from the producer's")
        equivalence = reuse.get("equivalence") or {}
        if equivalence.get("method") not in ("canonical-byte-equal", "frozen-tolerance") \
                or equivalence.get("passed") is not True:
            reasons.append("numeric equivalence not proven by a frozen method")
        if not reuse.get("provenance_excluded_from_key"):
            reasons.append("provenance fields excluded from the key are not declared")
        causality = reuse.get("causality_fields") or []
        for field in ("physical_compute_at", "simulated_cutoff", "simulated_ready_at"):
            if field not in causality:
                reasons.append(f"causality field {field} not captured")
    gates["G02-SEM"] = _gate(not reasons, reasons)
    if junit_info is not None:
        gates["G02-SEM"]["tests"] = junit_info

    # -- G02-NUM: outputs equal within the frozen tolerance; provenance split -
    reasons = []
    reuse = docs.get("actual_cross_run_reuse.json") or {}
    equivalence = reuse.get("equivalence") or {}
    if equivalence.get("method") not in ("canonical-byte-equal", "frozen-tolerance"):
        reasons.append("equivalence method is not a frozen, declared tolerance")
    if equivalence.get("passed") is not True:
        reasons.append("numeric equivalence did not pass")
    if equivalence.get("method") == "frozen-tolerance" and not equivalence.get("tolerance_frozen_at"):
        reasons.append("frozen-tolerance without a freeze reference is not allowed")
    if not reuse.get("provenance_excluded_from_key"):
        reasons.append("provenance/financial key separation not recorded")
    resume = docs.get("resume_parity.json")
    if resume is None:
        reasons.append("resume_parity.json missing or unreadable")
    else:
        if resume.get("parity_passed") is not True:
            reasons.append("study resume parity did not pass")
        if not resume.get("naive_restart_differs"):
            reasons.append("red control missing: a naive restart must differ "
                           "or the parity test proves nothing")
    gates["G02-NUM"] = _gate(not reasons, reasons)

    # -- G02-COUNT: counters complete and arithmetically consistent -----------
    reasons = []
    counters = docs.get("counters.json")
    if counters is None:
        reasons.append("counters.json missing or unreadable")
    else:
        for field in COUNTER_FIELDS:
            if not _nonneg_int(counters.get(field)):
                reasons.append(f"counter {field} missing or not a non-negative integer")
        if counters.get("cache_hit_bars_counted_as_executed") is not False:
            reasons.append("cache-hit bars must never be counted as executed bars")
        values = {f: counters.get(f) for f in COUNTER_FIELDS}
        if all(_nonneg_int(v) for v in values.values()):
            if values["cache_hits"] + values["cache_misses"] != values["unique_evaluation_requests"]:
                reasons.append("cache_hits + cache_misses != unique_evaluation_requests")
            if values["cache_misses"] != values["unique_evaluations"]:
                reasons.append("cache_misses != unique_evaluations: one miss must "
                               "compute exactly one unique semantic key")
            if values["new_engine_runs"] > values["cache_misses"]:
                reasons.append("new_engine_runs exceeds cache_misses: a hit ran the engine")
            if values["requested_trials"] < values["unique_evaluation_requests"]:
                reasons.append("requested_trials < evaluation requests")
        if not counters.get("scope"):
            reasons.append("counters must state the scope they were measured over")
    gates["G02-COUNT"] = _gate(not reasons, reasons)

    # -- G02-LEDGER: old attempts/costs intact; no reset; protected unchanged -
    reasons = []
    envelope = docs.get("resource_envelope.json")
    if envelope is None:
        reasons.append("resource_envelope.json missing or unreadable")
    else:
        before = envelope.get("ledger_before") or {}
        after = envelope.get("ledger_after") or {}
        for key in ("spent", "attempts", "budget"):
            if before.get(key) is None or after.get(key) is None:
                reasons.append(f"ledger snapshot missing {key}")
            elif before.get(key) != after.get(key):
                reasons.append(
                    f"ledger {key} changed during the phase: "
                    f"{before.get(key)} -> {after.get(key)}")
        if not envelope.get("phase_wall_cap_s"):
            reasons.append("phase sub-envelope wall cap missing")
        measured = envelope.get("phase_measured_wall_s")
        if not isinstance(measured, (int, float)) or isinstance(measured, bool) or measured < 0:
            reasons.append("measured phase wall missing")
        elif measured > float(envelope.get("phase_wall_cap_s") or 0):
            reasons.append("phase exceeded its frozen sub-envelope")
    if protected_status_after.strip():
        reasons.append("protected tree changed by the phase; delta: "
                       + protected_status_after.strip()[:500])
    gate_doc = docs.get("phase_gate.json")
    if gate_doc is None:
        reasons.append("phase_gate.json missing or unreadable")
    else:
        if gate_doc.get("schema") != GATE_SCHEMA:
            reasons.append(f"phase gate schema must be {GATE_SCHEMA}")
        if gate_doc.get("phase_id") != "RA-02":
            reasons.append("phase gate receipt belongs to another phase")
        if gate_doc.get("owner_review", {}).get("status") != "PENDING":
            reasons.append("owner review must stay PENDING until a real decision")
        if gate_doc.get("can_start_next_phase") is not False:
            reasons.append("can_start_next_phase must be false until owner approval")
    gates["G02-LEDGER"] = _gate(not reasons, reasons)

    # -- manifest hashes (shared discipline with RA-01) ------------------------
    reasons = []
    manifest = docs.get("phase_manifest.json")
    if manifest is None:
        reasons.append("no manifest to check hashes against")
    else:
        for entry in manifest.get("artifacts", []):
            rel = entry.get("relpath", "")
            want = entry.get("sha256", "")
            target = root / rel
            if not target.is_file():
                reasons.append(f"manifest lists missing file: {rel}")
            elif want and _sha256(target) != want:
                reasons.append(f"hash mismatch (tampered or stale): {rel}")
        for name in REQUIRED_ARTIFACTS:
            if name in VERDICT_BEARING:
                continue
            if name.endswith(".json") and name != "phase_manifest.json" and not any(
                    e.get("relpath") == name for e in manifest.get("artifacts", [])):
                reasons.append(f"required artifact not indexed in manifest: {name}")
    gates["G02-MANIFEST"] = _gate(not reasons, reasons)

    for name in REQUIRED_ARTIFACTS:
        doc = docs.get(name)
        if isinstance(doc, dict) and doc.get("status") == "BLOCKED":
            gates["G02-SEM"] = _gate(False, gates["G02-SEM"]["reasons"]
                                     + [f"{name} reports BLOCKED and cannot ride a PASS"])

    overall = all(g["pass"] for g in gates.values()) and all(
        g in gates for g in REQUIRED_GATES + ("G02-MANIFEST",))
    return {
        "schema": "crypto_regime_lab.ra02_verification.v1",
        "run_dir": str(root),
        "gates": gates,
        "overall": "PASS" if overall else "FAIL",
    }
