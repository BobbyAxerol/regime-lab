"""RF-05 acceptance — frozen claims, recomputation, integrity and handoff guards.

Each guard has a denominator and can go red:

* every freeze-manifest component hash equals the committed file (no
  self-referential entry and no hash recorded without a file). A component that
  changed after the freeze passes only when a later REGISTERED study declares
  the exact old/new hashes in its OWN declaration artifact, tied to its entry in
  the follow-up registration; an undeclared drift, a declaration naming another
  study's id, a broken supersession chain, or a drift beyond the registered
  ceiling all fail;
* every evaluated CI carries a positive common-date denominator and the frozen
  MDE 0.0371 bps/day, and the Holm family is exactly {TIMING, BUDGET_AWARE};
* no contrast is ``POSITIVE_WITHIN_SCOPE`` without a CI lower bound above the
  MDE and a Holm-adjusted p below 0.05, and every status is A16-legal;
* the artifact-integrity checks cover RF-01..RF-05 and pass, including the
  12-section report pair;
* A-VWAP/A-HASH stay ``BLOCKED_CAPABILITY`` with null metrics and reasons, and
  the A-SC endpoint route deviation stays ``NOT_EVALUABLE``;
* the cost stress keeps the registered 1x/1.5x/2x levels with the 1x harness
  control and never claims an engine rerun.
"""

from __future__ import annotations

import json
import math
import re

from crypto_regime_lab.evidence.claim_gate import statistical_status_allowed
from crypto_regime_lab.safety.paths import sha256_file

RF05 = ("evidence", "corrective_mode4_v3", "RF-05")
RF04 = ("evidence", "corrective_mode4_v3", "RF-04")
PRE_RF04 = ("evidence", "corrective_mode4_v3", "pre-RF04-clearing")
PHASES = ("RF-01", "RF-02", "RF-03", "RF-04", "RF-05")
MDE_BPS = 0.03709428129829986
BLOCKED_ALPHAS = {"A-VWAP", "A-HASH"}
POSITIVE = "POSITIVE_WITHIN_SCOPE"


def _load(lab_root, parts: tuple, name: str) -> dict:
    return json.loads(lab_root.joinpath(*parts).joinpath(name).read_text(encoding="utf-8"))


# Registered follow-up studies that may declare a frozen RF-05 component
# repaired, in registration order, as (study_id, artifact path). A source is
# trusted for its OWN study_id only: the loader asserts the row's
# `registered_study` equals the source's id AND that the row's
# `registration_ref` resolves to that id inside the follow-up registration, so a
# declaration cannot be attached to a study that never registered it.
_SUPERSESSION_SOURCES = (
    ("FUP-01", ("evidence", "corrective_mode4_v3", "FUP-01", "native_event_capability.json")),
    ("FUP-04", ("evidence", "corrective_mode4_v3", "FUP-04", "report_level_memory_repair.json")),
)
# The ceiling on how many frozen components of a manifest may carry a
# supersession is DECLARED in a registered artifact (FUP-04, which raised it from
# the original hardcoded 1 so its own second repair could be admitted). The
# ceiling can therefore only move by registration, never by editing a guard.
_CEILING_SOURCE = ("evidence", "corrective_mode4_v3", "FUP-04", "report_level_memory_repair.json")


def _registration_ref_study(lab_root, ref: str) -> str:
    """Resolve `<registration file>#/studies/N` to the study id registered there."""
    path_part, _, pointer = ref.partition("#")
    assert pointer.startswith("/studies/"), f"unexpected registration_ref {ref!r}"
    payload = json.loads(lab_root.joinpath(path_part).read_text(encoding="utf-8"))
    return payload["studies"][int(pointer.split("/")[-1])]["id"]


def _declared_ceiling(lab_root, manifest_name: str) -> int:
    payload = json.loads(lab_root.joinpath(*_CEILING_SOURCE).read_text(encoding="utf-8"))
    ceilings = payload["frozen_supersession_ceilings"]
    assert manifest_name in ceilings, (
        f"{manifest_name} has no registered supersession ceiling: a drift there "
        "cannot be accepted without a registered study declaring one")
    return int(ceilings[manifest_name])


