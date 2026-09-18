"""Guide 13.6 and 13.7 — what may not be claimed, and what must be invalidated.

These two sections are not owned by any L0N.M task, which is the same shape as
the three cross-phase gaps found earlier (compute budgets, the CLI, the ID
taxonomy). A requirement with no owning task is one every phase audit can pass
while it stays undone.
"""

from __future__ import annotations

import json

import pytest

FORBIDDEN = {
    "regime works", "no leakage", "out-of-sample", "better on every dimension",
    "rust parity", "spot-perp carry", "whale netflow", "all four alphas certified",
    "absolutely production-safe",
}


@pytest.fixture(scope="module")
def forbidden(lab_root):
    path = lab_root / "configs" / "forbidden_claims_audit.json"
    if not path.is_file():
        pytest.skip("run scripts/audit_forbidden_claims.py")
    return json.loads(path.read_text())


@pytest.fixture(scope="module")
def corrections(lab_root):
    path = lab_root / "configs" / "correction_ledger.json"
    if not path.is_file():
        pytest.skip("run scripts/build_correction_ledger.py")
    return json.loads(path.read_text())


# --- guide 13.6 -----------------------------------------------------------


def test_all_nine_forbidden_claims_are_checked(forbidden):
    assert {c["claim"] for c in forbidden["checks"]} == FORBIDDEN
    assert forbidden["status"] == "NO_FORBIDDEN_CLAIM_IS_SUPPORTED"
    assert forbidden["unsupported_claims"] == []


def test_each_check_names_the_evidence_the_claim_would_need(forbidden):
    """Otherwise the audit records a verdict without saying what it verified."""
    for check in forbidden["checks"]:
        assert check.get("would_need"), check["claim"]
        assert check["passed"] is True, check


def test_the_forbidden_claim_audit_is_structural_not_lexical(forbidden):
    """Two earlier attempts in this lab grepped prose and flagged their own text."""
    assert "STRUCTURALLY" in forbidden["method"]
    assert "lexical scan cannot tell a claim from a denial" in forbidden["method"]


def test_the_negative_findings_the_lab_actually_reports_are_preserved(forbidden):
    """The strongest evidence that no edge is being claimed is the failures kept."""
    regime = next(c for c in forbidden["checks"] if c["claim"] == "regime works")
    assert regime["group_ablation_ran"] is True
    assert regime["group_ablation_improved_out_of_fold"] is False, (
        "the guide 8.3 ablation FAILED and that result must survive")
    separation = next(c for c in forbidden["checks"]
                      if c["claim"] == "better on every dimension")
    assert separation["conclusion_level"] != "NET_PARAMETER_SELECTION_EDGE"
    certified = next(c for c in forbidden["checks"]
                     if c["claim"] == "all four alphas certified")
    assert certified["blocked"], "A-HASH's blocker must not have quietly become READY"


def test_production_safety_rests_on_a_measured_refusal(forbidden):
    """Path naming is not isolation; the guide names this claim explicitly."""
    check = next(c for c in forbidden["checks"] if c["claim"] == "absolutely production-safe")
    assert check["os_isolation_available"] is True
    assert check["fake_protected_write_refused"] is True
    assert check["refusal_errno"] == 30, "EROFS: the kernel refused, not a path guard"
    assert check["market_execution_allowed"] is False
    assert check["protected_roots_measured_read_only"], "no protected root was measured"


# --- guide 13.7 -----------------------------------------------------------


def test_every_correction_is_traceable_to_evidence(corrections):
    assert corrections["status"] == "EVERY_CORRECTION_TRACEABLE"
    assert corrections["unverifiable"] == []
    assert corrections["defects_total"] >= 12


def test_a_numeric_correction_names_the_run_it_superseded(corrections):
    """Prose in a report cannot be checked; a run id can."""
    numeric = [d for d in corrections["defects"] if d["numeric_change"]]
    assert numeric, "no correction is backed by a value change in the evidence tree"
    for defect in numeric:
        assert defect["verification"] == "DERIVED_FROM_EVIDENCE"
        assert len(defect["numeric_change"]) == 1, (
            f"{defect['id']} matches {len(defect['numeric_change'])} transitions; its signature "
            "does not identify one defect")
        change = defect["numeric_change"][0]
        assert change["superseded_run"].startswith("run-")
        assert change["superseding_run"].startswith("run-")
        assert change["superseded_run"] < change["superseding_run"], (
            "the replacement must come from a LATER run, not a nicer one")


def test_the_worst_published_number_is_recorded_as_superseded(corrections):
    """LAB-07 first reported +2.11%; the tape defect made it wrong.

    That number reached a report. The ledger has to say so, and point at the run
    that produced it, or the correction is only a claim about a correction.
    """
    tape = next(d for d in corrections["defects"] if d["id"] == "COR-01")
    change = tape["numeric_change"][0]
    assert change["from"]["total_return"] == pytest.approx(0.021052071167515063)
    assert change["to"]["total_return"] == pytest.approx(0.0017171592602391872)
    assert change["from"]["fills"] == 18 and change["to"]["fills"] == 150
    assert change["from"]["entries"] == change["to"]["entries"], (
        "the signature is that fills moved while entries did not")


def test_every_correction_names_the_test_that_now_guards_it(corrections):
    for defect in corrections["defects"]:
        assert defect["guarded_by"].startswith("tests/"), defect["id"]
        assert "::" in defect["guarded_by"], defect["id"]


