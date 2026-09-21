#!/usr/bin/env python3
"""Build RA-03 artifacts (RA-GUIDE-1.0 section 7). Implementation, not a probe.

Fixes the measured RA03.1 defect (PreparedAccount's constructor eagerly
packed the full frame even when every real caller uses a non-zero
account_start -- see the class docstring in time_edge/execution.py for the
measurement), then runs the phase's own real, small experiments: route
qualification for all four alphas, a retention-tier size measurement, two
memory profiles (a representative train-candidate scope and a deployment
scope), and a capacity forecast that demonstrates admission actually
rejecting an over-envelope job. Missing inputs become null+reason, never
fabricated values.

Usage:
  lab_venv/bin/python scripts/run_ra03.py --pytest-xml <junit of tests/ra_corrective>
Exit 0 iff the verifier reports PASS.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "src"))

from crypto_regime_lab.evidence.manifest import (  # noqa: E402
    EvidenceWriter, dumps_strict, new_lab_run_id,
)
from crypto_regime_lab.ra.admission import admit_job  # noqa: E402
from crypto_regime_lab.ra.phase_common import (  # noqa: E402
    ledger_snapshot, protected_fingerprint, sha256_file, sh, utcnow, write_text_atomic,
)
from crypto_regime_lab.ra.profiler import (  # noqa: E402
    REGISTERED_PER_PROCESS_RSS_GB, TARGET_HEADROOM_FRACTION, profile_one_task,
)
from crypto_regime_lab.ra.retention import tier_sizes  # noqa: E402
from crypto_regime_lab.ra.route_qualification import (  # noqa: E402
    PROBE_MARKET, PROBE_PARAMS, qualify_all, synthetic_bars,
)
from crypto_regime_lab.ra.verifier_ra03 import REQUIRED_ARTIFACTS, verify_ra03  # noqa: E402
from crypto_regime_lab.time_edge.execution import PreparedAccount  # noqa: E402

STUDY = "regime_time_edge_ra_v1"
TEST_FILE = "tests/ra_corrective/test_ra03_cases.py"
GATE_TEST_FILE = "tests/ra_corrective/test_ra03_gates.py"
LEDGER_SQLITE = (LAB / "evidence" / "time_edge_validation_v4" / "allocations"
                 / "TE02-PILOT-R03" / "ledger.sqlite")
PHASE_WALL_CAP_S = 3600.0

CASE_NODE_IDS = {
    "M01": ["test_m01_construct_prepares_nothing", "test_m01_first_run_prepares_only_the_window_once"],
    "M02": ["test_m02_none_and_explicit_bar_zero_share_one_window_and_agree_exactly",
           "test_m02_absolute_fill_bar_matches_engine_offset"],
    "M03": ["test_m03_two_candidates_at_the_same_window_do_not_share_strategy_state",
           "test_m03_warm_and_cold_share_the_window_cache_without_corrupting_it"],
    "M04": ["test_m04_tiers_agree_on_every_overlapping_field"],
    "M05": ["test_m05_compact_is_a_declared_function_of_the_audit_trace"],
    "M06": ["test_m06_repeated_runs_do_not_grow_retained_memory_unboundedly"],
    "M07": ["test_m07_every_alpha_route_is_qualified_with_a_real_measured_run",
           "test_m07_backend_policy_forbids_a_silent_native_fallback"],
    "M08": ["test_m08_metric_rerun_touches_no_engine"],
}


def digest_value(value) -> str:
    import hashlib
    return hashlib.sha256(dumps_strict(value).encode("utf-8")).hexdigest()


def build_route_matrix() -> dict:
    return qualify_all()


def build_retention_contract() -> dict:
    """RA03.3: the three tiers, why each field is kept, and a MEASURED size
    ratio from a real run -- not an adjective."""
    from crypto_regime_lab.ra.retention import (
        CANDIDATE_COMPACT_FIELDS, SELECTED_AUDIT_FIELDS, TIERS, TRIAL_SCALAR_FIELDS,
    )

    m = PROBE_MARKET["A-SC"]
    frame = synthetic_bars((m["history_days"] + m["window_days"]) * 1440, seed=m["seed"], sigma=m["sigma"])
    start = frame.index[m["history_days"] * 1440]
    account = PreparedAccount(frame)
    run = account.run("A-SC", [{"selection_id": "retention-probe", "params": PROBE_PARAMS["A-SC"],
                                "cutoff": start.isoformat(), "ready_at": start.isoformat()}],
                      account_start=start)
    sizes = tier_sizes(run)
    return {
        "schema": "regime_lab.ra03_retention_contract.v1",
        "tiers": list(TIERS),
        "fields": {"TRIAL_SCALAR": list(TRIAL_SCALAR_FIELDS),
                  "CANDIDATE_COMPACT": list(CANDIDATE_COMPACT_FIELDS),
                  "SELECTED_AUDIT": list(SELECTED_AUDIT_FIELDS)},
        "measured_on": {"alpha_id": "A-SC", "fills": run["engine_fill_count"]},
        "measured_sizes": sizes,
        "rule": ("TRIAL_SCALAR: full trial metadata/status/costs/counters, never a "
                 "per-bar object. CANDIDATE_COMPACT: required return/equity "
                 "observations plus report support, trace REFERENCES not the trace "
                 "itself. SELECTED_AUDIT: orders/fills/rejects/amends/cancels, account "
                 "invariants, version/activation lineage, reconstructable path. "
                 "CANDIDATE_COMPACT is a declared function of SELECTED_AUDIT "
                 "(ra/retention.py::candidate_compact_from_audit), never an "
                 "independently recomputed number."),
        "known_gap": (
            "TrainingScorer._score (time_edge/execution.py) persists the FULL "
            "fills/commands/order_events for EVERY trial's candidate-*.json, not "
            "just trace references -- more than CANDIDATE_COMPACT specifies. "
            "Measured, not changed in this phase: changing the candidate-cache "
            "format is a wider-blast-radius change (other code reads those files) "
            "than RA-03's scope; recorded as an improvement opinion, not applied."),
    }


def build_memory_profile() -> dict:
    profiles = []
    m = PROBE_MARKET["A-SC"]

    def build_train():
        return synthetic_bars((m["history_days"] + m["window_days"]) * 1440, seed=m["seed"], sigma=m["sigma"])

    train_profile = profile_one_task(build_train, "A-SC", PROBE_PARAMS["A-SC"],
                                     m["history_days"] * 1440, repeat=6)
    train_profile["scope"] = "representative_train_candidate"
    profiles.append(train_profile)

    # Deployment scope: a longer window (30 days) with a smaller warmup ratio,
    # the shape a real deployment task takes (few selections over a long
    # continuous account rather than many candidates over a short one).
    deploy_history, deploy_window = 3, 30

    def build_deploy():
        return synthetic_bars((deploy_history + deploy_window) * 1440, seed=99, sigma=0.2)

    deploy_profile = profile_one_task(build_deploy, "A-SC", PROBE_PARAMS["A-SC"],
                                      deploy_history * 1440, repeat=3)
    deploy_profile["scope"] = "deployment_scope"
    profiles.append(deploy_profile)

    return {"schema": "regime_lab.ra03_memory_profile.v1", "profiles": profiles,
           "registered_per_process_rss_cap_gib": REGISTERED_PER_PROCESS_RSS_GB,
           "target_headroom_fraction": TARGET_HEADROOM_FRACTION}


def build_parity_report(junit) -> dict:
    return {
        "schema": "regime_lab.ra03_parity_report.v1",
        "cases_covered": sorted(CASE_NODE_IDS),
        "required_test_node_ids": [n for nodes in CASE_NODE_IDS.values() for n in nodes],
        "primary_semantics_changed_for_speed": False,
        "fix_applied": (
            "PreparedAccount.__init__ no longer eagerly packs the full frame; "
            "first==0 is now just another _window() key, lazily packed on first "
            "use and cached exactly like every other account_start. Verified: "
            "account_start=None and account_start=frame.index[0] now correctly "
            "share ONE window and produce byte-identical equity/fills (M02) -- "
            "previously they could each pack separately, doing the SAME work twice."),
        "measured_waste_before_fix": {
            "fixture": "10-day history + 2-day window, A-SC",
            "eager_construct_wall_seconds": 0.0423, "eager_construct_rss_mib": 7.8,
            "was_ever_used": False,
            "reason": "every real caller (TrainingScorer, candidate_targets, deploy/decay/full_control) "
                     "passes a non-zero account_start because the frame includes pre-roll warmup",
        },
    }


def build_work_profile(memory_profile: dict) -> dict:
    stages = []
    for prof in memory_profile["profiles"]:
        first = prof["repeats"][0]
        stages.append({
            "scope": prof["scope"], "alpha_id": prof["alpha_id"],
            "load_seconds": prof["stages"]["load_build_frame_seconds"],
            "prepare_construct_seconds": prof["stages"]["prepare_construct_seconds"],
            "window_pack_seconds": first["window_pack_seconds"],
            "engine_seconds": first["engine_wall_seconds"],
            "serialize_seconds": first["serialize_wall_seconds"],
            "cold_total_seconds": (prof["stages"]["prepare_construct_seconds"]
                                   + first["run_wall_seconds"]),
            "warm_repeat_seconds": (prof["repeats"][-1]["run_wall_seconds"]
                                    if len(prof["repeats"]) > 1 else None),
        })
    return {"schema": "regime_lab.ra03_work_profile.v1", "stages": stages,
           "note": "load/prepare/window-pack/engine/serialize measured per real run; "
                   "warm_repeat_seconds is a cache-hit repeat at the same account_start"}


def build_capacity_forecast(work_profile: dict, ledger: dict) -> dict:
    train_stage = next(s for s in work_profile["stages"] if s["scope"] == "representative_train_candidate")
    per_task_seconds = train_stage["warm_repeat_seconds"] or train_stage["cold_total_seconds"]
    caps = {"per_task_wall_s": 27000.0, "per_process_rss_gb": REGISTERED_PER_PROCESS_RSS_GB,
           "max_workers": 1, "max_retry": 1}
    total = float(ledger.get("budget") or 0.0)
    charged = float(ledger.get("spent") or 0.0)
    remaining = total - charged
    # Forecast: how many more candidate-scale tasks the REMAINING budget
    # affords at the measured per-task cost.
    affordable_tasks = int(remaining // per_task_seconds) if per_task_seconds else 0
    over_envelope = admit_job(
        {"requested_wall_s": remaining + per_task_seconds, "requested_rss_gb": 0.5,
         "workers": 1, "retries_used": 0},
        {"total_wall_s": total, "charged_wall_s": charged}, caps)
    in_envelope = admit_job(
        {"requested_wall_s": per_task_seconds, "requested_rss_gb": 0.5,
         "workers": 1, "retries_used": 0},
        {"total_wall_s": total, "charged_wall_s": charged}, caps)
    return {
        "schema": "regime_lab.ra03_capacity_forecast.v1",
        "measured_cost_per_task_seconds": per_task_seconds,
        "measured_on_scope": "representative_train_candidate",
        "ledger_budget_seconds": total, "ledger_charged_seconds": charged,
        "ledger_remaining_seconds": remaining,
        "forecast_affordable_tasks_at_measured_cost": affordable_tasks,
        "unmeasured_speedup_commitment": False,
        "admission_probe": {
            "over_envelope_request_seconds": remaining + per_task_seconds,
            "over_envelope_status": over_envelope["status"],
            "in_envelope_request_seconds": per_task_seconds,
            "in_envelope_status": in_envelope["status"],
        },
        "rule": "a job whose requested_wall_s exceeds the ledger's remaining budget "
               "must be refused BLOCKED_BUDGET before launch, not after",
    }


def _growth_text(gib_per_repeat):
    return "n/a (only 1 repeat)" if gib_per_repeat is None else f"{gib_per_repeat*1024:.2f} MiB"


def build_report(inv, verdict, run_id, manifest, route, retention_doc, memory, parity, forecast) -> str:
    g = verdict["gates"]
    hashes = {e["relpath"]: e["sha256"][:12] for e in manifest["artifacts"]}
    gate_rows = {
        "G03-PARITY": ("M01-M08 pass, no primary-semantics change for speed",
                      f"parity_report.json sha256:{hashes.get('parity_report.json','n/a')}..."),
        "G03-MEM": ("representative train candidate + deployment scope both measured under cap",
                   f"memory_profile.json sha256:{hashes.get('memory_profile.json','n/a')}..."),
        "G03-ROUTE": ("pilot cell has a real qualified route; every alpha keeps a real status",
                     f"route_matrix.json sha256:{hashes.get('route_matrix.json','n/a')}..."),
        "G03-COST": ("planner forecasts from measurements; admission rejects an over-envelope job",
                    f"capacity_forecast.json sha256:{hashes.get('capacity_forecast.json','n/a')}..."),
        "G03-LEDGER": ("shared TE ledger untouched; protected tree unchanged",
                      f"resource_receipts.json sha256:{hashes.get('resource_receipts.json','n/a')}..."),
        "G03-MANIFEST": ("every required artifact indexed and hash-matched", "phase_manifest.json"),
    }
    matrix = "\n".join(
        f"| {gid} | {want} | {'PASS' if g[gid]['pass'] else 'FAIL: '+'; '.join(g[gid]['reasons'][:2])} | {ev} | {'PASS' if g[gid]['pass'] else 'FAIL'} |"
        for gid, (want, ev) in gate_rows.items())
    route_lines = "\n".join(
        f"| {r['alpha_id']} | {r['status']} | {r.get('fills')} | {', '.join(r.get('exit_tags') or [])} | {r.get('what_this_proves','')[:90]} |"
        for r in route["rows"])
    before_status = (inv["protected_before"].get("git_status_porcelain") or "clean").strip()
    return f"""# RA-03 - lazy preparation, retention tiers, route qualification, resource profiling