def _declared_supersessions(lab_root, manifest_name: str, prior_hashes: dict) -> dict:
    """Frozen components a registered follow-up declares it has repaired.

    The freeze and reproducibility manifests stay honest RF-05 records: a file
    whose committed hash no longer matches may pass only when a later REGISTERED
    study declares the exact old and new hashes in its OWN artifact. An
    undeclared drift still fails, and so does a declaration that names another
    study's id or a prior hash other than the frozen one.

    When two registered studies declare the same path (a second repair of an
    already-repaired component) the later source wins, and the chain is checked
    rather than assumed: the later row must name the earlier row's current hash
    as the one it supersedes. A registered study that has not produced its
    declaration artifact yet simply declares nothing.
    """
    declared: dict = {}
    for study_id, parts in _SUPERSESSION_SOURCES:
        source = lab_root.joinpath(*parts)
        if not source.is_file():
            continue
        payload = json.loads(source.read_text(encoding="utf-8"))
        for row in payload.get("frozen_component_supersessions", []):
            if not row["frozen_by"].endswith(manifest_name):
                continue
            assert row["registered_study"] == study_id, (
                f"{row['path']}: {source.name} declares for "
                f"{row['registered_study']!r} but is {study_id!r}'s artifact")
            assert _registration_ref_study(lab_root, row["registration_ref"]) == study_id, (
                f"{row['path']}: registration_ref does not resolve to {study_id!r}")
            assert prior_hashes.get(row["path"]) == row["frozen_sha256"], (
                f"{row['path']}: the declaration does not match the RF-05 prior hash")
            assert row["rf05_results_recomputed"] is False, row
            previous = declared.get(row["path"])
            if previous is None:
                assert not row.get("supersedes_previous_current_sha256"), (
                    f"{row['path']}: names a superseded declaration no source holds")
            else:
                assert (row.get("supersedes_previous_current_sha256")
                        == previous["current_sha256"]), (
                    f"{row['path']}: the supersession chain is broken -- "
                    f"{study_id} must supersede {previous['current_sha256']}")
            declared[row["path"]] = row
    return declared


def test_rf05_freeze_manifest_hashes_match_committed_files(lab_root):
    manifest = _load(lab_root, RF05, "freeze_manifest.json")
    assert manifest["hash_algorithm"] == "sha256"
    assert manifest["all_components_present"] is True
    prior = {row["path"]: row["sha256"]
             for rows in manifest["components"].values() for row in rows}
    declared = _declared_supersessions(lab_root, "freeze_manifest.json", prior)
    checked = 0
    superseded = 0
    for group, rows in manifest["components"].items():
        assert rows, f"freeze group {group} is empty"
        for row in rows:
            assert row["present"] is True, f"{row['path']} is not present"
            path = lab_root / row["path"]
            assert path.is_file(), f"{row['path']} is missing"
            actual = sha256_file(path)
            if actual != row["sha256"]:
                assert row["path"] in declared, (
                    f"{row['path']} changed after the RF-05 freeze without a registered "
                    "follow-up supersession declaring the old and new hashes")
                assert declared[row["path"]]["current_sha256"] == actual, (
                    f"{row['path']}: the declared supersession hash does not match the file")
                superseded += 1
            checked += 1
    assert superseded == len(declared), "a declared supersession matched no frozen component"
    ceiling = _declared_ceiling(lab_root, "freeze_manifest.json")
    assert superseded <= ceiling, (
        f"{superseded} frozen components drifted but only {ceiling} are declared "
        "by registered follow-ups")
    assert checked >= 30, "the freeze component denominator collapsed"
    contamination = manifest["contamination"]
    assert contamination["status"] == "NESTED_RETROSPECTIVE"
    assert contamination["untouched_holdout"] is False
    prospective = contamination["prospective_protocol"]
    assert prospective["status"] == "SPECIFIED_NOT_EXECUTED"
    assert prospective["executed"] is False and prospective["live_orders"] is False
    protocol_path = lab_root / prospective["artifact"]
    assert protocol_path.is_file()
    assert sha256_file(protocol_path) == prospective["artifact_sha256"]
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    assert protocol["status"] == "SPECIFIED_NOT_EXECUTED"
    assert protocol["execution_status"] == "NOT_EXECUTED"
    assert math.isclose(manifest["frozen_mde"]["value_bps_per_day"], MDE_BPS,
                        rel_tol=0.0, abs_tol=1e-12)


