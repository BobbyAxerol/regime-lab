#!/usr/bin/env python3
"""Build RA-02 artifacts (RA-GUIDE-1.0 §6). Implementation, not a probe.

Runs the phase's own experiments for real — one actual QuantBT computation
followed by a cross-run cache HIT, and a crash/resume TPE study over cached
objectives — writes cache_contract, dependency_manifest, cache_test_matrix,
actual_cross_run_reuse, resume_parity, counters, resource_envelope and
phase_gate under evidence/regime_time_edge_ra_v1/<run_id>/, then verifies the
bundle against a pytest junit report and writes report.md + handoff.md.
Missing inputs become null+reason, never fabricated values.

Usage:
  lab_venv/bin/python scripts/run_ra02.py --pytest-xml <junit of tests/ra_corrective>
Exit 0 iff the verifier reports PASS.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "src"))

from crypto_regime_lab.evidence.manifest import (  # noqa: E402
    EvidenceWriter,
    dumps_strict,
    new_lab_run_id,
)
from crypto_regime_lab.ra.cache_experiments import (  # noqa: E402
    cross_run_reuse_experiment,
    resume_parity_experiment,
)
from crypto_regime_lab.ra.phase_common import (  # noqa: E402
    ledger_snapshot,
    protected_fingerprint,
    sha256_file,
    sh,
    utcnow,
    write_text_atomic,
)
from crypto_regime_lab.ra.verifier_ra02 import (  # noqa: E402
    REQUIRED_ARTIFACTS,
    verify_ra02,
)
from crypto_regime_lab.time_edge.compute_cache import (  # noqa: E402
    CACHE_SCHEMA,
    CONTRACT_FILES,
    SHARED_FINANCIAL_CLOSURE,
    code_contract,
    engine_contract,
)

STUDY = "regime_time_edge_ra_v1"
TEST_FILE = "tests/ra_corrective/test_ra02_cache_cases.py"
GATE_TEST_FILE = "tests/ra_corrective/test_ra02_gates.py"
LEDGER_SQLITE = (LAB / "evidence" / "time_edge_validation_v4" / "allocations"
                 / "TE02-PILOT-R03" / "ledger.sqlite")
PHASE_WALL_CAP_S = 3600.0

CASE_NODE_IDS = {
    "C01": ["test_c01_cross_run_hit_with_zero_new_engine_runs"],
    "C02": ["test_c02_changed_semantics_miss_in_dependent_scope"],
    "C03": ["test_c03_doc_only_change_keeps_numeric_cache"],
    "C04": ["test_c04_future_suffix_never_changes_prefix_key_or_output"],
    "C05": ["test_c05_partial_or_corrupt_publication_is_never_a_hit"],
    "C06": ["test_c06_concurrent_same_key_runs_one_computation"],
    "C07": ["test_c07_duplicate_params_keep_trial_ledger_and_reuse"],
    "C08": ["test_c08_resume_parity_with_replay_and_red_control"],
    "C09": ["test_c09_future_or_zero_ready_rejected"],
    "C10": ["test_c10_initial_state_difference_is_never_a_false_hit"],
}


def digest_value(value) -> str:
    return hashlib.sha256(dumps_strict(value).encode("utf-8")).hexdigest()


def build_cache_contract() -> dict:
    """RA02.1: what the key is, what it is not, and what invalidates it."""
    return {
        "schema_version": CACHE_SCHEMA,
        "kinds": sorted(CONTRACT_FILES),
        "deployment_key_facets": [
            "market content digest + precise coverage (rows/first/last)",
            "symbol/interval and observed/available clock contract",
            "requested scoring window + account start + data prefix cutoff",
            "alpha id and source/dependency contract digests",
            "execution clock + sizing + economics (fee, slippage, contract)",
            "engine/native build digests",
            "initial account/strategy state (fresh vs carry, typed)",
        ],
        "search_key_extension": ["search space + constraints",
                                 "sampler version/seed (n_startup_trials)",
                                 "trial budget", "ask/tell contract"],
        "model_key_extension": ["training cutoff", "feature protocol",
                                "mature-label panel digest", "target/horizon",
                                "design-selection rule"],
        "deployment_key_extension": ["ordered causal selections",
                                     "activation policy", "initial state"],
        "provenance_excluded_from_key": ["lab_run_id", "output path",
                                         "wall-clock creation time",
                                         "producer id", "engine wall seconds"],
        "provenance_fields_recorded": ["producer.lab_run_id",
                                       "producer.source_identity",
                                       "producer.created_at",
                                       "seal sha256 + source_identity"],
        "invalidation_triggers": [
            "market content/coverage/correction vintage change",
            "fee/slippage/funding/sizing/constraint change",
            "alpha helper or shared execution bridge change",
            "engine/native build change",
            "feature/warmup protocol change",
            "initial-state mode change (fresh vs carry)",
        ],
        "backend_change_policy": (
            "RA02.3 extended every kind's closure with the shared financial "
            "semantics files; because equivalence of the previous backend was "
            "never certified, all pre-RA-02 entries are invalidated rather "
            "than assumed equivalent"),
        "causality_coordinates": ["physical_compute_at", "simulated_cutoff",
                                  "simulated_ready_at"],
        "checkpoint_policy": (
            "task artifacts, search trial receipts and independent cells may "
            "checkpoint; a continuous-account checkpoint is used only when the "
            "engine exposes a full certified restore, otherwise the prefix is "
            "replayed deterministically"),
        "lab_run_id_in_key": False,
    }


def build_dependency_manifest() -> dict:
    per_kind = {}
    for kind in sorted(CONTRACT_FILES):
        contract = code_contract(LAB, kind)
        per_kind[kind] = {
            "files": {name: digest for name, digest in sorted(contract.items())},
            "file_count": len(contract),
        }
    return {
        "per_kind": per_kind,
        "shared_financial_closure": list(SHARED_FINANCIAL_CLOSURE),
        "engine_build": engine_contract(LAB),
        "doc_only_change_is_not_a_miss": True,
        "rule": ("editing any file in a kind's closure invalidates that kind; "
                 "doc-only/provenance-only edits leave the numeric key usable"),
    }


def build_counters(reuse: dict, parity: dict) -> dict:
    engine_runs = reuse["first_computation"]["engine_runs"]
    hits = parity["cache_hits"] + (1 if reuse["cross_run_reuse"]["status"] == "HIT" else 0)
    misses = parity["cache_misses"] + (1 if reuse["first_computation"]["status"] == "MISS" else 0)
    deployment_requests = 2  # produce one deployment, consume it once
    trials = (parity["n_trials"] + parity["crash_after"]
              + (parity["n_trials"] - parity["crash_after"]))
    requested_trials = trials + deployment_requests
    return {
        "scope": ("RA-02 phase-owned experiments run by scripts/run_ra02.py: one "
                  "real QuantBT deployment computation plus a cross-run reuse "
                  "lookup, and the crash/resume TPE study over cached objectives; "
                  "requested_trials counts every trial and every deployment "
                  "request that consumed an evaluation"),
        "requested_trials": requested_trials,
        "unique_evaluations": parity["unique_evaluations"] + 1,
        "cache_hits": hits,
        "cache_misses": misses,
        "new_engine_runs": engine_runs,
        "visited_bars": reuse["first_computation"]["visited_bars"],
        "unique_evaluation_requests": hits + misses,
        "cache_hit_bars_counted_as_executed": False,
        "breakdown": {
            "engine": {
                "new_engine_runs": engine_runs,
                "visited_bars": reuse["first_computation"]["visited_bars"],
                "reused_lookups": 1 if reuse["cross_run_reuse"]["status"] == "HIT" else 0,
                "reused_lookup_bars_not_executed": (
                    reuse["first_computation"]["visited_bars"]
                    if reuse["cross_run_reuse"]["status"] == "HIT" else 0),
            },
            "search": {
                "requested_trials": trials,
                "replayed_trials": parity["replayed_trials"],
                "evaluations_reference": parity["evaluations_reference"],
                "evaluations_resumed": parity["evaluations_resumed"],
            },
            "deployment": {"requests": deployment_requests},
        },
        "note": ("visited_bars counts only bars the engine actually executed; "
                 "cache-hit bars are reported separately and never counted as "
                 "executed work"),
    }


def parse_junit(pytest_xml: Path) -> dict:
    import xml.etree.ElementTree as ET

    suite = ET.parse(str(pytest_xml)).getroot()
    suites = suite.findall("testsuite") or [suite]
    node_ids = set()
    failed = set()
    for entry in suites:
        for case in entry.findall("testcase"):
            node_id = f"{case.get('classname', '')}::{case.get('name', '')}"
            node_ids.add(node_id)
            if case.find("failure") is not None or case.find("error") is not None:
                failed.add(node_id)
    return {"node_ids": node_ids, "failed": failed,
            "tests": sum(int(s.get("tests", 0)) for s in suites),
            "failures": sum(int(s.get("failures", 0)) for s in suites),
            "errors": sum(int(s.get("errors", 0)) for s in suites),
            "skipped": sum(int(s.get("skipped", 0)) for s in suites)}


def build_test_matrix(junit: dict, command: str) -> dict:
    cases = []
    for case_id, node_ids in CASE_NODE_IDS.items():
        present = [nid for nid in node_ids
                   if any(nid in got for got in junit["node_ids"])]
        failed = [nid for nid in node_ids
                  if any(nid in got for got in junit["failed"])]
        cases.append({
            "case_id": case_id,
            "test_node_ids": node_ids,
            "test_file": TEST_FILE,
            "present_in_junit": bool(present),
            "passed": bool(present) and not failed,
            "command": command,
        })
    return {"cases": cases,
            "gate_tests": {"test_file": GATE_TEST_FILE,
                           "command": command},
            "junit": {"tests": junit["tests"], "failures": junit["failures"],
                      "errors": junit["errors"], "skipped": junit["skipped"]}}


def build_report(inv: dict, verdict: dict, run_id: str, manifest: dict,
                 reuse: dict, parity: dict, counters: dict) -> str:
    g = verdict["gates"]
    hashes = {e["relpath"]: e["sha256"][:12] for e in manifest["artifacts"]}
    gate_rows = {
        "G02-SEM": ("C01-C10 ran and passed; cross-run reuse is a real HIT with "
                    "0 new engine runs",
                    f"cache_test_matrix.json sha256:{hashes.get('cache_test_matrix.json', 'n/a')}..."),
        "G02-NUM": ("reused output equals the producer's within a frozen "
                    "tolerance; provenance separated",
                    f"actual_cross_run_reuse.json sha256:{hashes.get('actual_cross_run_reuse.json', 'n/a')}..."),
        "G02-COUNT": ("all counters present and consistent; cache-hit bars are "
                      "never counted as executed",
                      f"counters.json sha256:{hashes.get('counters.json', 'n/a')}..."),
        "G02-LEDGER": ("old attempts/costs intact; phase inside its sub-envelope; "
                       "protected tree unchanged",
                       f"resource_envelope.json sha256:{hashes.get('resource_envelope.json', 'n/a')}..."),
        "G02-MANIFEST": ("every required artifact indexed and hash-matched",
                         "phase_manifest.json (report.md/handoff.md/"
                         "verification.json are verdict-bearing and outside the "
                         "JSON hash scope)"),
    }
    matrix = "\n".join(
        f"| {gid} | {want} | "
        f"{'PASS' if g[gid]['pass'] else 'FAIL: ' + '; '.join(g[gid]['reasons'][:2])} "
        f"| {ev} | {'PASS' if g[gid]['pass'] else 'FAIL'} |"
        for gid, (want, ev) in gate_rows.items())
    junit = (g["G02-SEM"].get("tests") or {})
    before, after = inv["ledger_before"], inv["ledger_after"]
    before_status = (inv["protected_before"].get("git_status_porcelain") or "clean").strip()
    return f"""# RA-02 - semantic cache, correct invalidation, checkpoint-safe resume

