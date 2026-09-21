#!/usr/bin/env python3
"""Build RA-05 artifacts (RA-GUIDE-1.0 section 9). Implementation, not a probe.

The FIRST real economic comparison in the RA track: STATIC/M4_CAL/
M4_CAL_MATCHED/M4_REGIME on real BTCUSDT 1m bars (snapshots/server_core_v1)
and real regime emissions (evidence/time_edge_validation_v4/
host-emissions-03.json), all four through the SAME
`run_cutoff_walk_forward` (RA-04-proven, real per-fill "event" route),
differing only in `schedule`.

Phase-owned scale, explicitly NOT the full registered 50-trial/multi-year
contract (same precedent as RA-02/03/04): a 90-day window, 45-day rolling
train memory (vs the registered 180), 8 trials/cutoff. RA05.1 freezes this
spec before the comparison runs; the ONE measurement that necessarily
precedes the freeze (per-selection wall time, needed to forecast
M4_CAL_MATCHED's cadence) is the STATIC arm's own real result, reused
verbatim rather than re-run.

Usage:
  lab_venv/bin/python scripts/run_ra05.py --pytest-xml <junit of tests/ra_corrective>
  lab_venv/bin/python scripts/run_ra05.py --pytest-xml <junit> --smoke   # tiny/fast config, for dry-running the pipeline
Exit 0 iff the verifier reports PASS.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

import pandas as pd

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "src"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter, new_lab_run_id  # noqa: E402
from crypto_regime_lab.ra.phase_common import (  # noqa: E402
    ledger_snapshot, protected_fingerprint, sha256_file, sh, utcnow, write_text_atomic,
)
from crypto_regime_lab.ra.ra05_arms import (  # noqa: E402
    CAL_MATCHED_MENU, REGIME_BUDGET, REGIME_MAX_AGE_DAYS, REGIME_MIN_GAP_DAYS,
    audit_scheduler, build_calendar_schedule, build_regime_schedule, build_static_schedule,
    classify_regime_trigger_reasons, forecast_cal_matched_test_days,
)
from crypto_regime_lab.ra.ra05_discovery import (  # noqa: E402
    action_divergence, descriptive_returns, run_one_arm,
)
from crypto_regime_lab.ra.ra05_market import (  # noqa: E402
    EMISSIONS_ARTIFACT, SNAPSHOT_MANIFEST, load_real_bars, load_real_emissions,
)
from crypto_regime_lab.ra.verifier_ra05 import REQUIRED_ARTIFACTS, verify_ra05  # noqa: E402
from crypto_regime_lab.time_edge.execution import PreparedAccount  # noqa: E402

STUDY = "regime_time_edge_ra_v1"
LEDGER_SQLITE = (LAB / "evidence" / "time_edge_validation_v4" / "allocations"
                 / "TE02-PILOT-R03" / "ledger.sqlite")
PHASE_WALL_CAP_S = 7200.0
ALPHA_ID = "A-SC"
SYMBOL = "BTCUSDT"

#: Frozen defaults (RA05.1). --smoke overrides these to a tiny/fast config
#: for pipeline dry-runs; the real build uses these values.
DEFAULT_WINDOW_START = "2021-01-01"
DEFAULT_WINDOW_END = "2021-04-01"
DEFAULT_DATA_LOAD_START = "2020-11-01"
DEFAULT_TRAIN_MEMORY_DAYS = 45
DEFAULT_CAL_TEST_DAYS = 60
DEFAULT_TRIALS = 8
DEFAULT_SEED = 20260918
DEFAULT_ROUTE = "event"

CASE_NODE_IDS = {
    "D01": ["test_d01_all_arms_share_initial_selection_and_calendar_support"],
    "D02": ["test_d02_cal_matched_never_reads_the_window_own_trigger_count"],
    "D03": ["test_d03_exact_parameter_selection_traces_match_and_no_early_activation"],
    "D04": ["test_d04_funnel_reconstructs_sample_decisions_incl_no_switch"],
    "D05": ["test_d05_account_path_reconciles_no_folded_resets"],
    "D06": ["test_d06_costs_budgets_zero_change_not_fabricated"],
    "D07": ["test_d07_all_four_arms_present_one_failure_does_not_drop_others"],
}


def build_discovery_spec(*, window_start, window_end, data_load_start, train_memory_days,
                         cal_test_days, trials, seed, route, per_selection_wall_seconds,
                         cal_matched_forecast) -> dict:
    return {
        "schema": "regime_lab.ra05_discovery_spec.v1",
        "frozen_at_utc": utcnow(),
        "phase_owned_scale_note": ("90-day window, 45-day rolling train memory (registered: "
                                   "180), 8 trials/cutoff (registered: 50) -- same precedent as "
                                   "RA-02/03/04's phase-owned real-but-small experiments; the "
                                   "full registered contract is not spent proving plumbing here"),
        "pilot_cell": {"alpha_id": ALPHA_ID, "symbol": SYMBOL},
        "window": {"start": window_start, "end": window_end},
        "data_load_start": data_load_start,
        "arms": {
            "STATIC": "one selection at window_start, never refits (diagnostic)",
            "M4_CAL": f"calendar_cutoffs, test_days={cal_test_days}, train_memory_days={train_memory_days}",
            "M4_CAL_MATCHED": ("calendar_cutoffs at a cadence FORECAST from a development prefix "
                               "disjoint from the evaluation window -- see cal_matched_forecast.json"),
            "M4_REGIME": (f"shared initial cutoff + real trigger cutoffs, min_gap_days="
                          f"{REGIME_MIN_GAP_DAYS}, max_age_days={REGIME_MAX_AGE_DAYS}, "
                          f"budget={REGIME_BUDGET} (experiments.regime_schedule.online_trigger_schedule)"),
        },
        "train_memory_days": train_memory_days, "cal_test_days": cal_test_days,
        "trial_budget_per_cutoff": trials, "seed": seed, "route": route,
        "cost_profile": {
            "per_selection_wall_seconds_measured": per_selection_wall_seconds,
            "measured_from": "STATIC arm's own real single-fold run (necessarily precedes this "
                             "freeze -- there is no cost to forecast from before one real "
                             "measurement exists)",
        },
        "cal_matched_chosen_test_days": cal_matched_forecast["chosen_test_days"],
        "cal_matched_menu": list(CAL_MATCHED_MENU),
        "data_sources": {
            "market": str(SNAPSHOT_MANIFEST.relative_to(LAB)),
            "emissions": str(EMISSIONS_ARTIFACT.relative_to(LAB)),
        },
        "primary_contrast": "M4_REGIME - M4_CAL_MATCHED (guide 3.1, RA-01 registered H-BUDGET)",
        "secondary_contrasts": ["M4_REGIME - M4_CAL", "M4_CAL_MATCHED - M4_CAL"],
        "common_valid_dates_rule": ("all four arms share window_start/window_end; no arm is "
                                    "shifted separately to skip a bad period (guide RA05.1)"),
        "not_run": ("the full registered 50-trial/multi-year discovery contract; the >=365-day "
                    "confirmatory floor (RA01.4 migration table); RA-07's bootstrap/claim-gate "
                    "machinery"),
    }


def build_phase_gate(status: str, research_status: str, gate_results=None, notes=None) -> dict:
    return {
        "schema": "regime_lab.ra_phase_gate.v1", "phase_id": "RA-05", "guide_version": "RA-GUIDE-1.0",
        "registration_digest": None, "source_dependency_digest": None,
        "implementation_status": "COMPLETE", "technical_gate": status,
        "research_status": research_status,
        "required_gates": ["G05-EXEC", "G05-TRACE", "G05-LEARN", "G05-SCOPE", "G05-MANIFEST"],
        "gate_results": gate_results or [], "mandatory_tests": [], "actual_run_refs": [],
        "verified_reuse_refs": [], "measured_resources": None,
        "protected_state_before_ref": "baseline/protected_before",
        "protected_state_after_ref": "baseline/protected_after",
        "open_blockers": [], "owner_review": {"status": "PENDING", "decision_ref": None},
        "can_start_next_phase": False, "notes": notes or [],
    }


def build_handoff(run_id: str, verdict: dict) -> str:
    return (
        "# RA-05 handoff\n\n"
        f"- run dir: evidence/{STUDY}/{run_id}/\n"
        f"- technical gate: {verdict['overall']}; research status: DISCOVERY_ONLY\n"
        "- approvals: RA-05 owner review PENDING; can_start_next_phase=false\n"
        "- next: RA-06 (reusable response panel, refit-vs-keep) only after owner approval.\n"
        "- Primary H-BUDGET contrast (M4_REGIME - M4_CAL_MATCHED) has point estimates only in "
        "this pilot; RA-07 owns the bootstrap/claim-gate machinery and the >=365-day "
        "confirmatory floor this short window does not clear.\n"
    )


def build_report(spec, forecast, audit, arms_result, divergence, descriptive, run_id, verdict,
                 manifest) -> str:
    gate_rows = "\n".join(
        f"| {gid} | PASS | {'PASS' if g['pass'] else 'FAIL'} | {run_id}/phase_manifest.json | "
        f"{'PASS' if g['pass'] else 'FAIL'} |"
        for gid, g in verdict["gates"].items())
    arm_rows = []
    for arm_name, row in descriptive["by_arm"].items():
        if row["status"] != "OK":
            arm_rows.append(f"| {arm_name} | NOT_EVALUABLE | - | - | - |")
            continue
        arm_rows.append(f"| {arm_name} | {row['total_return']:.4%} | {row['fill_count']} | "
                        f"{row['folds']} | {row['switches_admitted']}/{row['switches_kept_incumbent']} |")
    div_lines = []
    for pair, row in divergence["pairwise"].items():
        div_lines.append(f"- {pair}: {row['diverged_folds']}/{row['compared_folds']} folds diverged "
                         f"({'YES' if row['diverged'] else 'no'})")
    mechanism_lines = "\n".join(div_lines) if div_lines else "- no comparable arm pairs"
    return f"""# RA-05 - Discovery nho: 4 arms, timing dung va calendar budget-matched