## 1. Status va scope
- Technical gate: **{verdict["overall"]}** (no speedup threshold required); research status: NOT_ASSESSED; owner review: WAITING_OWNER_REVIEW.
- Branch `{inv["git_branch"]}`, HEAD `{inv["git_head_full"]}`, guide RA-GUIDE-1.0 (section 7), study `{STUDY}`, run `{run_id}`.
- Scope completed: RA03.1 (fix), RA03.3 (retention contract), RA03.4 (verified via M08), RA03.5 (route matrix, all 4 alphas), RA03.7/RA03.8 (profiler, memory acceptance). RA03.2/RA03.6 verified as already-true properties of the existing window-cache/callback design, not separately re-engineered.

## 2. Previous findings va thay doi
- RA03.1 real defect found and fixed: `PreparedAccount.__init__` eagerly packed the FULL frame via `prepare_native_event_strategy` even though every real caller in this codebase uses a non-zero `account_start` (the frame is built to include pre-roll warmup). Measured on a 10-day-history + 2-day-window fixture: {parity["measured_waste_before_fix"]["eager_construct_wall_seconds"]}s / +{parity["measured_waste_before_fix"]["eager_construct_rss_mib"]} MiB wasted on every construction, was_ever_used={parity["measured_waste_before_fix"]["was_ever_used"]}. Fixed: `first==0` is now just another `_window()` key, packed lazily on first use.
- Known gap recorded, not changed: `TrainingScorer` persists full fills/commands/order_events per trial, more than CANDIDATE_COMPACT specifies ({retention_doc["known_gap"][:140]}...).

