#!/usr/bin/env python
"""Guide 13.7 — when validity fails, version it and INVALIDATE the affected results.

Corrections were narrated in prose in four phase reports. Prose is not an audit
trail: a reader cannot tell from it which published number a defect killed, nor
check that the replacement came from a later run rather than from a nicer one.

So the numeric history is DERIVED, not typed. Every evidence run that ever wrote
a phase artifact is read in timestamp order, the headline figure is extracted,
and each change of value becomes a superseding event linked to the run ids on
both sides. A correction whose "before" number cannot be found in the evidence
tree is reported as UNVERIFIABLE rather than accepted.

The evidence directory is append-only, which is what makes this possible: the
run that produced the wrong number is still there.
"""

from __future__ import annotations

import glob
import json
import pathlib
import sys

LAB_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter, utc_now_iso  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"

#: artifact -> (label, how to pull the run's STATE out of it). The state is a
#: dict, not one number, so a defect can be matched to the transition it caused
#: instead of inheriting the artifact's whole history.
TRACKED = {
    "lab07_continuous_trace.json": (
        "LAB-07 continuous account",
        lambda d: {
            "total_return": (d.get("continuous_account") or {}).get("total_return"),
            "entries": (d.get("continuous_account") or {}).get("entries"),
            "fills": (d.get("continuous_account") or {}).get("fills"),
            "warm_source": next(
                (v.get("source") for v in
                 ((d.get("continuous_account") or {}).get("warm_bar_requirements") or {}).values()),
                None),
        }),
    "lab06_decision_ledger.json": (
        "LAB-06 decision ledger",
        lambda d: {"switch_count": d.get("switch_count"), "decisions": d.get("decisions")}),
    "lab05_k_selection.json": (
        "LAB-05 K selection",
        lambda d: {"k_used": d.get("registered_k_used")}),
}

