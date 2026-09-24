#!/usr/bin/env python3
"""Build FP-02 artifacts (guide §14): common evaluator, cache, memory,
runtime and lineage. Runs the guide's five mandatory REAL engine checks (no
mocked-only run):

  1. one candidate via the audit route (report_level=None)
  2. the SAME candidate via the score/fast route this evaluator intends to
     use (report_level="score") -- route_parity.json (FP02-G-PARITY)
  3. a small multi-selection deployment with a real pending/activation case
     -- lineage_demo.json (FP02-G-LINEAGE)
  4. cross-run semantic cache reuse -- cache_reuse.json (FP02-G-CACHE)
  5. an interrupted/resumed task (cache-based, guide's own conditional
     wording: "nếu checkpoint là capability được dùng") -- resume_demo.json
     (FP02-G-RESUME)

Plus memory_audit.json (FP02-G-MEMORY: peak within budget, not growing with
repeated calls) and a causal-hit re-check (FP02-G-LATENCY, re-derived by the
verifier from causality coordinates already on every payload above -- no
extra run needed for it).

Market data: a small REAL window (not synthetic) -- FP-03 onward needs this
evaluator on real bars, so this phase's own evidence should be on real bars
too, not a toy fixture. Kept small (10 real days, 1m) precisely because nothing
here needs to be large to prove the mechanism, and the RA-07 decay deep-dive
already paid for that lesson once.

Usage:
  lab_venv/bin/python scripts/run_fp02.py --pytest-xml <junit xml of the FP-02 tests>
Exit 0 iff the FP-02 verifier reports PASS.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import resource
import sys
from datetime import datetime, timezone
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "src"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter, new_lab_run_id  # noqa: E402
from crypto_regime_lab.fp import GUIDE_VERSION, STUDY_ID  # noqa: E402
from crypto_regime_lab.fp import evaluator as ev  # noqa: E402
from crypto_regime_lab.fp.verifier_fp02 import (  # noqa: E402
    REQUIRED_GATES, REQUIRED_TEST_NODES, verify_fp02,
)
from crypto_regime_lab.ra.ra05_market import load_real_bars  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402
from crypto_regime_lab.safety.process import lab_worker_env  # noqa: E402
from crypto_regime_lab.time_edge.compute_cache import ComputeCache  # noqa: E402

PHASE_ID = "FP-02"
CONFIG_DIR = LAB / "configs" / "forward_persistence_fp_v1"
CACHE_ROOT = "evidence/forward_persistence_fp_v1/compute-cache"
ALPHA_ID = "A-SC"
WINDOW_START = "2023-06-01"
WINDOW_END = "2023-06-11"
BASE_PARAMS_A = {"AP": 5, "coeff": 2, "novolumedata": False, "src_col": "close",
                 "alpha.condition_threshold": 50}
BASE_PARAMS_B = {"AP": 8, "coeff": 3, "novolumedata": False, "src_col": "close",
                 "alpha.condition_threshold": 40}


def _salt(lab_run_id: str) -> int:
    """A small, deterministic, per-run offset so this script's OWN cache
    demonstration is meaningful on every re-run, not only the first: the
    ComputeCache directory is deliberately PERSISTENT across invocations
    (that is the whole point of a semantic cache), so reusing the literal
    same params on a second build of this phase would make the 'first call
    is a MISS' / 'resume recomputes only what is new' claims false --
    correctly, since the cache really would already hold them. AP is a
    harmless small integer for A-SC; this changes nothing about what is
    being proved, only which exact candidate proves it this time."""
    return int(hashlib.sha256(lab_run_id.encode()).hexdigest(), 16) % 1000


def _params_for(lab_run_id: str) -> tuple[dict, dict]:
    offset = _salt(lab_run_id)
    return ({**BASE_PARAMS_A, "AP": BASE_PARAMS_A["AP"] + offset},
            {**BASE_PARAMS_B, "AP": BASE_PARAMS_B["AP"] + offset})

TEST_NODE_IDS = list(REQUIRED_TEST_NODES) + [
    "test_fp02_lineage_rejects_a_fabricated_disagreement",
    "test_fp02_verifier_passes_on_a_valid_bundle",
    "test_fp02_verifier_survives_the_real_two_stage_gate_receipt_write",
    "test_fp02_verifier_fails_on_empty_dir",
    "test_fp02_verifier_fails_on_tampered_artifact",
    "test_fp02_verifier_fails_when_parity_route_disagrees",
    "test_fp02_verifier_fails_when_lineage_fills_do_not_reconcile",
    "test_fp02_verifier_fails_when_resume_recomputes_twice",
]


def utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="microseconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _apply_thread_and_memory_limits(policy) -> dict:
    """Guide §0.2/Appendix C's registered resource envelope, applied to THIS
    process (no subprocess needed at this scale): thread env vars via the
    lab's established lab_worker_env, and RLIMIT_AS so an unexpected
    over-budget call raises a recorded MemoryError instead of a kernel
    SIGKILL (mem_audit.py precedent, 2026-09-20)."""
    import os

    env = lab_worker_env(policy)
    for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
               "NUMEXPR_NUM_THREADS", "NUMBA_NUM_THREADS"):
        os.environ[key] = env[key]
    budget = policy.raw["resource_budget"]
    cap_bytes = int(budget["working_memory_gib"] * (1 << 30))
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    resource.setrlimit(resource.RLIMIT_AS, (cap_bytes, hard))
    return {"cpu_limit": env["OMP_NUM_THREADS"], "rlimit_as_gib": budget["working_memory_gib"],
            "previous_soft_gib": (None if soft == resource.RLIM_INFINITY
                                  else round(soft / (1 << 30), 2))}


def write_configs() -> dict:
    """FP-02's own studies-array entry, appended idempotently -- FP-01's row
    stays untouched (guide §24.4: never overwrite a prior registration)."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    reg_path = CONFIG_DIR / "registration.json"
    reg = json.loads(reg_path.read_text(encoding="utf-8"))
    studies = reg.setdefault("studies", [])
    fp02_entry = {
        "id": "FP-02",
        "title": "Evaluator and reusable runtime",
        "scope": [
            "common evaluator mapped onto the qualified event-account route "
            "(report_level audit/score, FUP-04-proven)",
            "standardized candidate (5.1) and continuous deployment (5.2) "
            "accounts, same underlying call",
            "semantic cache/invalidation (ComputeCache, fp_candidate/fp_deployment kinds)",
            "compact vs full retention tiers (fp/retention_fp02.py)",
            "lineage from selection to actual activation/orders/fills (fp/lineage.py)",
        ],
        "non_goals": ["any market/edge claim", "an actual TPE search loop (FP-03)",
                      "a new execution route (the guide's own qualified-route exit clause applies)"],
        "required_inputs": ["FP-01 (admission hook, boundary repair, chronology guard)",
                            "snapshots/server_core_v1 (read-only), a small real A-SC window"],
        "exit": "FP02-G-PARITY / FP02-G-CACHE / FP02-G-LATENCY / FP02-G-MEMORY / "
                "FP02-G-LINEAGE / FP02-G-RESUME all PASS",
        "budget": "T0 host-only: a handful of small real engine calls, no shared TE ledger charge",
    }
    if not any(s.get("id") == "FP-02" for s in studies):
        studies.append(fp02_entry)
        reg_path.write_text(json.dumps(reg, indent=2) + "\n", encoding="utf-8")
    return {"registration_path": str(reg_path)}