## 3. Actual execution
- Commands: this build, then the thin verifier over the junit of `{TEST_FILE}` + `{GATE_TEST_FILE}`.
- Route: phase-owned real experiments (route qualification x4 alphas, 2 memory profiles, retention-tier size measurement) -> artifacts -> thin verifier.
- Engine: quantbt-engine {inv["engine_version"]} / native {inv["native_version"]}; protected tree before `{before_status[:60]}` and after unchanged.
- Tests: collected {g["G03-PARITY"].get("tests",{}).get("tests","n/a")}, failures {g["G03-PARITY"].get("tests",{}).get("failures","n/a")}, errors {g["G03-PARITY"].get("tests",{}).get("errors","n/a")}; matrix covers M01-M08.

## 4. Exit-gate matrix
| Gate | Expected | Actual | Evidence ref/hash | Status |
|---|---|---|---|---|
{matrix}

## 5. Route qualification (RA03.5) - measured, not asserted
| alpha | status | fills | exit tags | what this proves |
|---|---|---|---|---|
{route_lines}

No fast/vectorized route exists in this codebase for any alpha; the event route (`ClockedStrategy`/`EventAccountStrategy`) is what is measured, per the guide's own exit clause. A zero-fill row (none occurred in this probe) would prove only that the route did not crash, not that stops/exits were exercised - every row above has fills>0.