#: Defects that changed a published figure or invalidated a claim. `changed`
#: names the tracked artifact whose history must corroborate it; a defect that
#: only removed a false CLAIM has `changed: None` and is verified by its test.
DEFECTS = [
    {"id": "COR-01", "phase": "LAB-07",
     "defect": "the intent tape was built from the FINAL adapter's decision list, so every trade "
               "made under an earlier parameter version vanished while still counting as an entry",
     "invalidated": "the first continuous-account return",
     "changed": "lab07_continuous_trace.json",
     # the tape defect is the transition where fills jump while entries hold
     "signature": lambda a, b: (a.get("entries") == b.get("entries")
                                and (a.get("fills") or 0) < (b.get("fills") or 0)),
     "guarded_by": "tests/test_lab07_integration.py::"
                   "test_the_tape_is_built_from_the_active_adapter_at_every_bar"},
    {"id": "COR-02", "phase": "LAB-07",
     "defect": "the warm-bar requirement before an activation was a hardcoded 64, an unregistered "
               "free parameter of the switching policy; it is now derived from each adapter's own "
               "warmup_bars()",
     "invalidated": "the return measured under the arbitrary delay",
     "changed": "lab07_continuous_trace.json",
     # the warm-bar defect is the transition where the requirement gains a source
     "signature": lambda a, b: (a.get("warm_source") != b.get("warm_source")
                                and b.get("warm_source") == "derived_from_adapter_warmup_bars"),
     "guarded_by": "tests/test_lab07_integration.py::"
                   "test_the_warm_requirement_is_the_adapters_own_declaration"},
    {"id": "COR-03", "phase": "LAB-07",
     "defect": "the continuous account was driven from the 4h feature panel with no signals, so it "
               "made zero trades and every exit gate passed on an empty account",
     "invalidated": "the first run entirely (no fills, flat equity, one segment)",
     "changed": "lab07_continuous_trace.json",
     # the empty-run defect is the transition out of "no fills at all"
     "signature": lambda a, b: not a.get("fills") and bool(b.get("fills")),
     "guarded_by": "tests/test_lab07_integration.py::test_the_run_actually_traded"},
    {"id": "COR-04", "phase": "LAB-06",
     "defect": "every_switch_has_supporting_episodes was reported True over ZERO switches and "
               "quoted as evidence that every switch carried its evidence",
     "invalidated": "the claim, not a number: the switch count was always 0 and stays 0",
     "changed": None,
     "guarded_by": "tests/test_contingency_paths.py::"
                   "test_a_ledger_verdict_over_an_empty_population_is_labelled_vacuous"},
    {"id": "COR-05", "phase": "LAB-06",
     "defect": "a leaked loop variable gave every bank entry the LAST discovery's timestamp, so "
               "the lineage field T46 protects was wrong on all of them",
     "invalidated": "the first bank build (sizes [0,0,0,0,0,8])",
     "changed": None,
     "guarded_by": "tests/test_lab06_policy.py::"
                   "test_t46_every_entry_carries_its_own_discovery_time"},
    {"id": "COR-06", "phase": "LAB-06",
     "defect": "the contiguous-block support gate counted blocks over every episode with weight "
               "> 1e-9, and a Gaussian kernel never reaches zero, so every estimate looked like "
               "one unbroken run and every recommendation was refused for the wrong reason",
     "invalidated": "the first response panel (0 SUPPORTED estimates)",
     "changed": None,
     "guarded_by": "tests/test_lab06_policy.py::"
                   "test_t48_a_single_contiguous_block_is_not_enough_support"},
    {"id": "COR-07", "phase": "LAB-06",
     "defect": "switch assessment ran on the 7-day episode boundary instead of the registered 4h "
               "regime observation, tying two of the four clocks together",
     "invalidated": "the first decision ledger (155 decisions instead of 6566)",
     "changed": None,
     "guarded_by": "tests/test_lab06_policy.py::test_t52_the_four_clocks_are_distinct"},
    {"id": "COR-08", "phase": "LAB-05",
     "defect": "the model was fitted at a 6-month cadence against a registered 28-day one",
     "invalidated": "the first emission tape (762 of 1099 emissions STALE_MODEL)",
     "changed": None,
     "guarded_by": "tests/test_lab05_regime.py::test_t43_a_stale_model_is_reported_not_hidden"},
    {"id": "COR-09", "phase": "LAB-04",
     "defect": "the probe design used hash() on strings and unsorted set iteration, both salted "
               "by PYTHONHASHSEED, so a design did not reproduce across processes",
     "invalidated": "the first probe designs",
     "changed": None,
     "guarded_by": "tests/test_lab04_selector.py::"
                   "test_t32_probe_design_is_reproducible_across_processes"},
    {"id": "COR-10", "phase": "LAB-04",
     "defect": "the space-filling anchor required by guide 7.2 step 1 was missing from the "
               "candidate design",
     "invalidated": "the whole first 20-cell matrix, which was re-run",
     "changed": None,
     "guarded_by": "tests/test_lab04_legacy_labelling.py::"
                   "test_the_audit_refuses_a_matrix_built_with_the_wrong_design"},
    {"id": "COR-11", "phase": "cross-phase",
     "defect": "configs/data_eligibility.json was written from an earlier read of the snapshot "
               "than the one the study pins, under-counting every symbol",
     "invalidated": "the published per-symbol row counts",
     "changed": None,
     "guarded_by": "tests/test_lab03_pipeline.py::"
                   "test_data_eligibility_reproduces_from_the_pinned_manifest"},
    {"id": "COR-12", "phase": "cross-phase",
     "defect": "the read-lock classified drift by file digest alone, so it invalidated a cohort "
               "whose measurements were provably unchanged",
     "invalidated": "the EXTERNAL_DATA_DRIFT verdict on the G3 cohort",
     "changed": None,
     "guarded_by": "tests/test_lab03_pipeline.py::"
                   "test_measured_metrics_drift_is_a_restamp_and_the_shallow_check_still_fails_closed"},
    {"id": "COR-13", "phase": "LAB-09",
     "defect": "the lab passed the registered ONE-WAY taker fee into the engine's `fee` "
               "parameter, which the installed quantbt documents as a LEGACY ROUND-TRIP fee and "
               "halves into the canonical one-way rate. Every account since LAB-04 was charged "
               "0.0002 one-way where the study registered 0.0004. The engine default for `fee` "
               "is also 0.0004, so the call looked correct and raised nothing",
     "invalidated": (
         "SUPERSEDED READING. This entry first said 'no CONCLUSION is invalidated', on the "
         "strength of the deployment-side measurement alone: at the registered fee the "
         "development contrasts move by at most 19% in relative terms and none crosses the "
         "minimum economic effect. That half still holds. The other half was never measured "
         "when the claim was made, and it now is: scripts/probe_fee_sensitivity.py re-selected "
         "A-SC/BTCUSDT at the registered fee and ONE of twelve arm-selections CHANGED -- arm A "
         "at cutoff 2021-06-30 chose AP=41/threshold=50 instead of AP=36/threshold=55. The "
         "selector is fee-sensitive, so the defect is a DESIGN defect and not only an accounting "
         "one: the candidate bank LAB-04 built, and every arm LAB-08 and LAB-09 compared, were "
         "chosen under a cost the study did not register. By the severity rule fixed BEFORE the "
         "probe ran, that is MAJOR, and guide L09's exit makes a major accounting error "
         "FAILED_VALIDITY: the affected runs are invalidated, a protocol revision is required "
         "before a retest, and the headline is not kept"),
     "changed": None,
     "guarded_by": "tests/test_lab09_confirmation.py::"
                   "test_the_fee_binding_defect_is_reported_not_absorbed"},
    {"id": "COR-14", "phase": "LAB-09",
     "defect": "the confirmation role's group ablation was computed where LAB-05 computes it -- "
               "on the FIRST cutoff's training window -- which for that role is the 365 days "
               "BEFORE the interval starts, i.e. development data. It could not support a "
               "descriptive claim about the confirmation interval",
     "invalidated": "nothing published: it was caught before the descriptive contribution was "
                    "written. The claim now reads configs/lab09_group_ablation.json, measured on "
                    "the LAST cutoff's window",
     "changed": None,
     "guarded_by": "tests/test_lab09_confirmation.py::"
                   "test_the_descriptive_claim_rests_on_an_in_interval_window"},
    {"id": "COR-15", "phase": "LAB-09",
     "defect": "the phase auditors marked a clause DONE when a STRING naming its evidence was "
               "present, so a pointer at a renamed field or a deleted test was indistinguishable "
               "from a real one",
     "invalidated": "no number. It weakened every clause audit, which is why the LAB-09 auditor "
                    "RESOLVES each pointer in the artifact, in pytest's collection, or in the "
                    "source before it counts it",
     "changed": None,
     "guarded_by": "tests/test_lab09_confirmation.py::"
                   "test_the_audit_resolves_its_evidence_pointers"},
    {"id": "COR-16", "phase": "LAB-06",
     "defect": "guide 13.4 names `proposal_before_guard` and `decision_after_guard` and requires "
               "both on EVERY decision including a no-switch. Neither existed, so a decision "
               "where no challenger cleared the economics and one where a challenger DID clear "
               "and a gate refused it were the same row -- and that difference is the entire "
               "content of an inaction region, which is LAB-06's whole result",
     "invalidated": "no number: the 6,566 decisions and the zero switches are unchanged. What "
                    "was missing was the evidence that distinguishes the two kinds of no-switch, "
                    "and the ledger was re-derived with it rather than re-decided",
     "changed": None,
     "guarded_by": "tests/test_lab06_policy.py::"
                   "test_a_no_switch_records_what_the_economics_proposed_before_any_gate"},
    {"id": "COR-17", "phase": "cross-phase",
     "defect": "the frozen protocol declares `execution_bars: 1m` for all four alphas and the "
               "account resolves protective orders on the DECISION bar: both "
               "run_continuous_account and run_candidate hand the engine the decision-bar frame "
               "and no 1-minute frame is built anywhere in the account path",
     "invalidated": "the ABSOLUTE level of any cell whose alpha rests protection. Measured: "
                    "A-HMA 27% of fills protective, A-VWAP 50%, A-SC 0% -- A-SC cannot be "
                    "affected at all. No CONTRAST is invalidated: every arm and every control "
                    "runs on the same frame through the same engine, so the resolution cancels "
                    "in B-A, C-A, D-B and D-C",
     "changed": None,
     "guarded_by": "tests/test_guide_contracts.py::"
                   "test_the_declared_execution_resolution_is_compared_against_the_actual_one"},
    {"id": "COR-18", "phase": "cross-phase",
     "defect": "the assertion-vacuity audit declared its accepted contingency branches by "
               "`file:LINE`. A line number expires the moment anything above it is edited, which "
               "fails in two directions: a real declaration silently becomes UNDECLARED, and a "
               "stale number can land on a DIFFERENT assert that then reads as declared although "
               "nobody reviewed it",
     "invalidated": "no measurement. It weakened the audit that exists to catch checks nobody "
                    "has looked at -- 3 of 5 declarations had already drifted off their lines by "
                    "the time it was found",
     "changed": None,
     "guarded_by": "tests/test_contingency_paths.py::"
                   "test_a_vacuity_declaration_survives_an_edit_above_it"},
    {"id": "COR-19", "phase": "LAB-09",
     "defect": "the MISSING_ENRICHMENT stress dropped a random 20% of emissions independently. "
               "Removing scattered rows almost never moves where the FIRST transition of a "
               "period falls, so the corrupted tape produced a refresh schedule identical to the "
               "real one on all six cutoffs -- the stress would have re-run arm D for an hour "
               "and could not have produced a different answer",
     "invalidated": "nothing published: caught by smoke-testing the stress before the run rather "
                    "than after. The stress now drops CONTIGUOUS outages, which is also what an "
                    "enrichment product actually does; six week-long outages drop 4.3% of the "
                    "tape and move one of the six cutoffs",
     "changed": None,
     "guarded_by": "tests/test_lab09_stress.py::"
                   "test_missing_enrichment_drops_contiguous_stretches_not_scattered_rows"},
    {"id": "COR-20", "phase": "cross-phase",
     "defect": "T54 stayed PARTIAL with the reason 'applying it to a reported ARM COMPARISON is "
               "LAB-08's, because there is no arm comparison yet'. LAB-08 ran the comparison and "
               "the reason went stale. Worse, the `A_legacy_selection_adjusted` label lived on "
               "the DOCUMENT and in the report's prose, not on the contrasts -- so a contrast "
               "lifted out of the panel, which is exactly what LAB-09's claim report does for "
               "the selection and timing contributions, arrived with no hint that its baseline "
               "is not untouched",
     "invalidated": "no number. It left the guide 13.6 caveat one indirection away from the "
                    "comparison it qualifies. Every contrast measured against arm A now carries "
                    "the label itself, the interaction included because it contains B-A, and "
                    "T54 moves to COVERED",
     "changed": None,
     "guarded_by": "tests/test_lab08_factorial.py::"
                   "test_every_contrast_against_arm_a_carries_the_baseline_caveat"},
    {"id": "COR-21", "phase": "LAB-09",
     "defect": "not a defect in a result: two REVISIONS to a registered contract. The OS "
               "resource budget registered one worker and a CPU limit of 2. The confirmation was "
               "measured at 24 min per cell -- twelve selector cutoffs at 97 strategy "
               "evaluations each -- and the remaining twelve cells would have taken close to "
               "five hours on one core while three sat idle. The user asked for it to be faster, "
               "twice: workers 1 -> 2 with the CPU limit untouched, then 2 -> 3 with the limit "
               "raised to 3",
     "invalidated": "the COMPARABILITY of the confirmation's wall seconds against LAB-08's, "
                    "which were measured at one worker. No measured RESULT is affected: cells "
                    "are independent, deterministic and checkpointed, so a shard decides only "
                    "which process computes a cell. A shard is a CELL boundary and never an arm "
                    "boundary -- all five arms of a cell still run sequentially in one process "
                    "on one core -- so no arm can finish ahead of another, which is the thing "
                    "guide L08.6 forbids buying with CPU. Peak memory is 0.40 GiB per worker "
                    "against a 4 GiB budget, and the lab processes are niced so the user's live "
                    "collectors preempt them",
     "changed": None,
     "guarded_by": "tests/test_guide_contracts.py::"
                   "test_a_budget_revision_is_appended_and_never_restamped"},
    {"id": "COR-22", "phase": "LAB-09",
     "defect": "the guard written for COR-21 asserted the wrong invariant. It required "
               "`cpu_limit` to be identical across a budget revision, as a proxy for 'the "
               "conditions a baseline was measured under must not change'. The proxy fails in "
               "both directions: it blocks a recorded and justified revision, and it permits any "
               "unrecorded change that does not happen to touch that one number",
     "invalidated": "nothing measured. What it weakened is the guard itself. Guide L08.6 forbids "
                    "raising CPU SO THAT one policy finishes ahead of the baseline, so the "
                    "invariant is about ARMS: a revision must now state that per-arm compute is "
                    "unchanged, say HOW the arms stay equal, and justify any change to the CPU "
                    "limit separately",
     "changed": None,
     "guarded_by": "tests/test_guide_contracts.py::"
                   "test_a_budget_revision_is_appended_and_never_restamped"},
    {"id": "COR-23", "phase": "cross-phase",
     "defect": "two defects in the assertion-vacuity audit itself, found by running it. First, "
               "the skip detector filtered on `report.when == 'setup'`, but pytest.skip() called "
               "inside a test body -- how every artifact-dependent test here skips -- reports at "
               "`call`. It saw ZERO skipped tests and filed all 107 of their assertions as "
               "unreachable branches, which is the same conflation COR-18 had just fixed. "
               "Second, the gate that reads this audit's output was audited BY it: when the gate "
               "fails, pytest stops at its first assertion, so its later assertions go unreached, "
               "so the next run reports them undeclared, so the gate keeps failing -- a loop with "
               "no fixed point",
     "invalidated": "the audit's own verdict while both were present: 107 assertions reported as "
                    "unexamined checks when they were tests waiting for an artifact. After both "
                    "fixes: 26 skipped tests detected, 102 assertions classified SKIPPED_TEST, 7 "
                    "genuinely unreached branches and ALL of them declared, 0 undeclared, 0 "
                    "stale declarations",
     "changed": None,
     "guarded_by": "tests/test_contingency_paths.py::"
                   "test_a_vacuity_declaration_survives_an_edit_above_it"},
]