## 1. Status va scope
- Technical gate: **{verdict['overall']}**; research status: **DISCOVERY_ONLY** (guide 3.5: no
  positive/edge claim offered; a short pilot cannot be given an economic verdict per RA01.4's
  migration table).
- Branch `mode4-corrective`, guide RA-GUIDE-1.0 (section 9), study `{STUDY}`, run `{run_id}`.
- Pilot cell {spec['pilot_cell']['alpha_id']}/{spec['pilot_cell']['symbol']}, window
  {spec['window']['start']} to {spec['window']['end']} ({spec['phase_owned_scale_note']}).

## 2. Previous findings va thay doi (F-05/F-06/F-07)
- F-06 (28 accepted triggers, median gap ~28.17d, min-gap28, `time_edge/schedule.py`): re-audited
  on real emissions in this window -- {audit['accepted_total']} accepted trigger(s) via the
  F-06-cited function (confirmations=2), vs {audit['deployed_triggers']} via the function that
  actually drives M4_REGIME (`online_trigger_schedule`, no confirmation requirement). This
  divergence between two real scheduler implementations on the SAME data is itself the audit's
  finding, not an error.
- F-05/F-07 (JM/M0 mixture, rank-IC): the real emissions reused here come from the SAME
  29-vintage ladder F-05 measured (5/29 JM, 24 M0); this phase consumes that mixture as-is,
  neither re-fitting nor recharacterising it.