def test_rf05_claim_ci_denominators_mde_and_holm_family(lab_root):
    claim = _load(lab_root, RF05, "claim_report.json")
    assert math.isclose(claim["frozen_mde"]["value_bps_per_day"], MDE_BPS,
                        rel_tol=0.0, abs_tol=1e-9)
    method = claim["method"]
    assert method["common_dates_only"] is True
    assert method["bootstrap"]["financial_rerun"] is False
    assert method["bootstrap"]["block_days"] == 5
    assert method["bootstrap"]["block_length_development_chosen"] is True
    assert method["multiplicity"]["method"] == "holm"
    assert method["multiplicity"]["family"] == ["TIMING", "BUDGET_AWARE"]
    assert method["multiplicity"]["family_size"] == 2
    family = {entry["id"]: entry for entry in claim["family"]}
    assert set(family) == {"TIMING", "BUDGET_AWARE"}
    evaluated = 0
    for entry in claim["family"]:
        stats = entry["paired_daily_difference"]
        if entry["statistical_status"] != "NOT_EVALUABLE":
            assert stats["n_days"] > 0, f"{entry['id']} has no CI denominator"
            assert stats["ci95_low_bps"] is not None and stats["ci95_high_bps"] is not None
            assert stats["ci95_low_bps"] <= stats["ci95_high_bps"]
            evaluated += 1
        assert entry["holm_adjusted_p"] is not None or stats["p_two_sided"] is None
        assert entry["holm_family_size"] == 2
    assert evaluated >= 1, "no family contrast was evaluated"
    timing = family["TIMING"]
    budget = family["BUDGET_AWARE"]
    assert timing["cells_planned"] == 20
    assert timing["cells_evaluable"] == 10
    assert timing["coverage_status"].startswith("PARTIAL_COVERAGE_10_")
    assert budget["cells_registered"] == 2
    assert budget["coverage_status"].startswith("PARTIAL_COVERAGE_1_")
    assert budget["excluded_cells"], "the excluded BUDGET_AWARE cell needs a reason"
    assert all(row["reason"].strip() for row in budget["excluded_cells"])
    assert claim["answers"]["q2_benefit_within_tested_scope"]["answer"] == "INCONCLUSIVE"


def test_rf05_no_positive_without_ci_clearing_mde(lab_root):
    claim = _load(lab_root, RF05, "claim_report.json")
    checked = 0
    entries = list(claim["family"]) + claim["cells"] + claim["secondary_contrasts"]
    for entry in entries:
        allowed, reason = statistical_status_allowed(
            entry["execution_validity"], entry["implementation_fidelity"],
            entry["statistical_status"])
        assert allowed, f"{entry.get('contrast')}: {reason}"
        if entry["statistical_status"] == POSITIVE:
            stats = entry.get("paired_daily_difference") or {}
            holm = entry.get("holm_adjusted_p")
            assert stats.get("ci95_low_bps") is not None and stats["ci95_low_bps"] > MDE_BPS, (
                f"{entry.get('contrast')} claims POSITIVE without a CI above the MDE")
            assert holm is not None and holm < 0.05, (
                f"{entry.get('contrast')} claims POSITIVE without a Holm-adjusted p below 0.05")
        checked += 1
    assert checked >= 12, "the contrast denominator collapsed"
    positives = [entry for entry in claim["family"] if entry["statistical_status"] == POSITIVE]
    for entry in positives:
        assert entry["holm_significant"] is True
        assert entry["mde_cleared"] is True


