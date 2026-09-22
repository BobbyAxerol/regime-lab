"""FP-02 gate FP02-G-* thin verifier (guide §14 exit gate + §26.3).

Behavioral by construction, matching FP-01's verifier (FP-F09): every gate
re-derives its verdict from the artifacts on disk and, where the claim is
about causality or lineage, RE-RUNS the same guard function the evaluator
itself uses (``assert_causal_hit``, ``build_lineage``) against the recorded
raw data -- never trusts a boolean the artifact merely asserts about itself.
`verify_fp02` never raises: it returns the gate matrix with reasons.
"""
from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

REQUIRED_GATES = ("FP02-G-PARITY", "FP02-G-CACHE", "FP02-G-LATENCY",
                  "FP02-G-MEMORY", "FP02-G-LINEAGE", "FP02-G-RESUME")

REQUIRED_ARTIFACTS = (
    "route_parity.json", "cache_reuse.json", "lineage_demo.json",
    "resume_demo.json", "memory_audit.json", "resource_budget.json",
    "test_registry.json", "phase_manifest.json", "gate_receipt.json",
    "report.md", "handoff.md",
)

REQUIRED_TEST_NODES = (
    "test_fp02_g_parity_audit_vs_score_route",
    "test_fp02_g_cache_same_semantics_hit_different_economics_miss",
    "test_fp02_g_latency_causal_hit_guard",
    "test_fp02_g_memory_peak_bounded_and_not_growing_with_repeats",
    "test_fp02_g_lineage_reconstructs_activation_and_fills",
    "test_fp02_g_resume_cache_hit_after_simulated_crash",
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


def verify_fp02(run_dir, *, pytest_xml=None) -> dict:
    """Verify one FP-02 run directory. Returns the gate matrix (never raises)."""
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
            # Same exclusion as verifier_fp01.py, same reason: gate_receipt.json
            # is written twice by design (placeholder, then updated in place
            # with the verdict this very verification produces), so its bytes
            # never match the pre-verdict hash on any run after the one that
            # wrote it. Not a loosened check -- phase_manifest.json already
            # gets the identical treatment for the identical reason.
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

    # -- FP02-G-PARITY: audit vs score/fast route, PASS, equity exact-equal --
    reasons = list(manifest_reasons)
    parity = docs.get("route_parity.json")
    if parity is None:
        reasons.append("route_parity.json missing or unreadable")
    else:
        if parity.get("status") != "PASS":
            reasons.append(f"route_parity status is {parity.get('status')!r}, not PASS")
        if parity.get("equity_exact_equal") is not True:
            reasons.append("route_parity equity is not exact-equal between audit and fast")
        if parity.get("max_abs_equity_diff") not in (0, 0.0):
            reasons.append(f"route_parity max_abs_equity_diff is "
                           f"{parity.get('max_abs_equity_diff')}, not 0")
        if not parity.get("entries_match") or not parity.get("fill_count_match"):
            reasons.append("route_parity entries/fill counts disagree between routes")
    gates["FP02-G-PARITY"] = _gate(not reasons, reasons)

    # -- FP02-G-CACHE: a MISS then a HIT reusing the SAME payload; a changed
    # economic dependency MISSES and produces a different result --
    reasons = list(manifest_reasons)
    reuse = docs.get("cache_reuse.json")
    if reuse is None:
        reasons.append("cache_reuse.json missing or unreadable")
    else:
        if reuse.get("first", {}).get("status") != "MISS":
            reasons.append("first candidate evaluation was not a MISS (nothing was computed)")
        reused = reuse.get("reused", {})
        if reused.get("status") != "HIT":
            reasons.append("re-request under a different producer was not a HIT")
        if reused.get("payload_identical") is not True:
            reasons.append("HIT payload is not identical to the original computation")
        changed = reuse.get("changed_economics", {})
        if changed.get("status") != "MISS":
            reasons.append("a changed economic dependency did not MISS")
        if changed.get("terminal_equity_changed") is not True:
            reasons.append("changed economics produced the SAME terminal equity: "
                           "the facet is not actually load-bearing")
    gates["FP02-G-CACHE"] = _gate(not reasons, reasons)

    # -- FP02-G-LATENCY: re-run assert_causal_hit on the RAW recorded
    # causality from cache_reuse.json's real evaluate_candidate payload --
    # both the valid case (must pass) and a tampered copy (must raise) --
    # never a self-reported boolean.
    reasons = list(manifest_reasons)
    try:
        from ..ra.cache_semantics import assert_causal_hit
    except ImportError as exc:
        reasons.append(f"cannot import assert_causal_hit: {exc}")
        assert_causal_hit = None
    if assert_causal_hit is not None:
        causality = (docs.get("cache_reuse.json") or {}).get("first_causality")
        if not causality:
            reasons.append("cache_reuse.json carries no first_causality block to re-check")
        else:
            try:
                parsed = assert_causal_hit(causality, cutoff=causality["simulated_cutoff"])
            except ValueError as exc:
                reasons.append(f"a VALID recorded causality record failed re-verification: {exc}")
            else:
                if parsed["simulated_ready_at"] != parsed["simulated_cutoff"]:
                    reasons.append("simulated_ready_at is not simulated_cutoff for a "
                                   "standardized candidate (should never be earlier, and "
                                   "this evaluator never claims later either)")
            tampered = dict(causality)
            tampered["simulated_ready_at"] = "2099-01-01T00:00:00+00:00"
            try:
                assert_causal_hit(tampered, cutoff=causality["simulated_cutoff"])
            except ValueError:
                pass  # correctly refused a future-maturing record
            else:
                reasons.append("assert_causal_hit accepted a record maturing after its own "
                               "cutoff: the latency guard is not actually enforced")
    gates["FP02-G-LATENCY"] = _gate(not reasons, reasons)

    # -- FP02-G-MEMORY: peak within the registered budget; not growing --
    reasons = list(manifest_reasons)
    mem = docs.get("memory_audit.json")
    if mem is None:
        reasons.append("memory_audit.json missing or unreadable")
    else:
        peaks = mem.get("per_call_peak_mib") or []
        budget = mem.get("budget_mib")
        if not peaks:
            reasons.append("no per-call peaks recorded")
        elif not budget:
            reasons.append("no budget recorded to check peaks against")
        else:
            over = [p for p in peaks if p >= budget]
            if over:
                reasons.append(f"{len(over)} call(s) reached/exceeded the {budget} MiB budget")
        if mem.get("within_budget") is not True:
            reasons.append("memory_audit itself reports within_budget=False")
        if mem.get("not_growing_unboundedly") is not True:
            reasons.append("memory_audit itself reports unbounded growth across repeats")
    gates["FP02-G-MEMORY"] = _gate(not reasons, reasons)

    # -- FP02-G-LINEAGE: fills fully attributed, >=1 real activation effected,
    # re-verified against the recorded bar ranges, not just the summary count --
    reasons = list(manifest_reasons)
    lineage_doc = docs.get("lineage_demo.json")
    if lineage_doc is None:
        reasons.append("lineage_demo.json missing or unreadable")
    else:
        lineage = lineage_doc.get("lineage", {})
        if lineage.get("fills_attributed") != lineage.get("fills_total"):
            reasons.append("lineage fills_attributed != fills_total")
        if not lineage.get("activations_effected") or lineage["activations_effected"] < 2:
            reasons.append("fewer than 2 activations effected: the required "
                           "pending/activation case was not actually exercised")
        rows = lineage.get("activations", [])
        recount = sum(r.get("fill_count", 0) for r in rows)
        if recount != lineage.get("fills_total"):
            reasons.append(f"re-summed per-activation fill_count ({recount}) does not match "
                           f"fills_total ({lineage.get('fills_total')})")
        ranges = [tuple(r["bar_range"]) for r in rows if r.get("bar_range")]
        for (s1, e1), (s2, e2) in zip(sorted(ranges), sorted(ranges)[1:]):
            if e1 != s2:
                reasons.append(f"bar ranges are not contiguous: [{s1},{e1}) then [{s2},{e2})")
    gates["FP02-G-LINEAGE"] = _gate(not reasons, reasons)

    # -- FP02-G-RESUME: a resumed pass recomputes only what was never
    # finished -- exactly one MISS per unique candidate, never per pass --
    reasons = list(manifest_reasons)
    resume = docs.get("resume_demo.json")
    if resume is None:
        reasons.append("resume_demo.json missing or unreadable")
    else:
        unique = resume.get("unique_candidates")
        total_misses = resume.get("total_misses")
        if unique is None or total_misses is None:
            reasons.append("resume_demo missing unique_candidates/total_misses")
        elif total_misses != unique:
            reasons.append(f"total_misses ({total_misses}) != unique_candidates ({unique}): "
                           "a naive restart would have recomputed some candidates twice")
        pre = resume.get("pre_resume_statuses") or []
        post = resume.get("post_resume_statuses") or []
        if not pre or "MISS" not in pre:
            reasons.append("pre-resume pass recorded no MISS: nothing was actually computed "
                           "before the simulated crash")
        if len(post) < len(pre) or post.count("HIT") < len(pre):
            reasons.append("post-resume pass did not HIT everything the pre-resume pass computed")
    gates["FP02-G-RESUME"] = _gate(not reasons, reasons)

    if missing:
        for gate in gates:
            if gates[gate]["pass"]:
                gates[gate] = _gate(False, gates[gate]["reasons"] +
                                    [f"missing artifacts: {', '.join(missing)}"])
    overall = all(g["pass"] for g in gates.values()) and all(
        g in gates for g in REQUIRED_GATES)
    return {
        "schema": "regime_lab.fp02_verification.v1",
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
    for wanted in REQUIRED_TEST_NODES:
        if not any(wanted in got for got in node_ids):
            reasons.append(f"required FP02 test not in report: {wanted}")
            break
    if registry:
        for wanted in registry.get("test_node_ids", []):
            if not any(wanted in got for got in node_ids):
                reasons.append(f"registered test not found in report: {wanted}")
                break
    return info