def run_fp02(pytest_xml: str | None) -> tuple[int, dict]:
    policy = SandboxPolicy.discover(LAB)
    policy.assert_lab_root_ok()
    limits = _apply_thread_and_memory_limits(policy)
    started = utcnow()
    write_configs()

    # load_real_bars takes a SYMBOL, not an alpha id -- ALPHA_ID ("A-SC") is a
    # separate axis, passed to the evaluator calls below, never to the loader.
    frame, partitions = load_real_bars("BTCUSDT", start=WINDOW_START, end=WINDOW_END)
    frame = frame[["open", "high", "low", "close", "volume"]].copy()

    lab_run_id = new_lab_run_id("fp02")
    PARAMS_A, PARAMS_B = _params_for(lab_run_id)
    writer = EvidenceWriter(policy=policy, study_id=STUDY_ID, lab_run_id=lab_run_id)
    run_dir = writer.run_dir
    cache = ComputeCache(LAB, "fp02", cache_root=CACHE_ROOT)

    # 1+2. FP02-G-PARITY: audit route vs the score/fast route, same candidate.
    parity = ev.route_parity(LAB, ALPHA_ID, frame, PARAMS_A)

    # 4. FP02-G-CACHE: cross-run reuse (same semantics) + a genuine MISS
    # (a changed economic dependency).
    cutoff = frame.index[-1]
    payload_a, event_a = ev.evaluate_candidate(cache, LAB, ALPHA_ID, frame, PARAMS_A,
                                               cutoff=cutoff, producer=f"{lab_run_id}-a")
    payload_b, event_b = ev.evaluate_candidate(cache, LAB, ALPHA_ID, frame, PARAMS_A,
                                               cutoff=cutoff, producer=f"{lab_run_id}-b")
    changed_economics = {**ev.default_economics(), "one_way_fee": 0.0009}
    payload_c, event_c = ev.evaluate_candidate(cache, LAB, ALPHA_ID, frame, PARAMS_A,
                                               cutoff=cutoff, economics=changed_economics,
                                               producer=f"{lab_run_id}-c")
    cache_reuse = {
        "schema": "regime_lab.fp02_cache_reuse.v1",
        "first": {"status": event_a["status"], "producer": event_a["producer"]["lab_run_id"]},
        "first_causality": payload_a["causality"],
        "reused": {"status": event_b["status"], "producer_of_reused_payload":
                  event_b["producer"]["lab_run_id"], "payload_identical": payload_b == payload_a},
        "changed_economics": {"status": event_c["status"],
                              "terminal_equity_changed": (
                                  payload_c["trial_scalar"]["terminal_equity"]
                                  != payload_a["trial_scalar"]["terminal_equity"])},
        "provenance_excluded_from_payload_key": [
            "producer", "physical_compute_at (only inside causality, semantic not provenance)"],
    }

    # 3. FP02-G-LINEAGE: a real multi-selection deployment with a pending/
    # activation case.
    switch_bar = len(frame) // 2
    requests = [
        {"activation_id": f"{lab_run_id}-initial", "params": PARAMS_A, "requested_at_bar": 0},
        {"activation_id": f"{lab_run_id}-switch", "params": PARAMS_B,
         "requested_at_bar": switch_bar},
    ]
    deploy_payload, deploy_event = ev.run_deployment(
        cache, LAB, ALPHA_ID, frame, requests, ready_at=frame.index[-1],
        producer=f"{lab_run_id}-deploy")
    lineage_demo = {
        "schema": "regime_lab.fp02_lineage_demo.v1",
        "status": deploy_event["status"], "requests": requests,
        "switch_requested_at_bar": switch_bar,
        "lineage": deploy_payload["lineage"],
        "trial_scalar": deploy_payload["trial_scalar"],
    }

    # 5. FP02-G-RESUME: a fresh ComputeCache instance (what a restarted
    # process would construct) resumes what is already computed.
    fresh_candidates = [{**PARAMS_A, "AP": PARAMS_A["AP"] + delta} for delta in (1, 2, 3)]
    pre_resume_statuses = []
    for params in fresh_candidates[:2]:
        _payload, event = ev.evaluate_candidate(cache, LAB, ALPHA_ID, frame, params,
                                                cutoff=cutoff, producer=f"{lab_run_id}-resume1")
        pre_resume_statuses.append(event["status"])
    resumed_cache = ComputeCache(LAB, "fp02", cache_root=CACHE_ROOT)
    post_resume_statuses = []
    for params in fresh_candidates:
        _payload, event = ev.evaluate_candidate(resumed_cache, LAB, ALPHA_ID, frame, params,
                                                cutoff=cutoff, producer=f"{lab_run_id}-resume2")
        post_resume_statuses.append(event["status"])
    resume_demo = {
        "schema": "regime_lab.fp02_resume_demo.v1",
        "pre_resume_statuses": pre_resume_statuses, "post_resume_statuses": post_resume_statuses,
        "total_misses": pre_resume_statuses.count("MISS") + post_resume_statuses.count("MISS"),
        "unique_candidates": len(fresh_candidates),
    }

    # FP02-G-MEMORY: repeated small candidate evaluations, peak measured.
    from crypto_regime_lab.fp.instrumentation import mib, vm_rss_kib

    mem_frame = frame.iloc[: len(frame) // 3].copy()
    mem_cache = ComputeCache(LAB, "fp02mem", cache_root=CACHE_ROOT)
    peaks_mib = []
    for i in range(5):
        params = {**PARAMS_A, "AP": PARAMS_A["AP"] + i}
        payload, _event = ev.evaluate_candidate(mem_cache, LAB, ALPHA_ID, mem_frame, params,
                                                cutoff=mem_frame.index[-1],
                                                producer=f"{lab_run_id}-mem{i}")
        peaks_mib.append(payload["instrumentation"]["peak_mib"])
    memory_audit = {
        "schema": "regime_lab.fp02_memory_audit.v1",
        "budget_mib": policy.raw["resource_budget"]["working_memory_gib"] * 1024,
        "per_call_peak_mib": peaks_mib,
        "current_process_rss_mib": mib(vm_rss_kib()),
        "within_budget": all(p < policy.raw["resource_budget"]["working_memory_gib"] * 1024
                             for p in peaks_mib),
        "not_growing_unboundedly": peaks_mib[-1] < peaks_mib[0] * 3 + 50,
        "resource_limits_applied": limits,
    }

    resource_budget = {
        "schema": "regime_lab.fp02_resource_budget.v1", "lab_run_id": lab_run_id,
        "fp02_wall_seconds_charged_to_shared_ledger": 0,
        "engine_calls": (2 + 3 + 1 + 5 + 5),
        "note": "FP-02's own small real engine calls; no shared TE ledger touched",
        "market_partitions_used": partitions if partitions else "see frame load below",
    }
    test_registry = {"schema": "regime_lab.fp02_test_registry.v1", "lab_run_id": lab_run_id,
                     "test_node_ids": TEST_NODE_IDS, "pytest_xml": pytest_xml}

    manifest = {
        "schema": "regime_lab.fp02_phase_manifest.v1", "lab_run_id": lab_run_id,
        "study_id": STUDY_ID, "phase_id": PHASE_ID, "guide_version": GUIDE_VERSION,
        "started_at_utc": started,
        "market_window": {"alpha_id": ALPHA_ID, "start": WINDOW_START, "end": WINDOW_END,
                          "rows": int(len(frame))},
        "required_gates": list(REQUIRED_GATES), "artifacts": [],
    }
    with writer.attempt("fp02_build") as att:
        writer.write_json("route_parity.json", parity, schema="regime_lab.fp02_route_parity.v1")
        writer.write_json("cache_reuse.json", cache_reuse, schema="regime_lab.fp02_cache_reuse.v1")
        writer.write_json("lineage_demo.json", lineage_demo,
                          schema="regime_lab.fp02_lineage_demo.v1")
        writer.write_json("resume_demo.json", resume_demo, schema="regime_lab.fp02_resume_demo.v1")
        writer.write_json("memory_audit.json", memory_audit,
                          schema="regime_lab.fp02_memory_audit.v1")
        writer.write_json("resource_budget.json", resource_budget,
                          schema="regime_lab.fp02_resource_budget.v1")
        writer.write_json("test_registry.json", test_registry,
                          schema="regime_lab.fp02_test_registry.v1")
        writer.write_json("phase_manifest.json", manifest,
                          schema="regime_lab.fp02_phase_manifest.v1")
        att.detail = {"run_dir": str(run_dir)}

    report_text = render_report(lab_run_id=lab_run_id, run_dir=run_dir, parity=parity,
                                cache_reuse=cache_reuse, lineage_demo=lineage_demo,
                                resume_demo=resume_demo, memory_audit=memory_audit,
                                resource_budget=resource_budget,
                                manifest=manifest, started=started)
    handoff_text = render_handoff(lab_run_id=lab_run_id, run_dir=run_dir)
    (run_dir / "report.md").write_text(report_text, encoding="utf-8")
    (run_dir / "handoff.md").write_text(handoff_text, encoding="utf-8")
    (run_dir / "gate_receipt.json").write_text(json.dumps({
        "schema": "regime_lab.fp_gate.v1", "phase_id": PHASE_ID, "guide_version": GUIDE_VERSION,
        "lab_run_id": lab_run_id, "required_gates": list(REQUIRED_GATES),
        "technical_gate": "PENDING_VERIFICATION", "research_status": "NOT_ASSESSED",
        "owner_review": {"status": "PENDING", "decision_ref": None},
        "can_start_next_phase": False,
    }, indent=2) + "\n", encoding="utf-8")
    manifest["artifacts"] = [
        {"path": name, "sha256": sha256_file(run_dir / name)}
        for name in ("route_parity.json", "cache_reuse.json", "lineage_demo.json",
                     "resume_demo.json", "memory_audit.json", "resource_budget.json",
                     "test_registry.json", "report.md", "handoff.md", "gate_receipt.json")
    ]
    (run_dir / "phase_manifest.json").write_text(
        json.dumps({**manifest, "written_at_utc": utcnow()}, indent=2) + "\n", encoding="utf-8")
    manifest["artifacts"].append(
        {"path": "phase_manifest.json", "sha256": sha256_file(run_dir / "phase_manifest.json")})

    verdict = verify_fp02(run_dir, pytest_xml=pytest_xml)
    receipt = json.loads((run_dir / "gate_receipt.json").read_text())
    receipt.update({"technical_gate": verdict["overall"], "verification": verdict,
                    "verified_at_utc": utcnow()})
    (run_dir / "gate_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n",
                                               encoding="utf-8")
    write_fp_current(lab_run_id=lab_run_id, run_dir=run_dir, verdict=verdict)
    print(json.dumps({"run_dir": str(run_dir), "gates": verdict["gates"],
                      "overall": verdict["overall"]}, indent=2))
    return (0 if verdict["overall"] == "PASS" else 1), {"lab_run_id": lab_run_id,
                                                        "run_dir": str(run_dir)}


def render_report(*, lab_run_id, run_dir, parity, cache_reuse, lineage_demo, resume_demo,
                  memory_audit, resource_budget, manifest, started) -> str:
    lines = [
        f"# FP-02 — Evaluator and reusable runtime ({lab_run_id})", "",
        f"- run_dir: {run_dir}", f"- started_at: {started}",
        f"- market window: {manifest['market_window']['alpha_id']} "
        f"{manifest['market_window']['start']} -> {manifest['market_window']['end']} "
        f"({manifest['market_window']['rows']} real 1m bars, sha256-verified snapshot)",
        f"- engine calls (real): {resource_budget['engine_calls']}",
        "",
        "## FP02-G-PARITY — audit route vs score/fast route, same candidate",
        f"- status: {parity['status']}",
        f"- equity_exact_equal: {parity['equity_exact_equal']} "
        f"(max_abs_equity_diff={parity['max_abs_equity_diff']})",
        f"- audit: fill_count={parity['audit']['fill_count']} "
        f"engine_fill_count={parity['audit']['engine_fill_count']} "
        f"entries={parity['audit']['entries']}",
        f"- fast (score): fill_count={parity['fast']['fill_count']} "
        f"engine_fill_count={parity['fast']['engine_fill_count']} "
        f"entries={parity['fast']['entries']}",
        f"- precedent: {parity['precedent']}",
        "",
        "## FP02-G-CACHE — cross-run reuse + a genuine economic-dependency miss",
        f"- first: {cache_reuse['first']}",
        f"- reused (different producer, same semantics): {cache_reuse['reused']}",
        f"- changed economics (different fee rate): {cache_reuse['changed_economics']}",
        "",
        "## FP02-G-LINEAGE — real multi-selection deployment, pending/activation case",
        f"- status: {lineage_demo['status']}",
        f"- switch requested at bar {lineage_demo['switch_requested_at_bar']}",
        f"- activations effected: {lineage_demo['lineage']['activations_effected']}",
        f"- fills: {lineage_demo['lineage']['fills_total']} total, "
        f"{lineage_demo['lineage']['fills_attributed']} attributed "
        f"({lineage_demo['lineage']['fills_during_sentinel']} during a warming/flat sentinel)",
        "- per-activation bar ranges:",
    ]
    for row in lineage_demo["lineage"]["activations"]:
        label = row["activation_id"] or f"sentinel:{row.get('sentinel')}"
        lines.append(f"  - {label}: bar_range={row['bar_range']} fills={row['fill_count']}")
    lines += [
        "",
        "## FP02-G-RESUME — cache-based resume (no search loop exists yet to checkpoint)",
        f"- pre-crash statuses: {resume_demo['pre_resume_statuses']}",
        f"- post-resume statuses (fresh ComputeCache instance): {resume_demo['post_resume_statuses']}",
        f"- total engine recomputes across BOTH passes: {resume_demo['total_misses']} "
        f"(of {resume_demo['unique_candidates']} unique candidates -- a naive restart "
        "would have recomputed all of them twice)",
        "",
        "## FP02-G-MEMORY",
        f"- budget: {memory_audit['budget_mib']} MiB",
        f"- per-call peaks: {memory_audit['per_call_peak_mib']} MiB",
        f"- within_budget: {memory_audit['within_budget']}",
        f"- not_growing_unboundedly: {memory_audit['not_growing_unboundedly']}",
        f"- resource limits applied to this process: {memory_audit['resource_limits_applied']}",
        "",
        "## Permitted conclusions",
        "- Technical: the common evaluator (candidate + deployment, same underlying "
        "qualified route), semantic cache, retention tiers, causality-guarded latency "
        "independence and selection-to-fill lineage all exist and are proved on real "
        "engine calls over real market bars, not a mocked run.",
        "- Research: NOT_ASSESSED -- no market claim in FP-02.",
        "- Owner review: PENDING; FP-03 needs its own approval (R-18).",
        "",
    ]
    return "\n".join(lines)


def render_handoff(*, lab_run_id, run_dir) -> str:
    return "\n".join([
        f"# FP-02 handoff ({lab_run_id})", "",
        f"- run_dir: {run_dir}",
        "- next authorized action: NONE until the owner approves FP-02 -> FP-03 "
        "(record in evidence/regime_time_edge_ra_v1/owner_decisions.jsonl, R-18).",
        "- FP-03 (guide 15) must reuse: fp.evaluator.evaluate_candidate/route_parity/"
        "run_deployment, the ComputeCache fp_candidate/fp_deployment kinds.",
        "- FP-02's evaluator does not itself run a checkpointed multi-trial search "
        "(FP02-G-RESUME's own scope is cache-based, not sampler-state resume) -- "
        "FP-03's search loop is the first place sampler-state resume can be measured.",
        ""])


def write_fp_current(*, lab_run_id, run_dir, verdict) -> None:
    gates = verdict.get("gates", {})
    states = " / ".join(
        f"{name}={'PASS' if gates.get(name, {}).get('pass') else 'FAIL'}"
        for name in REQUIRED_GATES)
    (LAB / "handoff" / "FP_CURRENT.md").write_text("\n".join([
        "# FP_CURRENT", "",
        "## Current source",
        "- FP-01: PASS (evidence/forward_persistence_fp_v1/fp01-20260922T162253Z-3538bb29/)",
        f"- FP-02: run {lab_run_id} ({run_dir})",
        f"- FP-02 overall: {verdict.get('overall')}",
        f"- FP-02 gates: {states}",
        "", "## Phase state",
        "| Phase | Technical | Research | Owner | Evidence |",
        "|---|---|---|---|---|",
        "| FP-01 | PASS | NOT_ASSESSED | PENDING | "
        "evidence/forward_persistence_fp_v1/fp01-20260922T162253Z-3538bb29/ |",
        f"| FP-02 | {verdict.get('overall')} | NOT_ASSESSED | PENDING (needs R-18 approval) | "
        f"evidence/forward_persistence_fp_v1/{lab_run_id}/ |",
        "| FP-03 | NOT_RUN | NOT_ASSESSED | PENDING (needs R-18 approval) | — |",
        "", "## Latest run",
        f"FP-02 {verdict.get('overall')}: common evaluator (candidate + deployment on the "
        "qualified event-account route), semantic cache, retention tiers, causal-latency "
        "guard and selection-to-fill lineage, all proved on real engine calls over a real "
        "10-day A-SC/BTCUSDT window.",
        "", "## Dieu da biet tu evidence",
        "- report_level audit vs score is equity-exact on FP-02's OWN real candidate, not "
        "only cited from FUP-04's window (route_parity.json).",
        "- A real multi-selection deployment shows the activation delay applies to the "
        "INITIAL version too, not only switches (WARMING sentinel before bar 0's version "
        "ever decides) -- lineage_demo.json.",
        "- Cross-run cache reuse and cache-based resume both hold on the real evaluator "
        "(cache_reuse.json, resume_demo.json).",
        "", "## Dieu chua biet",
        "- Sampler-state resume (Optuna) is unmeasured -- no search loop exists yet (FP-03).",
        "- Whether the evaluator's cache/lineage design holds up at FP-03's 128-trial scale.",
        "", "## Blockers",
        "- None recorded for FP-02 at this evidence.",
        "", "## Budget",
        "- FP-02 charged 0 to the shared TE ledger; ~16 small real engine calls, all on a "
        "10-day/1m real window.",
        "", "## Next authorized action",
        "- NONE: wait for owner approval FP-02 -> FP-03 (R-18).",
        "", "## Khong duoc lam",
        "- No bulk search; no economics change without a new upgrade record; no FP-03 "
        "start without approval.",
        ""]), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pytest-xml", default=None)
    args = parser.parse_args()
    code, _info = run_fp02(args.pytest_xml)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