def test_rf05_integrity_covers_rf01_to_rf05(lab_root):
    integrity = _load(lab_root, RF05, "artifact_integrity.json")
    assert integrity["status"] == "PASS", (
        [check for check in integrity["checks"] if not check["passed"]])
    checked_phases = {row["phase"] for row in integrity["phase_report_pairs"]}
    assert checked_phases == set(PHASES)
    assert all(row["report_md"] and row["report_json"] for row in integrity["phase_report_pairs"])
    assert integrity["json_file_count"] > 0
    assert len(integrity["json_files_checked"]) == integrity["json_file_count"]
    visited = [path for path in integrity["json_files_checked"]
               if any(f"/{phase}/" in path for phase in PHASES)]
    for phase in PHASES:
        assert any(f"/{phase}/" in path for path in visited), f"{phase} not covered"
    check_ids = {check["id"] for check in integrity["checks"]}
    for required in ("STRICT_JSON", "COVERAGE_NULLS", "SELECTION_JOINS", "FREEZE_HASHES",
                     "CLAIM_GATE", "BOOTSTRAP_DENOMINATORS", "REPORT_COVERAGE", "PHASE_REPORTS"):
        assert required in check_ids, f"integrity check {required} missing"
    for check in integrity["checks"]:
        assert check["denominator"] > 0, f"{check['id']} has no denominator"
        assert check["passed"] is True, f"{check['id']}: {check['failures']}"


def test_rf05_report_has_twelve_sections(lab_root):
    report_md = lab_root.joinpath(*RF05).joinpath("report.md").read_text(encoding="utf-8")
    numbers = sorted(int(value) for value in re.findall(r"^## (\d+)\.", report_md, flags=re.M))
    assert numbers == list(range(1, 13)), f"report sections are {numbers}"
    report = _load(lab_root, RF05, "report.json")
    for key in ("objective", "source", "findings", "tests", "market_runs", "metrics",
                "performance", "proof_capability", "potential", "claim", "limitations", "handoff"):
        assert key in report, f"report.json lacks {key}"
    assert report["phase_id"] == "RF-05"
    assert report["status"] == "PARTIAL_TECHNICAL_CLOSURE"
    assert report["market_runs"]["rf05_engine_runs"] == 0
    assert report["claim"]["statistical_status"] == "INCONCLUSIVE"


def test_rf05_blocked_and_deviation_cells_are_null_with_reasons(lab_root):
    claim = _load(lab_root, RF05, "claim_report.json")
    blocked = claim["blocked_cells"]
    assert len(blocked) == 10
    for row in blocked:
        assert row["cell"].split("/")[0] in BLOCKED_ALPHAS
        assert row["status"] == "BLOCKED_CAPABILITY"
        assert row["account_metrics"] is None
        assert (row["reason"] or "").strip()
        assert (row["metrics_reason"] or "").strip()
    deviations = claim["route_deviations"]
    assert len(deviations) == 1
    assert deviations[0]["cell"] == "A-SC/BTCUSDT"
    assert deviations[0]["implementation_fidelity"] == "DEVIATED"
    assert deviations[0]["statistical_status"] == "NOT_EVALUABLE"
    coverage = _load(lab_root, RF04, "cell_coverage.json")
    for cell in coverage["cells"]:
        if cell["coverage_status"] == "BLOCKED_CAPABILITY":
            assert cell["executed"] is False
            assert cell["account_metrics"] is None
            assert cell["reason"].strip()