def test_the_evidence_tree_is_append_only(corrections, lab_root):
    """The ledger is only checkable because the superseded run still exists."""
    assert corrections["evidence_is_append_only"] is True
    for defect in corrections["defects"]:
        for change in defect["numeric_change"] or []:
            for run_id in (change["superseded_run"], change["superseding_run"]):
                run = lab_root / "evidence" / "crypto_regime_timeedge_v2" / run_id
                assert run.is_dir(), f"{run_id} is referenced but no longer on disk"


# --- guide 11.5: artifact discipline --------------------------------------


def _strict(text: str):
    """Parse rejecting NaN/Infinity literals, which are not valid JSON."""
    return json.loads(text, parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))


def _non_finite(node, path=""):
    import math

    bad = []
    if isinstance(node, float):
        if math.isnan(node) or math.isinf(node):
            bad.append(path)
    elif isinstance(node, dict):
        for key, value in node.items():
            bad += _non_finite(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            bad += _non_finite(value, f"{path}[{index}]")
    return bad


def test_every_config_artifact_is_strict_json_and_versioned(lab_root):
    """Guide 11.5: strict JSON with allow_nan=False, and a schema version on each.

    A NaN written into an artifact is not merely ugly — it is invalid JSON that
    some parsers accept and others reject, so an artifact carrying one is read
    differently depending on who reads it.
    """
    files = sorted((lab_root / "configs").rglob("*.json"))
    assert len(files) > 40, "the config tree looks truncated; this would pass trivially"
    for path in files:
        try:
            document = _strict(path.read_text())
        except ValueError as exc:
            pytest.fail(f"{path.name} contains a NaN/Infinity literal: {exc}")
        assert _non_finite(document) == [], f"{path.name} carries a non-finite float"
        if isinstance(document, dict):
            assert "schema" in document, f"{path.name} has no schema version"


def test_every_evidence_artifact_is_strict_json(lab_root):
    files = sorted((lab_root / "evidence").rglob("*.json"))
    assert len(files) > 100, "the evidence tree looks truncated"
    for path in files:
        try:
            _strict(path.read_text())
        except ValueError as exc:
            pytest.fail(f"{path.relative_to(lab_root)} is not strict JSON: {exc}")


def test_the_writer_never_drops_a_record(lab_root):
    """Guide 11.5: a full writer queue backpressures or fails — it does not drop."""
    from crypto_regime_lab.evidence.audit_queue import (
        AuditQueueOverflow,
        BoundedAuditQueue,
        QueueFullPolicy,
    )

    written: list[dict] = []
    queue = BoundedAuditQueue(sink=lambda rows: written.extend(rows) or len(rows),
                              maxsize=2, policy=QueueFullPolicy.EXPLICIT_FAIL)
    queue.offer({"row": 1})
    queue.offer({"row": 2})
    with pytest.raises(AuditQueueOverflow):
        queue.offer({"row": 3})
    stats = queue.stats()
    assert stats["dropped"] == 0, "a dropped record is a silently shorter run"
    assert stats["accepted"] == 2 and stats["pending"] == 2, (
        "the two accepted rows must still be queued, not lost to the overflow")


# --- cross-phase: do the evidence pointers still resolve? (COR-15) -----------
def test_no_completed_phase_has_a_broken_evidence_pointer(lab_root):
    """Every phase audit's evidence must still point at something that exists.

    An audit that counts the PRESENCE of an evidence string cannot tell a live
    pointer from one whose field was renamed or whose test was deleted — and
    every phase report quotes its audit. `scripts/audit_evidence_pointers.py`
    resolves them; this test is the gate.
    """
    path = lab_root / "configs" / "evidence_pointer_audit.json"
    if not path.is_file():
        pytest.skip("run scripts/audit_evidence_pointers.py")
    audit = json.loads(path.read_text())
    completed = [f"lab0{n}_task_audit.json" for n in range(1, 9)]
    if (lab_root / "configs" / "lab09_claim_report.json").is_file():
        completed.append("lab09_task_audit.json")

    broken = [b for b in audit["broken"] if b["phase"] in completed]
    assert broken == [], (
        "these evidence pointers no longer resolve: "
        + "; ".join(f"{b['phase']}:{b['clause_id']} {b['fragment']} — {b.get('detail')}"
                    for b in broken))

    # and the audit has to have had something to check
    checked = [name for name in completed
               if audit["per_phase"].get(name, {}).get("status") == "CHECKED"]
    assert len(checked) >= 8, f"only {len(checked)} phase audits were resolved"
    resolved = sum(audit["per_phase"][name]["counts"].get("RESOLVED", 0) for name in checked)
    assert resolved > 300, (
        f"only {resolved} pointers resolved across {len(checked)} phases; a sweep that "
        "resolves almost nothing passes for the wrong reason")


def test_the_pointer_audit_reports_prose_separately_from_evidence(lab_root):
    """A sentence is not a locator, and the two are never merged.

    LAB-05's audit is 16 prose clauses to 31 resolvable pointers; LAB-07's is 3
    to 72. That gap is a real difference in how checkable those phases are, and
    it is only visible if prose is counted on its own.
    """
    path = lab_root / "configs" / "evidence_pointer_audit.json"
    if not path.is_file():
        pytest.skip("run scripts/audit_evidence_pointers.py")
    audit = json.loads(path.read_text())
    assert "PROSE_ONLY" in audit["classification"]
    assert "AMBIGUOUS_SHORTHAND" in audit["classification"]
    prose_bearing = [name for name, rec in audit["per_phase"].items()
                     if rec.get("status") == "CHECKED"
                     and rec["counts"].get("PROSE_ONLY", 0) > 0]
    assert prose_bearing, "no phase reported a prose-only clause, which is implausible"