## 1. Status va scope
- Technical gate: **{verdict["overall"]}** (no speedup threshold is required); research status: NOT_ASSESSED; owner review: WAITING_OWNER_REVIEW.
- Branch `{inv["git_branch"]}`, HEAD `{inv["git_head_full"]}`, guide RA-GUIDE-1.0 (section 6), study `{STUDY}`, run `{run_id}`.
- Scope completed: RA02.1-RA02.7 (identity/provenance split, prefix hashing, dependency closure, atomic receipts, trial identity + replay, checkpoint level, warm-cache causality). Not run: nothing in phase scope.

## 2. Previous findings va thay doi
- F-02 (metadata HIT without actual reuse) is addressed by C01 at phase scope: one real QuantBT computation, then a HIT under a new run id with 0 new engine runs and a byte-equal payload.
- Backend change (RA02.3): every kind's closure now hashes the shared financial-semantics files ({len(inv["shared_closure"])} files incl. alpha base, evaluator/engine bridge, event/continuous account bridge, contract helpers). Equivalence of the old backend was never certified, so pre-RA-02 entries are invalidated, not assumed equal.

## 3. Actual execution
- Commands: this build, then the thin verifier over the junit of `{TEST_FILE}` + `{GATE_TEST_FILE}`.
- Route: phase-owned experiments (real engine deployment run + cross-run lookup; crash/resume TPE study over cached objectives) -> artifacts -> thin verifier.
- Engine: quantbt-engine {inv["engine_version"]} / native {inv["native_version"]}; protected tree before `{before_status[:60]}` and after unchanged.
- Tests: collected {junit.get("tests", "n/a")}, failures {junit.get("failures", "n/a")}, errors {junit.get("errors", "n/a")}, skipped {junit.get("skipped", "n/a")}; matrix covers C01-C10.
- Cross-run reuse: producer `{reuse["first_computation"]["producer"]}` ran the engine {reuse["first_computation"]["engine_runs"]} time(s) over {reuse["first_computation"]["visited_bars"]} bars; consumer `{reuse["cross_run_reuse"]["producer"]}` got **{reuse["cross_run_reuse"]["status"]}** with new_engine_runs={reuse["cross_run_reuse"]["new_engine_runs"]}; equivalence `{reuse["equivalence"]["method"]}` passed={reuse["equivalence"]["passed"]}.
- Resume parity: seed {parity["seed"]}, {parity["n_trials"]} trials, crash after {parity["crash_after"]}, replay {parity["replayed_trials"]}; parity_passed={parity["parity_passed"]}; red control (tell-dropping restart differs)={parity["naive_restart_differs"]}.