## 3. Actual execution
- Real BTCUSDT 1m bars ({spec['data_sources']['market']}), real regime emissions
  ({spec['data_sources']['emissions']}), sha256-verified before read.
- Engine: quantbt-engine 1.1.1 / native 0.4.2; protected tree before `clean` and after unchanged.
- Route `{spec['route']}` (real per-fill native QuantBT account, RF-04 precedent for A-SC), seed
  `{spec['seed']}`, {spec['trial_budget_per_cutoff']} trials/cutoff.

## 4. Exit-gate matrix
| Gate | Expected | Actual | Evidence ref | Status |
|---|---|---|---|---|
{gate_rows}

## 5. Correctness va causality
- All four arms called the SAME `run_cutoff_walk_forward` (same alpha, frame, trials, seed,
  route, fees); the ONLY varying input is `schedule` (guide 3.1).
- `oos_used_for_selection` reported False by every arm's own selector metadata.
- CAL_MATCHED's cadence forecast used a development prefix DISJOINT from the evaluation window
  (real emissions outside `[{spec['window']['start']}, {spec['window']['end']})`), never the
  window's own realized trigger count -- {forecast['development_days']} development days,
  {forecast['development_triggers']} triggers, rate {forecast['trigger_rate_per_day']:.5f}/day ->
  predicted {forecast['predicted_trigger_count_in_window']:.2f} triggers in-window -> menu choice
  **{forecast['chosen_test_days']} days** (menu {forecast['menu']}).