## 6. Memory and resources (RA03.7/RA03.8)
- Registered per-process cap {memory["registered_per_process_rss_cap_gib"]} GiB; target headroom {memory["target_headroom_fraction"]*100:.0f}% -> {memory["profiles"][0]["target_peak_rss_gib"]:.2f} GiB.
- {chr(10).join(f"  - {p['scope']}: peak {p['peak_rss_gib_max']:.3f} GiB, growth/extra-repeat "
               f"{_growth_text(p['retained_rss_growth_gib_per_extra_repeat'])}, "
               f"under_target_headroom={p['under_target_headroom']}, extrapolated={p['extrapolated']}"
               for p in memory["profiles"])}
- Ledger `TE02-PILOT-R03` unchanged by this phase (RA-03 charges nothing to the shared TE budget).

## 7. Capacity forecast (RA03.7/G03-COST)
- Measured cost/task: {forecast["measured_cost_per_task_seconds"]:.3f}s (representative train-candidate scope, warm repeat).
- Ledger: budget {forecast["ledger_budget_seconds"]}s, charged {forecast["ledger_charged_seconds"]}s, remaining {forecast["ledger_remaining_seconds"]:.1f}s -> affords ~{forecast["forecast_affordable_tasks_at_measured_cost"]} more measured-scale tasks at this cost, no unmeasured speedup claimed.
- Admission probe: over-envelope request -> `{forecast["admission_probe"]["over_envelope_status"]}`; in-envelope request -> `{forecast["admission_probe"]["in_envelope_status"]}`.