def test_rf05_secondary_contrasts_are_separate_and_exploratory(lab_root):
    claim = _load(lab_root, RF05, "claim_report.json")
    family_ids = {entry["id"] for entry in claim["family"]}
    assert family_ids == {"TIMING", "BUDGET_AWARE"}
    secondary_ids = {entry["id"] for entry in claim["secondary_contrasts"]}
    assert {"DELAYED_STATE", "MATCHED_MINUS_CALENDAR", "SELECTOR", "INTERACTION",
            "POLICY_E"} <= secondary_ids
    assert family_ids.isdisjoint(secondary_ids)
    for entry in claim["secondary_contrasts"]:
        assert entry["exploratory"] is True
        assert entry["family"] in ("secondary", "exploratory")
        assert entry["statistical_status"] != POSITIVE
        if entry["statistical_status"] not in ("NOT_EVALUABLE",):
            assert entry["paired_daily_difference"]["n_days"] > 0


def test_rf05_recomputation_cost_stress_and_no_engine_claim(lab_root):
    recomputation = _load(lab_root, RF05, "recomputation.json")
    cost = recomputation["cost_stress"]
    assert cost["registered_multipliers"] == [1.0, 1.5, 2.0]
    assert [row["level"] for row in cost["per_level_aggregate"]] == ["1x", "1.5x", "2x"]
    assert cost["harness_control"]["one_x_reproduces_base_equity"] is True
    assert cost["harness_control"]["max_abs_equity_difference"] == 0.0
    assert cost["per_cell"], "the cost-stress cohort is empty"
    assert all(row["levels"].keys() == {"1x", "1.5x", "2x"} for row in cost["per_cell"])
    for row in cost["per_level_aggregate"]:
        assert row["n_days"] > 0
    reconstruction = recomputation["metric_reconstruction"]
    assert len(reconstruction) == 20
    failures = [row for row in reconstruction if row["total_return_comparison"] != "EXACT_MATCH"]
    assert failures == [], f"engine/recomputed total return mismatches: {failures}"
    assert recomputation["status"] == "RECOMPUTED_FROM_FROZEN_ARTIFACTS"
    assert recomputation["not_rerunnable"], "not-rerunnable items must be explicit"
    assert all(row["reason"].strip() for row in recomputation["not_rerunnable"])


def test_rf05_reproducibility_and_handoff_guardrails(lab_root):
    repro = _load(lab_root, RF05, "reproducibility_manifest.json")
    assert repro["status"] == "REPRODUCIBLE_ON_SERVER"
    assert repro["production_merge_or_publish"] is False
    assert repro["original_evidence_preserved"] is True
    assert repro["rollback"]["protected_paths_untouched"] is True
    assert repro["remaining_blockers"], "remaining blockers must be listed with reasons"
    assert all(row["reason"].strip() for row in repro["remaining_blockers"])
    runner_paths = [row["path"] for row in repro["canonical_runners"]]
    assert "scripts/run_rf05.py" in runner_paths
    assert "scripts/write_rf05_report.py" in runner_paths
    assert "tests/mode4_corrective/test_rf05_claims.py" in runner_paths
    prior = {row["path"]: row["sha256"] for row in repro["canonical_runners"]}
    declared = _declared_supersessions(lab_root, "reproducibility_manifest.json", prior)
    superseded = 0
    for row in repro["canonical_runners"]:
        assert (lab_root / row["path"]).is_file()
        actual = sha256_file(lab_root / row["path"])
        if actual != row["sha256"]:
            assert row["path"] in declared, (
                f"{row['path']} changed after the RF-05 reproducibility manifest without a "
                "registered follow-up supersession declaring the old and new hashes")
            assert declared[row["path"]]["current_sha256"] == actual, (
                f"{row['path']}: the declared supersession hash does not match the file")
            superseded += 1
    assert superseded == len(declared), "a declared supersession matched no canonical runner"
    repro_ceiling = _declared_ceiling(lab_root, "reproducibility_manifest.json")
    assert superseded <= repro_ceiling, (
        f"{superseded} canonical runners drifted but only {repro_ceiling} are declared")
    assert repro["artifact_hashes"]["rf05"]
    handoff = lab_root.joinpath(*RF05).joinpath("handoff.md").read_text(encoding="utf-8")
    for token in ("Canonical commands", "Rollback", "Remaining blockers", "no production merge"):
        assert token.lower() in handoff.lower(), f"handoff.md lacks {token!r}"