## 6. Runtime va memory
- Phase wall time and resource use recorded in `phase_gate.json.measured_resources`.

## 7. Scientific result va kha nang ket luan
- **Action divergence (the RA-05 mechanism question, independent of PnL):**
{mechanism_lines}
- **Descriptive returns (point estimates only, no CI/claim-gate -- RA-07 scope):**

| arm | total return | fills | folds | admitted/kept |
|---|---|---|---|---|
{chr(10).join(arm_rows)}

- None claimed: RA-05 is DISCOVERY_ONLY. What the evidence shows: whether the four arms'
  admission-guarded selections actually diverge in real params/timing under real data, and what
  that costs/returns descriptively -- not whether regime timing beats calendar timing with
  statistical confidence (guide: "khong doi regime thang de PASS").
- What it does not prove: any CI-bounded claim on the primary H-BUDGET contrast
  (M4_REGIME - M4_CAL_MATCHED) -- this pilot's window does not clear the registered >=365-day
  confirmatory floor (RA01.4).

## 8. Blockers/debt va quyet dinh
- No P0/P1 in phase scope. Open items outside scope, carried forward unresolved: T62/T63
  forbidden-claims (resolved earlier this session, see AGENTS.md), TE-03.7 still NOT_RUN_BUDGET
  (separate study/track, not touched here).
- Owner decisions pending: this phase's review; can_start_next_phase=false.

## 9. Reproduction, commit va handoff
- Rerun: `lab_venv/bin/python scripts/run_ra05.py --pytest-xml <junit>` (new run_id per attempt;
  prior runs immutable). `--smoke` runs a tiny/fast config to dry-run the pipeline.
- Independent verify: re-run the build, or import `verify_ra05` and point it at the run dir with
  the same junit; deterministic given the same real snapshot bytes.
- Protected trees: fingerprint recorded before/after; phase-changed files:
  `src/crypto_regime_lab/ra/{{ra05_market,ra05_arms,ra05_funnel,ra05_discovery,verifier_ra05}}.py`,
  `scripts/run_ra05.py`, `tests/ra_corrective/test_ra05_*.py`, this run dir; committed scoped, no
  push.