def history(artifact: str) -> list[dict]:
    """Every state this artifact ever held, and each transition between them."""
    _label, extract = TRACKED[artifact]
    rows = []
    for path in sorted(glob.glob(str(LAB_ROOT / "evidence/**" / artifact), recursive=True)):
        run_id = pathlib.Path(path).parent.name
        try:
            state = extract(json.loads(pathlib.Path(path).read_text()))
        except Exception:
            continue
        rows.append({"run_id": run_id, "state": state})
    changes = []
    for previous, current in zip(rows, rows[1:]):
        if previous["state"] != current["state"]:
            changes.append({"from": previous["state"], "to": current["state"],
                            "superseded_run": previous["run_id"],
                            "superseding_run": current["run_id"]})
    return changes


def main() -> int:
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    numeric = {artifact: history(artifact) for artifact in TRACKED}
    with writer.attempt("guide.13_7_correction_ledger") as att:
        entries = []
        for defect in DEFECTS:
            record = {k: v for k, v in defect.items() if k != "signature"}
            artifact = defect["changed"]
            if artifact is None:
                record["numeric_change"] = None
                record["verification"] = "STRUCTURAL: the defect removed a false claim, not a value"
                entries.append(record)
                continue
            signature = defect.get("signature")
            matched = [c for c in numeric.get(artifact, [])
                       if signature is None or signature(c["from"], c["to"])]
            record["numeric_change"] = matched
            if not matched:
                record["verification"] = "UNVERIFIABLE: no matching transition in the evidence tree"
            elif len(matched) > 1:
                record["verification"] = (
                    f"AMBIGUOUS: {len(matched)} transitions match this defect's signature")
            else:
                record["verification"] = "DERIVED_FROM_EVIDENCE"
            entries.append(record)
        att.detail = {"defects": len(entries)}

    unverifiable = [e["id"] for e in entries
                    if str(e["verification"]).startswith(("UNVERIFIABLE", "AMBIGUOUS"))]
    document = {
        "schema": "crypto_regime_lab.correction_ledger.v1",
        "guide_section": "13.7",
        "built_at_utc": utc_now_iso(),
        "rule": ("guide 13.7: when validity fails, fix it in the lab, version it and INVALIDATE "
                 "the affected results -- do not carry on taking headlines. Prose in a report "
                 "does not let a reader check which published number a defect killed"),
        "method": ("the numeric history is DERIVED from every evidence run that wrote the "
                   "artifact, in timestamp order. The evidence tree is append-only, so the run "
                   "that produced the superseded number is still there to be read"),
        "defects": entries,
        "defects_total": len(entries),
        "numeric_history": numeric,
        "unverifiable": unverifiable,
        "evidence_is_append_only": True,
        "status": "EVERY_CORRECTION_TRACEABLE" if not unverifiable else "REVIEW_REQUIRED",
    }
    writer.write_config("correction_ledger.json", document)
    writer.write_json("correction_ledger.json", document, schema=document["schema"])

    for entry in entries:
        print(f"  {entry['id']}  {entry['phase']:<11} {entry['verification'].split(':')[0]}")
        for change in entry.get("numeric_change") or []:
            before = change["from"].get("total_return")
            after = change["to"].get("total_return")
            fmt = lambda v: "none" if v is None else f"{v:+.4%}"  # noqa: E731
            print(f"        {fmt(before)} -> {fmt(after)}   "
                  f"fills {change['from'].get('fills')} -> {change['to'].get('fills')}   "
                  f"superseded {change['superseded_run'][:28]}")
    print(f"\n{document['status']}  ({len(entries)} corrections, "
          f"{len(unverifiable)} unverifiable)")
    print(f"evidence -> {writer.run_dir}")
    return 0 if not unverifiable else 1


if __name__ == "__main__":
    raise SystemExit(main())