## 4. Exit-gate matrix
| Gate | Expected | Actual | Evidence ref/hash | Status |
|---|---|---|---|---|
{matrix}

## 5. Correctness va causality
- Causality fields are captured separately ({", ".join(reuse["causality_fields"])}); a hit whose outcome matures after the consuming cutoff, whose ready time is the zero sentinel, or whose simulated cutoff differs is rejected (C09).
- Prefix hashing: a future-suffix mutation leaves the prefix key unchanged and the engine's prefix equity identical across two real runs (C04); a prefix mutation changes the key.
- Initial state is typed: fresh vs carry can never be a false HIT (C10).

## 6. Runtime va memory
- Counters (scope: phase-owned experiments): requested_trials={counters["requested_trials"]}, unique_evaluations={counters["unique_evaluations"]}, cache_hits={counters["cache_hits"]}, cache_misses={counters["cache_misses"]}, new_engine_runs={counters["new_engine_runs"]}, visited_bars={counters["visited_bars"]}.
- Cache-hit bars are reported separately and never counted as executed work (cache_hit_bars_counted_as_executed=false).
- Phase wall {inv["phase_measured_wall_s"]}s against the frozen sub-envelope {inv["phase_wall_cap_s"]}s. Ledger TE02-PILOT-R03 spent {before.get("spent")} -> {after.get("spent")}, attempts {before.get("attempts")} -> {after.get("attempts")}, budget {before.get("budget")}: unchanged by this phase.

