#!/usr/bin/env python
"""FUP-04 — event-account memory budget: engine report-level opt-in + peak-RSS audit.

Registered follow-up study
``evidence/corrective_mode4_v3/followup-studies/followup_studies_registration.json``
entry FUP-04 (index 3). Context: the RA-07 decay deep-dive was SIGKILLed on this
host after four prior OOM fixes and a scope cut. ``scripts/mem_audit.py`` measured
the stages on the lab's real data paths and found the accumulator: a single
``run_event_account`` call over the full 613,440-bar deployment frame drove RSS to
4.24 GiB and the kernel OOM-killed it (dmesg, 2026-09-20 08:29:01). The engine's
own documented ``report_level`` kwarg selects its output-retention profile, and
the reduced profile reproduces the engine-default account path EXACTLY while
roughly halving peak transient memory.

What this script emits, all from measurement (never a restated claim):

* ``mem_audit_s3_score_profile.json`` — the 613k-bar deployment account under a
  4 GiB address-space cap with ``report_level="score"``: it COMPLETES.
* ``mem_audit_s3_engine_default.json`` — the same call with the engine default
  under the same cap: it FAILS (the OOM turned into a recordable signal).
* ``mem_audit_s7_parity.json`` — the real RA-05 fold-0 account call, engine
  default vs ``score``: byte-equal equity, identical strategy-level counts.
* ``report_level_memory_repair.json`` — the FUP-04 declaration: the measured
  effects, the opt-in contract, the frozen-component supersessions this repair
  needs (RF-05 hashes never drift silently), the declared supersession ceilings,
  and the protocol-migration rows for the guard rules this changes.

The script fails loudly if the parity invariants it records stop holding, so the
artifact can never outlive the measurement that justified it. Nothing outside
LAB_ROOT is written; the frozen RF-05 artifacts are never edited.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy, sha256_file  # noqa: E402

STUDY_ID = "corrective_mode4_v3"
RUN_ID = "FUP-04"
RUN_DIR = LAB_ROOT / "evidence" / STUDY_ID / RUN_ID
RF05_DIR = LAB_ROOT / "evidence" / STUDY_ID / "RF-05"
FUP01_DECLARATION = LAB_ROOT / "evidence" / STUDY_ID / "FUP-01" / "native_event_capability.json"
REGISTRATION_REF = ("evidence/corrective_mode4_v3/followup-studies/"
                    "followup_studies_registration.json#/studies/3")

FRAME_ROWS = 613440          # the deep-dive deployment frame the OOM hit
RLIMIT_GIB = 4.0             # the cap both s3 measurements ran under
# What the RF-05 guards consult for the ceiling on frozen-component drift. The
# original hardcoded 1 covered FUP-01's single repair; this repair needs two.
SUPERSESSION_CEILINGS = {"freeze_manifest.json": 2, "reproducibility_manifest.json": 1}

# (relpath, manifest name, container, reason). A previous declaration for a path
# (if any) is read from FUP-01's artifact so the chain is recorded, not assumed.
DECLARED_DRIFT = (
    ("src/crypto_regime_lab/experiments/dynamic_fold_provider.py", "freeze_manifest.json",
     "components",
     "FUP-04 threads the engine's output-retention profile through the event route "
     "(scorer + deployment account) and reads selection counters from the "
     "profile-invariant strategy-level fill records; default None keeps every "
     "existing caller byte-identical, so the frozen RF-05 results are not "
     "recomputed or restated"),
    ("src/crypto_regime_lab/integration/event_account.py", "freeze_manifest.json",
     "components",
     "FUP-04 adds an opt-in report_level to run_event_account and records the "
     "engine-reported resolved profile for provenance; the default path is "
     "unchanged, so the frozen RF-05 results are not recomputed or restated"),
    ("tests/mode4_corrective/test_rf05_claims.py", "reproducibility_manifest.json",
     "canonical_runners",
     "FUP-04 extends the RF-05 freeze/reproducibility guard's declared-supersession "
     "loader to read a registry of registered sources (each trusted only for its own "
     "study id, with registration_ref resolved) and replaces the hardcoded ceiling "
     "of 1 with a declared, counted ceiling"),
)


def _sha_in_manifest(manifest: dict, relpath: str, container: str) -> str | None:
    if container == "components":
        for rows in manifest.get("components", {}).values():
            for row in rows:
                if row["path"] == relpath:
                    return row["sha256"]
    elif container == "canonical_runners":
        for row in manifest.get("canonical_runners", []):
            if row["path"] == relpath:
                return row["sha256"]
    return None


def _fup01_current_sha(relpath: str) -> str | None:
    """The hash FUP-01 already declared as current for this path, if any."""
    if not FUP01_DECLARATION.is_file():
        return None
    payload = json.loads(FUP01_DECLARATION.read_text(encoding="utf-8"))
    for row in payload.get("frozen_component_supersessions", []):
        if row["path"] == relpath:
            return row["current_sha256"]
    return None


def frozen_component_supersessions() -> list[dict]:
    """Declare the RF-05-pinned files this registered follow-up repairs.

    Same contract as FUP-01's declaration, plus the chain link: a path FUP-01
    already repaired must name the hash FUP-01 left behind as the one this
    declaration supersedes, so an out-of-order repair cannot masquerade as a
    valid chain. ``rf05_results_recomputed`` stays False for all three: no RF-05
    number is recomputed, restated or superseded by this repair.
    """
    out = []
    for relpath, manifest_name, container, reason in DECLARED_DRIFT:
        manifest_path = RF05_DIR / manifest_name
        path = LAB_ROOT / relpath
        if not manifest_path.is_file() or not path.is_file():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        prior = _sha_in_manifest(manifest, relpath, container)
        if prior is None:
            continue
        row = {
            "path": relpath,
            "frozen_by": f"evidence/corrective_mode4_v3/RF-05/{manifest_name}",
            "frozen_sha256": prior,
            "current_sha256": sha256_file(path),
            "registered_study": "FUP-04",
            "registration_ref": REGISTRATION_REF,
            "reason": reason,
            "rf05_results_recomputed": False,
        }
        previous = _fup01_current_sha(relpath)
        if previous is not None:
            row["supersedes_previous_current_sha256"] = previous
        out.append(row)
    return out


# ---------------------------------------------------------------------------
# the measurements this declaration is built on
# ---------------------------------------------------------------------------

def classify_mem_audit(payload: dict) -> tuple[str, dict] | None:
    """Name one raw ``scripts/mem_audit.py`` output by the stage it contains.

    Returns ``(measurement_name, headline)`` or None for a payload this
    declaration does not use. Headlines are the numbers the artifact quotes, so
    the guard tests and the artifact can never disagree about them.
    """
    stages = payload.get("stages", {})
    s7 = stages.get("s7_report_level_parity")
    if s7:
        return "s7_parity_engine_default_vs_score", {
            "account_window": "RA-05 M4_CAL fold 0 train window",
            "default_peak_mib": s7["default_peak_mib"],
            "score_peak_mib": s7["score_peak_mib"],
            "default_wall_s": s7["default_wall_s"],
            "score_wall_s": s7["score_wall_s"],
            "equity_len": s7["equity_len_default"],
            "max_abs_equity_diff": s7["max_abs_equity_diff"],
            "exact_equal": s7["exact_equal"],
            "strategy_fills_default": s7["strategy_fills_default"],
            "strategy_fills_score": s7["strategy_fills_score"],
            "entries_default": s7["entries_default"],
            "entries_score": s7["entries_score"],
            "engine_fill_count_default": s7["engine_fill_count_default"],
            "engine_fill_count_score": s7["engine_fill_count_score"],
        }
    s3 = stages.get("s3_deployment_full_frame")
    if s3:
        failed = stages.get("s3_deployment_full_frame__FAILED")
        headline = {
            "frame_rows": s3["frame_rows"],
            "report_level": s3["report_level"],
            "peak_mib": s3["peak_mib"],
            "delta_mib": s3["delta_mib"],
            "wall_s": s3["wall_s"],
            "rlimit_as_gib": (stages.get("rlimit") or {}).get("rlimit_as_gib"),
            "outcome": "FAILED" if failed else "COMPLETED",
        }
        # Named by the profile actually requested, never by the outcome we hope
        # for: a default-profile run that happened to fit would otherwise be
        # filed as the score-profile evidence.
        name = ("s3_deployment_full_frame_score_profile"
                if str(s3.get("report_level")) == "score"
                else "s3_deployment_full_frame_engine_default")
        if not failed:
            headline["equity_len"] = s3["equity_len"]
            headline["status"] = s3["status"]
            return name, headline
        headline["error_type"] = failed["error_type"]
        headline["error"] = failed["error"]
        return name, headline
    return None


def check_invariants(measurements: dict) -> None:
    """Every number the declaration rests on, re-checked before it is written.

    These are the assertions that make the artifact reproducible rather than
    asserted: if the parity, the budget or the failure mode ever changes, this
    script fails instead of recording a claim the measurement no longer supports.
    """
    parity = measurements.get("s7_parity_engine_default_vs_score")
    assert parity is not None, (
        "the parity measurement is required: the opt-in exists only because a reduced "
        "profile was measured to reproduce the engine default's account path exactly")
    assert parity["equity_len"] > 0
    assert parity["exact_equal"] is True and parity["max_abs_equity_diff"] == 0.0, (
        f"equity parity broken: {parity['max_abs_equity_diff']} on {parity['equity_len']} bars")
    assert parity["strategy_fills_default"] == parity["strategy_fills_score"] > 0, (
        "strategy-level fills must be profile-invariant")
    assert parity["entries_default"] == parity["entries_score"] > 0
    assert parity["engine_fill_count_default"] == parity["strategy_fills_default"], (
        "on the engine default the audit count and the strategy-level count must agree, "
        "which is what makes switching the scorer to the latter behaviour-preserving")
    assert parity["engine_fill_count_score"] == 0, (
        "a reduced profile must drop the native audit trail; if it ever retains it, the "
        "count-source note in dynamic_fold_provider must be re-derived, not assumed")
    assert parity["score_peak_mib"] < parity["default_peak_mib"], (
        "the reduced profile must actually be smaller or the repair has no basis")

    score = measurements.get("s3_deployment_full_frame_score_profile")
    assert score is not None, "the 613k-bar score-profile measurement is required"
    assert score["outcome"] == "COMPLETED", score
    assert score["frame_rows"] == FRAME_ROWS
    assert score["status"] == "EVALUATED", score
    assert score["equity_len"] == FRAME_ROWS, (
        "the deployment account must cover the whole frame, not a truncated one")
    assert score["rlimit_as_gib"] == RLIMIT_GIB, (
        "the score measurement must run under the same cap the default profile failed under")

    default = measurements.get("s3_deployment_full_frame_engine_default")
    assert default is not None, "the control measurement (engine default) is required"
    assert default["outcome"] == "FAILED", (
        "the control must reproduce the budget failure, or the comparison has no control")
    assert default["frame_rows"] == FRAME_ROWS
    assert default["rlimit_as_gib"] == RLIMIT_GIB
    assert default["peak_mib"] > score["peak_mib"], (
        "the failing profile must be the more expensive one")


def protocol_migration() -> list[dict]:
    """The guard rules this repair changes, old rule -> new rule -> reason -> test.

    Recorded because changing a frozen guard's strength is itself a protocol
    decision; it may not happen silently inside a test edit.
    """
    guard = "tests/mode4_corrective/test_rf05_claims.py"
    return [
        {
            "old_gate": ("RF-05 freeze guard admitted at most ONE registered supersession of a "
                         "frozen component (`assert superseded <= 1`, hardcoded when FUP-01 was "
                         "the only repair)"),
            "new_disposition": ("the ceiling is DECLARED in a registered artifact "
                                "(`frozen_supersession_ceilings` in FUP-04: freeze_manifest 2, "
                                "reproducibility_manifest 1) and read by the guard; a drift "
                                "beyond the declared ceiling still fails, and the ceiling can "
                                "only move by registering a study that declares a new one"),
            "reason": ("FUP-04 repairs two frozen lab_source files (the event route and the "
                       "event account), which the pre-existing single-slot ceiling could not "
                       "admit without either dropping the repair or editing the frozen "
                       "artifacts -- both worse than declaring the ceiling"),
            "required_test": (f"{guard}::test_rf05_freeze_manifest_hashes_match_committed_files "
                              "reads the ceiling from this FUP-04 artifact and keeps "
                              "`superseded == len(declared)` and `checked >= 30`"),
            "affected_claims": ("none: RF-05 results are not recomputed or restated "
                                "(`rf05_results_recomputed: false`)"),
        },
        {
            "old_gate": ("supersession declarations were read from FUP-01's artifact only, with "
                         "`registered_study == \"FUP-01\"` hardcoded"),
            "new_disposition": ("declarations are read from a registry of registered sources; "
                                "each source is trusted only for its own study id, and the row's "
                                "`registration_ref` must resolve to that id in the follow-up "
                                "registration file, with the supersession chain "
                                "(`supersedes_previous_current_sha256`) checked rather than "
                                "assumed"),
            "reason": ("a second registered repair has no legal place to declare itself under a "
                       "single hardcoded source, and a declaration that cannot point at its own "
                       "registration is not evidence of registration"),
            "required_test": (f"{guard}::_declared_supersessions (exercised by both the freeze "
                              "and the reproducibility guards) fails on a wrong study id, on an "
                              "unresolvable registration_ref, and on a broken chain"),
            "affected_claims": "none",
        },
        {
            "old_gate": ("EventAccountScorer reported turnover/trade_count from "
                         "`engine_fill_count` (the native audit-trail count)"),
            "new_disposition": ("scores read the profile-invariant strategy-level fill count; "
                                "the audit-trail count is retained as provenance only"),
            "reason": ("under a reduced output profile the audit trail is not retained and that "
                       "counter legitimately reads 0, which would silently zero a selection "
                       "field; the two counters were measured equal (81 == 81) on the engine "
                       "default, so the change is behaviour-preserving for existing callers"),
            "required_test": ("tests/mode4_corrective/test_fup04_report_level.py::"
                              "test_fup04_scorer_fields_are_profile_invariant, plus the measured "
                              "counts recorded in this artifact"),
            "affected_claims": "none",
        },
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mem-audit-json", action="append", required=True,
                        help="path to a raw scripts/mem_audit.py output (repeatable; supply the "
                             "score-profile s3, the engine-default s3 and the s7 parity run)")
    parser.add_argument("--force", action="store_true",
                        help="overwrite an existing FUP-04 declaration explicitly")
    args = parser.parse_args()
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID, lab_run_id=RUN_ID)
    declaration_path = RUN_DIR / "report_level_memory_repair.json"
    if declaration_path.exists() and not args.force:
        raise SystemExit(f"{declaration_path} exists; pass --force to supersede explicitly")

    started = time.perf_counter()
    measurements: dict = {}
    raw_sources: dict = {}
    for raw_path in args.mem_audit_json:
        source = Path(raw_path)
        payload = json.loads(source.read_text(encoding="utf-8"))
        classified = classify_mem_audit(payload)
        if classified is None:
            continue
        name, headline = classified
        assert name not in measurements, f"two inputs both claim to be {name}"
        measurements[name] = headline
        raw_sources[name] = {"path": str(source), "sha256": sha256_file(source),
                             "stages": payload.get("stages", {})}
    check_invariants(measurements)

    records = {}
    for name in sorted(measurements):
        records[name] = writer.write_json(
            f"mem_audit_{name}.json",
            {"schema": "regime_lab.fup04_mem_audit_measurement.v1",
             "phase": RUN_ID, "measurement": name,
             "raw_source": {k: v for k, v in raw_sources[name].items() if k != "stages"},
             "headline": measurements[name],
             "raw_stages": raw_sources[name]["stages"]},
            schema="regime_lab.fup04_mem_audit_measurement.v1")

    declaration = {
        "schema": "regime_lab.fup04_report_level_repair.v1",
        "phase": RUN_ID,
        "registration_ref": REGISTRATION_REF,
        "purpose": ("make the full-length native-event deployment account fit the lab's memory "
                    "budget without changing what it measures, by threading the engine's own "
                    "documented output-retention profile through the event route as an opt-in"),
        "root_cause_evidence": {
            "kernel_oom": ("the RA-07 decay deep-dive's M4_CAL worker was OOM-killed at anon-rss "
                           "4.24 GiB on the 613,440-bar deployment frame "
                           "(dmesg 2026-09-20 08:29:01, pid 4110860)"),
            "dominant_accumulator": ("the engine's per-bar audit ledgers retained by the account "
                                     "run, not the search trials and not the frame itself"),
            "reproduced_as_a_measurement": ("under a 4 GiB address-space cap the default profile "
                                            "FAILS and the reduced profile COMPLETES, so the "
                                            "failure is a recorded result rather than a "
                                            "disappearance"),
        },
        "engine_contract": {
            "kwarg": "report_level",
            "documented_values": ["score", "minimal", "standard", "audit", "full"],
            "normalisation": ("quantbt/backends/native_event.py::"
                              "_normalize_native_event_report_level"),
            "default_when_none": "the engine's own default; this repair pins nothing",
            "parity_scope": ("measured on A-SC only; the load-bearing claim is therefore narrower "
                             "than 'all alphas': the equity path and the strategy-level counts "
                             "are identical for the one alpha measured"),
        },
        "opt_in_contract": {
            "default": "None (engine default) everywhere; every pre-existing caller is unchanged",
            "reduced_profile": "score",
            "callers_enabling_by_default": [],
            "provenance": ("run_event_account records both the requested `report_level` and the "
                           "engine-reported `resolved_report_level`, so a reduced-profile run "
                           "cannot be mistaken for a default one"),
        },
        "measurements": {name: {"artifact": records[name]["relpath"],
                                "sha256": records[name]["sha256"], **measurements[name]}
                         for name in sorted(measurements)},
        "invariants_checked_before_writing": [
            "equity exact-equal across profiles (max |diff| == 0.0)",
            "strategy-level fill and entry counts identical across profiles",
            "audit-trail count equals the strategy-level count on the engine default",
            "audit-trail count is 0 under the reduced profile (why scores read the other count)",
            "the reduced profile's peak is smaller than the default's",
            "the 613k-bar deployment account completes, full frame, status EVALUATED",
            "the control (engine default) fails under the same 4 GiB cap",
        ],
        "frozen_component_supersessions": frozen_component_supersessions(),
        "frozen_supersession_ceilings": dict(SUPERSESSION_CEILINGS),
        "protocol_migration": protocol_migration(),
        "timing_disclosure": ("the peak-RSS measurements and the source repair were made on "
                              "2026-09-20 BEFORE this registration entry existed; the registration "
                              "was written the same day, after the measurement and before this "
                              "declaration. Recorded rather than glossed: the measurement makes "
                              "NO economic or market claim, so there is no outcome to have been "
                              "tuned toward, but the ordering is not the registered-before-run "
                              "ideal and is stated as such"),
        "rf05_results_recomputed": False,
        "claim": ("mechanical/technical only: the account path is measurably unchanged under an "
                  "opt-in reduced engine profile, and the full-length deployment account fits the "
                  "budget. No economic, market or edge claim is made or implied"),
        "runtime_seconds": round(time.perf_counter() - started, 3),
    }
    declaration_record = writer.write_json(
        "report_level_memory_repair.json", declaration, schema=declaration["schema"])

    print(json.dumps({
        "run_dir": str(RUN_DIR),
        "declaration": {"sha256": declaration_record["sha256"],
                        "path": declaration_record["relpath"]},
        "measurements": {name: measurements[name].get("outcome", "parity")
                         for name in sorted(measurements)},
        "supersessions": [row["path"] for row in declaration["frozen_component_supersessions"]],
        "ceilings": dict(SUPERSESSION_CEILINGS),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