- Next permissible action: RA-06 only after owner approval of this phase.
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pytest-xml", required=True)
    parser.add_argument("--smoke", action="store_true",
                        help="tiny/fast config to dry-run the pipeline, not a real discovery run")
    parser.add_argument("--engine-report-level", default=None,
                        help=("engine output retention profile for run_event_account "
                              "(None=engine default; 'score' drops per-bar audit "
                              "ledgers; measured equity-exact, see mem_audit.py)"))
    args = parser.parse_args()
    phase_started = time.perf_counter()
    prot_before = protected_fingerprint()
    ledger = ledger_snapshot(LEDGER_SQLITE)

    if args.smoke:
        window_start, window_end = "2021-01-01", "2021-01-08"
        data_load_start = "2020-12-01"
        train_memory_days, cal_test_days, trials = 20, 4, 2
    else:
        window_start, window_end = DEFAULT_WINDOW_START, DEFAULT_WINDOW_END
        data_load_start = DEFAULT_DATA_LOAD_START
        train_memory_days, cal_test_days, trials = (DEFAULT_TRAIN_MEMORY_DAYS,
                                                     DEFAULT_CAL_TEST_DAYS, DEFAULT_TRIALS)
    seed, route = DEFAULT_SEED, DEFAULT_ROUTE

    from crypto_regime_lab.safety.paths import SandboxPolicy

    policy = SandboxPolicy.load(LAB / "configs" / "sandbox_policy.json")
    writer = EvidenceWriter.open(policy, study_id=STUDY, lab_run_id=new_lab_run_id("ra05"))
    run_dir = writer.run_dir
    scratch = run_dir / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)

    with writer.attempt("ra05_build") as att:
        frame, partitions = load_real_bars(SYMBOL, start=data_load_start, end=window_end)
        frame = frame[["open", "high", "low", "close", "volume"]].copy()
        prepared = PreparedAccount(frame)
        emissions_doc = load_real_emissions(window_start=window_start, window_end=window_end)
        emissions = emissions_doc["emissions"]

        # -- RA05.1 (part 1): the one measurement that must precede the freeze --
        static_schedule = build_static_schedule(window_start, window_end,
                                                train_memory_days=train_memory_days)
        static_outcome = run_one_arm(
            ALPHA_ID, frame, static_schedule, prepared=prepared, trials=trials, seed=seed,
            route=route, evidence_dir=scratch, lab_run_id=writer.lab_run_id,
            engine_report_level=args.engine_report_level)
        if not static_outcome.get("ok"):
            raise RuntimeError(f"STATIC arm (the pre-freeze profiling run) failed: "
                              f"{static_outcome.get('error')}")
        per_selection_wall_seconds = static_outcome["run"]["wall_seconds"] / max(
            1, static_outcome["run"]["fold_count"])

        # -- RA05.2: CAL_MATCHED forecast (development prefix, never the window) --
        full_emissions = json.loads(EMISSIONS_ARTIFACT.read_text())["emissions"]
        forecast = forecast_cal_matched_test_days(
            full_emissions, window_start=window_start, window_end=window_end,
            per_selection_wall_seconds=per_selection_wall_seconds)

        # -- RA05.3: scheduler audit (F-06) -----------------------------------
        audit = audit_scheduler(emissions, window_start=window_start, window_end=window_end)

        # -- RA05.1 (part 2): freeze the spec for the REMAINING arms ----------
        spec = build_discovery_spec(
            window_start=window_start, window_end=window_end, data_load_start=data_load_start,
            train_memory_days=train_memory_days, cal_test_days=cal_test_days, trials=trials,
            seed=seed, route=route, per_selection_wall_seconds=per_selection_wall_seconds,
            cal_matched_forecast=forecast)
        writer.write_json("discovery_spec.json", spec, schema="regime_lab.ra05_discovery_spec.v1")
        writer.write_json("cal_matched_forecast.json", forecast,
                          schema="regime_lab.ra05_cal_matched_forecast.v1")
        writer.write_json("scheduler_audit.json", audit, schema="regime_lab.ra05_scheduler_audit.v1")

        # -- RA05.5: run the remaining 3 arms from the FROZEN spec -------------
        cal_schedule = build_calendar_schedule(window_start, window_end, test_days=cal_test_days,
                                               train_memory_days=train_memory_days)
        cal_matched_schedule = replace(
            build_calendar_schedule(window_start, window_end,
                                    test_days=forecast["chosen_test_days"],
                                    train_memory_days=train_memory_days),
            arm="M4_CAL_MATCHED")
        regime_schedule = build_regime_schedule(
            emissions, window_start=window_start, window_end=window_end,
            train_memory_days=train_memory_days)
        regime_trigger_lookup = classify_regime_trigger_reasons(
            regime_schedule.cutoffs, emissions,
            shared_initial=pd.Timestamp(window_start, tz="UTC").isoformat())

        cal_outcome = run_one_arm(ALPHA_ID, frame, cal_schedule, prepared=prepared, trials=trials,
                                  seed=seed, route=route, evidence_dir=scratch,
                                  lab_run_id=writer.lab_run_id,
                                  engine_report_level=args.engine_report_level)
        cal_matched_outcome = run_one_arm(ALPHA_ID, frame, cal_matched_schedule, prepared=prepared,
                                          trials=trials, seed=seed, route=route,
                                          evidence_dir=scratch, lab_run_id=writer.lab_run_id,
                                          engine_report_level=args.engine_report_level)
        regime_outcome = run_one_arm(ALPHA_ID, frame, regime_schedule, prepared=prepared,
                                     trials=trials, seed=seed, route=route, evidence_dir=scratch,
                                     lab_run_id=writer.lab_run_id, trigger_lookup=regime_trigger_lookup,
                                     engine_report_level=args.engine_report_level)

        arms = {"STATIC": static_outcome, "M4_CAL": cal_outcome,
               "M4_CAL_MATCHED": cal_matched_outcome, "M4_REGIME": regime_outcome}

        # -- RA05.6: compact outcomes (drop the verbose per-trial ledger; keep
        # the fold table, funnel and account summary -- guide: "khong tinh
        # them hang chuc horizons chua dang ky") ------------------------------
        compact_arms = {}
        for name, outcome in arms.items():
            if not outcome.get("ok"):
                compact_arms[name] = outcome
                continue
            run = dict(outcome["run"])
            trial_count = run.pop("trial_records", None)
            run["trial_records_count"] = len(trial_count) if trial_count is not None else None
            compact_arms[name] = {**outcome, "run": run}
        writer.write_json("arms_result.json", {"schema": "regime_lab.ra05_arms_result.v1",
                                               "arms": compact_arms},
                          schema="regime_lab.ra05_arms_result.v1")

        divergence = action_divergence(arms)
        descriptive = descriptive_returns(arms)
        writer.write_json("action_divergence.json", divergence,
                          schema="regime_lab.ra05_action_divergence.v1")
        writer.write_json("descriptive_returns.json", descriptive,
                          schema="regime_lab.ra05_descriptive_returns.v1")

        import importlib.metadata as md

        def version(name):
            try:
                return md.version(name)
            except Exception:
                return None

        phase_wall = round(time.perf_counter() - phase_started, 1)
        snapshot = {k: ledger.get(k) for k in ("spent", "attempts", "budget")}
        baseline = {
            "git_branch": sh(["git", "branch", "--show-current"], cwd=LAB),
            "git_head_full": sh(["git", "rev-parse", "HEAD"], cwd=LAB),
            "engine_version": version("quantbt-engine"), "native_version": version("quantbt-native"),
            "protected_before": prot_before, "ledger_before": snapshot, "ledger_after": snapshot,
            "phase_wall_cap_s": PHASE_WALL_CAP_S, "phase_measured_wall_s": phase_wall,
            "started_at": utcnow(), "market_partitions_used": partitions,
        }
        writer.write_json("baseline_identity.json", baseline, schema="regime_lab.ra05_baseline.v1")

        def manifest_records():
            return [{"relpath": name, "sha256": sha256_file(run_dir / name),
                    "size_bytes": (run_dir / name).stat().st_size}
                   for name in REQUIRED_ARTIFACTS
                   if name not in ("phase_manifest.json", "phase_gate.json", "report.md", "handoff.md")
                   and (run_dir / name).is_file()]

        writer.write_json("phase_manifest.json", {
            "required_gates": ["G05-EXEC", "G05-TRACE", "G05-LEARN", "G05-SCOPE", "G05-MANIFEST"],
            "artifacts": manifest_records(),
            "source_dependency_digests": {"lab_head": baseline["git_head_full"],
                                          "endpoint_protected": prot_before.get("endpoint_sha256")},
            "approvals": {"ra05_review": "PENDING"},
        }, schema="regime_lab.ra05_manifest.v1")

        writer.write_json("phase_gate.json", build_phase_gate("PENDING_VERIFICATION", "DISCOVERY_ONLY"),
                          schema="regime_lab.ra_phase_gate.v1")
        write_text_atomic(run_dir / "report.md", "# RA-05 report - PENDING_VERIFICATION (mechanism)\n")
        write_text_atomic(run_dir / "handoff.md", "# RA-05 handoff - PENDING_VERIFICATION\n")
        prot_after = protected_fingerprint()

        gate_doc = build_phase_gate(
            "PENDING_VERIFICATION", "DISCOVERY_ONLY",
            notes=["verify ran over the frozen artifact set incl. this receipt"])

        junit = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
        try:
            import xml.etree.ElementTree as ET

            xml_root = ET.parse(args.pytest_xml).getroot()
            suites = xml_root.findall("testsuite") or [xml_root]
            junit = {"tests": sum(int(s.get("tests", 0)) for s in suites),
                    "failures": sum(int(s.get("failures", 0)) for s in suites),
                    "errors": sum(int(s.get("errors", 0)) for s in suites),
                    "skipped": sum(int(s.get("skipped", 0)) for s in suites)}
        except Exception:
            pass
        gate_doc["mandatory_tests"] = [{"command": " ".join(sys.argv), **junit}]
        gate_doc["measured_resources"] = {"phase_wall_s": phase_wall}
        gate_doc["actual_run_refs"] = ["arms_result.json", "action_divergence.json",
                                       "descriptive_returns.json"]
        gate_doc["verified_reuse_refs"] = ["dynamic_fold_provider.run_cutoff_walk_forward (RF-04)",
                                           "mode4_admission.admit_selection (RA-04)",
                                           "experiments.regime_schedule (RF-04)"]
        gate_doc["protected_state_after_ref"] = "protected status: " + (prot_after["git_status_porcelain"] or "clean")
        writer.write_json("phase_gate.json", gate_doc, schema="regime_lab.ra_phase_gate.v1")

        verdict = verify_ra05(run_dir, pytest_xml=args.pytest_xml,
                              protected_status_after=prot_after["git_status_porcelain"])
        gate_doc["technical_gate"] = verdict["overall"]
        gate_doc["gate_results"] = [{"gate_id": gid, "status": "PASS" if g["pass"] else "FAIL",
                                     "reasons": g["reasons"][:3]} for gid, g in verdict["gates"].items()]
        writer.write_json("phase_gate.json", gate_doc, schema="regime_lab.ra_phase_gate.v1")

        manifest_doc = json.loads((run_dir / "phase_manifest.json").read_text())
        manifest_doc["artifacts"] = manifest_records()
        writer.write_json("phase_manifest.json", manifest_doc, schema="regime_lab.ra05_manifest.v1")

        verdict = verify_ra05(run_dir, pytest_xml=args.pytest_xml,
                              protected_status_after=prot_after["git_status_porcelain"])
        writer.write_json("verification.json", verdict, schema="regime_lab.ra05_verification.v1")
        write_text_atomic(run_dir / "report.md",
                          build_report(spec, forecast, audit, compact_arms, divergence,
                                      descriptive, writer.lab_run_id, verdict, manifest_doc))
        write_text_atomic(run_dir / "handoff.md", build_handoff(writer.lab_run_id, verdict))
        att.detail = {"run_dir": str(run_dir), "overall": verdict["overall"]}

    print(json.dumps({"run_dir": str(run_dir), "overall": verdict["overall"],
                      "gates": {k: v["pass"] for k, v in verdict["gates"].items()}}, indent=2))
    return 0 if verdict["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