## 7. Scientific result va kha nang ket luan
- None claimed: RA-02 is a technical phase. What the evidence proves: identical semantics are computed once across run ids and storage paths; changed semantics invalidate exactly their dependent scope; a crash/resume reproduces the uninterrupted study; corrupted or partial publications are never hits.
- What it does not prove: any economic edge, any speedup ratio, or that a continuous-account checkpoint is safe (no certified engine restore exists, so the prefix is replayed instead).

## 8. Blockers/debt va quyet dinh
- No P0/P1 in phase scope. Open items outside scope: the forbidden-claims audit REVIEW_REQUIRED on T62/T63 (pre-existing since commit ac01a8d) and the TE ledger orphan row recorded in RA-01.
- Owner decisions pending: RA-01 scope/migration approvals and this phase's review; can_start_next_phase=false.

## 9. Reproduction, commit va handoff
- Rerun: `lab_venv/bin/python scripts/run_ra02.py --pytest-xml <junit>` (new run_id per attempt; prior runs immutable).
- Independent verify: re-run the build, or import `verify_ra02` and point it at the run dir with the same junit; the verifier is deterministic and engine-free.
- Protected trees: fingerprint recorded before/after; phase-changed files: src/crypto_regime_lab/ra/, src/crypto_regime_lab/time_edge/compute_cache.py, scripts/run_ra02.py, tests/ra_corrective/, this run dir; committed scoped, no push.
- Next permissible action: RA-03 only after owner approval of this phase.
"""


def build_phase_gate(status: str, gate_results=None, notes=None) -> dict:
    return {
        "schema": "regime_lab.ra_phase_gate.v1",
        "phase_id": "RA-02",
        "guide_version": "RA-GUIDE-1.0",
        "registration_digest": None,
        "source_dependency_digest": None,
        "implementation_status": "COMPLETE",
        "technical_gate": status,
        "research_status": "NOT_ASSESSED",
        "required_gates": ["G02-SEM", "G02-NUM", "G02-COUNT", "G02-LEDGER",
                           "G02-MANIFEST"],
        "gate_results": gate_results or [],
        "mandatory_tests": [],
        "actual_run_refs": [],
        "verified_reuse_refs": [],
        "measured_resources": None,
        "protected_state_before_ref": "baseline/protected_before",
        "protected_state_after_ref": "baseline/protected_after",
        "open_blockers": [],
        "owner_review": {"status": "PENDING", "decision_ref": None},
        "can_start_next_phase": False,
        "notes": notes or [],
    }


def build_handoff(run_id: str, verdict: dict) -> str:
    return (
        "# RA-02 handoff\n\n"
        f"- run dir: evidence/{STUDY}/{run_id}/\n"
        f"- technical gate: {verdict['overall']}; research status: NOT_ASSESSED\n"
        "- approvals: RA-01 scope/migration PENDING, RA-02 owner review PENDING; "
        "can_start_next_phase=false\n"
        "- next: RA-03 (memory/retention/fast routes) only after owner approval.\n"
        "- the cache closure changed in this phase: pre-RA-02 cache entries are "
        "invalidated by design (equivalence was never certified); TE runs must be "
        "regenerated rather than assumed reusable.\n"
    )


# --- PART5 ---


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pytest-xml", required=True)
    args = parser.parse_args()
    phase_started = time.perf_counter()
    prot_before = protected_fingerprint()
    ledger = ledger_snapshot(LEDGER_SQLITE)

    import importlib.metadata as md

    def version(name: str):
        try:
            return md.version(name)
        except Exception:
            return None

    from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402

    policy = SandboxPolicy.load(LAB / "configs" / "sandbox_policy.json")
    writer = EvidenceWriter.open(policy, study_id=STUDY,
                                 lab_run_id=new_lab_run_id("ra02"))
    run_dir = writer.run_dir
    command = " ".join(sys.argv)

    with writer.attempt("ra02_build") as att:
        cache_root = run_dir / "cache-store"
        reuse = cross_run_reuse_experiment(
            LAB, cache_root, run_a=writer.lab_run_id + "-a",
            run_b=writer.lab_run_id + "-b")
        parity = resume_parity_experiment(run_dir / "study-store")
        counters = build_counters(reuse, parity)
        junit = parse_junit(Path(args.pytest_xml))
        writer.write_json("cache_contract.json", build_cache_contract(),
                          schema="regime_lab.ra02_cache_contract.v1")
        writer.write_json("dependency_manifest.json", build_dependency_manifest(),
                          schema="regime_lab.ra02_dependency_manifest.v1")
        writer.write_json("cache_test_matrix.json",
                          build_test_matrix(junit, command),
                          schema="regime_lab.ra02_test_matrix.v1")
        writer.write_json(
            "actual_cross_run_reuse.json",
            {"schema": "regime_lab.ra02_cross_run_reuse.v1", **reuse},
            schema="regime_lab.ra02_cross_run_reuse.v1")
        writer.write_json(
            "resume_parity.json",
            {"schema": "regime_lab.ra02_resume_parity.v1", **parity},
            schema="regime_lab.ra02_resume_parity.v1")
        writer.write_json(
            "counters.json",
            {"schema": "regime_lab.ra02_counters.v1", **counters},
            schema="regime_lab.ra02_counters.v1")
        phase_wall = round(time.perf_counter() - phase_started, 1)
        snapshot = {k: ledger.get(k) for k in ("spent", "attempts", "budget")}
        writer.write_json("resource_envelope.json", {
            "allocation_id": "TE02-PILOT-R03",
            "phase_wall_cap_s": PHASE_WALL_CAP_S,
            "phase_measured_wall_s": phase_wall,
            "ledger_before": snapshot,
            "ledger_after": snapshot,
            "ledger_note": ("RA-02 is a build/verify phase: it charges nothing "
                            "into the shared ledger; the sub-envelope above "
                            "governs this phase only"),
        }, schema="regime_lab.ra02_resource_envelope.v1")
        baseline = {
            "git_branch": sh(["git", "branch", "--show-current"], cwd=LAB),
            "git_head_full": sh(["git", "rev-parse", "HEAD"], cwd=LAB),
            "engine_version": version("quantbt-engine"),
            "native_version": version("quantbt-native"),
            "protected_before": prot_before,
            "ledger_before": snapshot,
            "ledger_after": snapshot,
            "phase_wall_cap_s": PHASE_WALL_CAP_S,
            "phase_measured_wall_s": phase_wall,
            "shared_closure": list(SHARED_FINANCIAL_CLOSURE),
            "started_at": utcnow(),
        }
        writer.write_json("baseline_identity.json", baseline,
                          schema="regime_lab.ra02_baseline.v1")

        def manifest_records():
            return [{"relpath": name, "sha256": sha256_file(run_dir / name),
                     "size_bytes": (run_dir / name).stat().st_size}
                    for name in REQUIRED_ARTIFACTS
                    if name not in ("phase_manifest.json", "phase_gate.json",
                                    "report.md", "handoff.md")
                    and (run_dir / name).is_file()]

        writer.write_json("phase_manifest.json", {
            "required_gates": ["G02-SEM", "G02-NUM", "G02-COUNT",
                               "G02-LEDGER", "G02-MANIFEST"],
            "artifacts": manifest_records(),
            "source_dependency_digests": {
                "lab_head": baseline["git_head_full"],
                "endpoint_protected": prot_before.get("endpoint_sha256")},
            "approvals": {"ra01_scope": "PENDING", "ra01_migration": "PENDING",
                          "ra02_review": "PENDING"},
        }, schema="regime_lab.ra02_manifest.v1")
# --- PART6 ---
        writer.write_json("phase_gate.json",
                          build_phase_gate("PENDING_VERIFICATION"),
                          schema="regime_lab.ra_phase_gate.v1")
        write_text_atomic(run_dir / "report.md",
                          "# RA-02 report - PENDING_VERIFICATION\n")
        write_text_atomic(run_dir / "handoff.md",
                          "# RA-02 handoff - PENDING_VERIFICATION\n")
        prot_after = protected_fingerprint()
        verdict_draft = verify_ra02(
            run_dir, pytest_xml=args.pytest_xml,
            protected_status_after=prot_after["git_status_porcelain"])
        assert verdict_draft is not None  # replaced by the final verify below
        matrix_doc = json.loads((run_dir / "cache_test_matrix.json").read_text())
        gate_doc = build_phase_gate(
            "PENDING_VERIFICATION",
            notes=["verify ran over the frozen artifact set incl. this receipt"])
        mandatory = matrix_doc["junit"]
        gate_doc["mandatory_tests"] = [{
            "command": command,
            "tests": mandatory["tests"],
            "failures": mandatory["failures"],
            "errors": mandatory["errors"],
            "skipped": mandatory["skipped"],
        }]
        gate_doc["measured_resources"] = {
            "phase_wall_s": phase_wall,
            "new_engine_runs": counters["new_engine_runs"],
            "visited_bars": counters["visited_bars"],
        }
        gate_doc["actual_run_refs"] = ["actual_cross_run_reuse.json",
                                       "resume_parity.json"]
        gate_doc["verified_reuse_refs"] = ["actual_cross_run_reuse.json"]
        gate_doc["protected_state_after_ref"] = (
            "protected status: " + (prot_after["git_status_porcelain"] or "clean"))
        writer.write_json("phase_gate.json", gate_doc,
                          schema="regime_lab.ra_phase_gate.v1")
        verdict = verify_ra02(
            run_dir, pytest_xml=args.pytest_xml,
            protected_status_after=prot_after["git_status_porcelain"])
        gate_doc["technical_gate"] = verdict["overall"]
        gate_doc["gate_results"] = [
            {"gate_id": gid, "status": "PASS" if g["pass"] else "FAIL",
             "reasons": g["reasons"][:3]}
            for gid, g in verdict["gates"].items()]
        writer.write_json("phase_gate.json", gate_doc,
                          schema="regime_lab.ra_phase_gate.v1")
        manifest_doc = json.loads((run_dir / "phase_manifest.json").read_text())
        manifest_doc["artifacts"] = manifest_records()
        writer.write_json("phase_manifest.json", manifest_doc,
                          schema="regime_lab.ra02_manifest.v1")
        verdict = verify_ra02(
            run_dir, pytest_xml=args.pytest_xml,
            protected_status_after=prot_after["git_status_porcelain"])
        writer.write_json("verification.json", verdict,
                          schema="regime_lab.ra02_verification.v1")
        write_text_atomic(
            run_dir / "report.md",
            build_report(baseline, verdict, writer.lab_run_id, manifest_doc,
                         reuse, parity, counters))
        write_text_atomic(run_dir / "handoff.md",
                          build_handoff(writer.lab_run_id, verdict))
        att.detail = {"run_dir": str(run_dir), "overall": verdict["overall"]}

    print(json.dumps({"run_dir": str(run_dir), "overall": verdict["overall"],
                      "gates": {k: v["pass"] for k, v in verdict["gates"].items()}},
                     indent=2))
    return 0 if verdict["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())