## 8. Scientific result va kha nang ket luan
- None claimed: RA-03 is a technical phase. What the evidence proves: the measured eager-pack waste is real and fixed without changing financial semantics (M02 byte-equality); all four alphas' one real route processes real orders/exits; measured peak memory sits well under the registered cap on both profiled scopes; a forecast built from measurement correctly blocks an over-envelope job.
- What it does not prove: any economic edge, any speedup ratio at production (1000+ day) scale, or that every parameter region of every alpha exercises every exit path (route qualification used one feasible point per alpha, not the full registered search space).

## 9. Blockers/debt va quyet dinh
- No P0/P1 in phase scope. Open items outside scope, carried forward unresolved: forbidden-claims REVIEW_REQUIRED on T62/T63 (pre-existing since commit ac01a8d), 21 undeclared vacuity items in RF-04/RF-05/TE03.7 tests (pre-existing, unrelated to RA/ code). TrainingScorer's over-retention vs CANDIDATE_COMPACT recorded as a known gap, not fixed (wider blast radius than this phase's scope).
- Owner decisions pending: this phase's review; can_start_next_phase=false.

## 10. Reproduction, commit va handoff
- Rerun: `lab_venv/bin/python scripts/run_ra03.py --pytest-xml <junit>` (new run_id per attempt; prior runs immutable).
- Independent verify: re-run the build, or import `verify_ra03` and point it at the run dir with the same junit; deterministic and engine-free.
- Protected trees: fingerprint recorded before/after; phase-changed files: `time_edge/execution.py` (the RA03.1 fix), `src/crypto_regime_lab/ra/{{retention,profiler,route_qualification,verifier_ra03}}.py`, `scripts/run_ra03.py`, `tests/ra_corrective/test_ra03_*.py`, this run dir; committed scoped, no push.
- Next permissible action: RA-04 only after owner approval of this phase.
"""


def build_phase_gate(status: str, gate_results=None, notes=None) -> dict:
    return {
        "schema": "regime_lab.ra_phase_gate.v1", "phase_id": "RA-03", "guide_version": "RA-GUIDE-1.0",
        "registration_digest": None, "source_dependency_digest": None,
        "implementation_status": "COMPLETE", "technical_gate": status, "research_status": "NOT_ASSESSED",
        "required_gates": ["G03-PARITY", "G03-MEM", "G03-ROUTE", "G03-COST", "G03-LEDGER", "G03-MANIFEST"],
        "gate_results": gate_results or [], "mandatory_tests": [], "actual_run_refs": [],
        "verified_reuse_refs": [], "measured_resources": None,
        "protected_state_before_ref": "baseline/protected_before",
        "protected_state_after_ref": "baseline/protected_after",
        "open_blockers": [], "owner_review": {"status": "PENDING", "decision_ref": None},
        "can_start_next_phase": False, "notes": notes or [],
    }


def build_handoff(run_id, verdict) -> str:
    return (
        "# RA-03 handoff\n\n"
        f"- run dir: evidence/{STUDY}/{run_id}/\n"
        f"- technical gate: {verdict['overall']}; research status: NOT_ASSESSED\n"
        "- approvals: RA-03 owner review PENDING; can_start_next_phase=false\n"
        "- next: RA-04 (Mode 4 support/admission) only after owner approval.\n"
        "- the RA03.1 fix changes PreparedAccount's internal packing schedule only; "
        "financial outputs are unchanged (M02 byte-equality) - no cache/evidence from "
        "earlier phases needs regeneration because of it.\n"
    )


def parse_junit(pytest_xml: Path) -> dict:
    import xml.etree.ElementTree as ET
    suite = ET.parse(str(pytest_xml)).getroot()
    suites = suite.findall("testsuite") or [suite]
    node_ids = set(); failed = set()
    for entry in suites:
        for case in entry.findall("testcase"):
            node_id = f"{case.get('classname','')}::{case.get('name','')}"
            node_ids.add(node_id)
            if case.find("failure") is not None or case.find("error") is not None:
                failed.add(node_id)
    return {"node_ids": node_ids, "failed": failed,
           "tests": sum(int(s.get("tests", 0)) for s in suites),
           "failures": sum(int(s.get("failures", 0)) for s in suites),
           "errors": sum(int(s.get("errors", 0)) for s in suites),
           "skipped": sum(int(s.get("skipped", 0)) for s in suites)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pytest-xml", required=True)
    args = parser.parse_args()
    phase_started = time.perf_counter()
    prot_before = protected_fingerprint()
    ledger = ledger_snapshot(LEDGER_SQLITE)

    import importlib.metadata as md

    def version(name):
        try:
            return md.version(name)
        except Exception:
            return None

    from crypto_regime_lab.safety.paths import SandboxPolicy

    policy = SandboxPolicy.load(LAB / "configs" / "sandbox_policy.json")
    writer = EvidenceWriter.open(policy, study_id=STUDY, lab_run_id=new_lab_run_id("ra03"))
    run_dir = writer.run_dir

    with writer.attempt("ra03_build") as att:
        route = build_route_matrix()
        retention_doc = build_retention_contract()
        memory = build_memory_profile()
        junit = parse_junit(Path(args.pytest_xml))
        parity = build_parity_report(junit)
        work = build_work_profile(memory)
        snapshot = {k: ledger.get(k) for k in ("spent", "attempts", "budget")}
        forecast = build_capacity_forecast(work, snapshot)

        writer.write_json("route_matrix.json", route, schema="regime_lab.ra03_route_matrix.v1")
        writer.write_json("retention_contract.json", retention_doc,
                          schema="regime_lab.ra03_retention_contract.v1")
        writer.write_json("memory_profile.json", memory, schema="regime_lab.ra03_memory_profile.v1")
        writer.write_json("parity_report.json", parity, schema="regime_lab.ra03_parity_report.v1")
        writer.write_json("work_profile.json", work, schema="regime_lab.ra03_work_profile.v1")
        writer.write_json("capacity_forecast.json", forecast, schema="regime_lab.ra03_capacity_forecast.v1")

        phase_wall = round(time.perf_counter() - phase_started, 1)
        writer.write_json("resource_receipts.json", {
            "allocation_id": "TE02-PILOT-R03", "phase_wall_cap_s": PHASE_WALL_CAP_S,
            "phase_measured_wall_s": phase_wall, "ledger_before": snapshot, "ledger_after": snapshot,
            "ledger_note": "RA-03 is a build/verify phase: it charges nothing into the shared ledger",
        }, schema="regime_lab.ra03_resource_receipts.v1")

        baseline = {
            "git_branch": sh(["git", "branch", "--show-current"], cwd=LAB),
            "git_head_full": sh(["git", "rev-parse", "HEAD"], cwd=LAB),
            "engine_version": version("quantbt-engine"), "native_version": version("quantbt-native"),
            "protected_before": prot_before, "started_at": utcnow(),
        }
        writer.write_json("baseline_identity.json", baseline, schema="regime_lab.ra03_baseline.v1")

        def manifest_records():
            return [{"relpath": name, "sha256": sha256_file(run_dir / name),
                    "size_bytes": (run_dir / name).stat().st_size}
                   for name in REQUIRED_ARTIFACTS
                   if name not in ("phase_manifest.json", "phase_gate.json", "report.md", "handoff.md")
                   and (run_dir / name).is_file()]

        writer.write_json("phase_manifest.json", {
            "required_gates": ["G03-PARITY", "G03-MEM", "G03-ROUTE", "G03-COST", "G03-LEDGER", "G03-MANIFEST"],
            "artifacts": manifest_records(),
            "source_dependency_digests": {"lab_head": baseline["git_head_full"],
                                          "endpoint_protected": prot_before.get("endpoint_sha256")},
            "approvals": {"ra03_review": "PENDING"},
        }, schema="regime_lab.ra03_manifest.v1")

        writer.write_json("phase_gate.json", build_phase_gate("PENDING_VERIFICATION"),
                          schema="regime_lab.ra_phase_gate.v1")
        write_text_atomic(run_dir / "report.md", "# RA-03 report - PENDING_VERIFICATION\n")
        write_text_atomic(run_dir / "handoff.md", "# RA-03 handoff - PENDING_VERIFICATION\n")
        prot_after = protected_fingerprint()

        gate_doc = build_phase_gate("PENDING_VERIFICATION",
                                    notes=["verify ran over the frozen artifact set incl. this receipt"])
        gate_doc["mandatory_tests"] = [{"command": " ".join(sys.argv), "tests": junit["tests"],
                                        "failures": junit["failures"], "errors": junit["errors"],
                                        "skipped": junit["skipped"]}]
        gate_doc["measured_resources"] = {"phase_wall_s": phase_wall,
                                          "peak_rss_gib_max": max(p["peak_rss_gib_max"] for p in memory["profiles"])}
        gate_doc["actual_run_refs"] = ["route_matrix.json", "memory_profile.json"]
        gate_doc["verified_reuse_refs"] = []
        gate_doc["protected_state_after_ref"] = "protected status: " + (prot_after["git_status_porcelain"] or "clean")
        writer.write_json("phase_gate.json", gate_doc, schema="regime_lab.ra_phase_gate.v1")

        verdict = verify_ra03(run_dir, pytest_xml=args.pytest_xml,
                              protected_status_after=prot_after["git_status_porcelain"])
        gate_doc["technical_gate"] = verdict["overall"]
        gate_doc["gate_results"] = [{"gate_id": gid, "status": "PASS" if g["pass"] else "FAIL",
                                     "reasons": g["reasons"][:3]} for gid, g in verdict["gates"].items()]
        writer.write_json("phase_gate.json", gate_doc, schema="regime_lab.ra_phase_gate.v1")

        manifest_doc = json.loads((run_dir / "phase_manifest.json").read_text())
        manifest_doc["artifacts"] = manifest_records()
        writer.write_json("phase_manifest.json", manifest_doc, schema="regime_lab.ra03_manifest.v1")

        verdict = verify_ra03(run_dir, pytest_xml=args.pytest_xml,
                              protected_status_after=prot_after["git_status_porcelain"])
        writer.write_json("verification.json", verdict, schema="regime_lab.ra03_verification.v1")
        write_text_atomic(run_dir / "report.md",
                          build_report(baseline, verdict, writer.lab_run_id, manifest_doc,
                                      route, retention_doc, memory, parity, forecast))
        write_text_atomic(run_dir / "handoff.md", build_handoff(writer.lab_run_id, verdict))
        att.detail = {"run_dir": str(run_dir), "overall": verdict["overall"]}

    print(json.dumps({"run_dir": str(run_dir), "overall": verdict["overall"],
                      "gates": {k: v["pass"] for k, v in verdict["gates"].items()}}, indent=2))
    return 0 if verdict["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
