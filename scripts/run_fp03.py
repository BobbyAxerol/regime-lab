#!/usr/bin/env python3
"""Build FP-03 artifacts (guide section 15): search-space qualification and
learning curve.

Real engine work, in order (never concurrent -- registered budget is
workers=1):

  1. Schema qualification (FP03.1): mapping + unknown-value rejection
     (cheap, no engine) + a real behavioral-effect fixture per tunable
     dimension (small window, matches FP-02's own 10-day reference).
  2. One real run_cutoff_walk_forward search per calibration origin
     (FP03.2/03.3), 256 trials, engine_report_level="score" (a real pilot
     on this exact scale hit a clean, RLIMIT_AS-caught MemoryError under
     the engine default profile -- the SAME audit-ledger accumulator
     FUP-04 already found and fixed on long frames; "score" is proven
     equity-exact, so this changes retention, never the objective).
     REUSES .cache/fp03_search_raw/origin_<date>.json if a prior run
     already wrote it (guide 11.2: an origin's search is not re-run to
     produce a nicer number, and a multi-hour real computation is not
     thrown away over a process restart).
  3. Sequential-prefix checkpoints (32/64/128/256) extracted from each
     origin's own real trial history -- never separately re-run.
  4. Forward comparison (FP03.4) on each REACHED checkpoint's selected
     candidate: real IS vs forward evaluation via fp.evaluator.
  5. Freeze (FP03.5): configs/forward_persistence_fp_v1/search_policy.json,
     from what was actually measured affordable, not asserted.

Usage:
  lab_venv/bin/python scripts/run_fp03.py --pytest-xml <junit xml of the FP-03 tests>
Exit 0 iff the FP-03 verifier reports PASS.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import resource
import sys
from datetime import datetime, timezone
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "src"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter, new_lab_run_id  # noqa: E402
from crypto_regime_lab.fp import GUIDE_VERSION, STUDY_ID  # noqa: E402
from crypto_regime_lab.fp import checkpoint_search as cs  # noqa: E402
from crypto_regime_lab.fp import forward_comparison as fc  # noqa: E402
from crypto_regime_lab.fp import param_qualification as pq  # noqa: E402
from crypto_regime_lab.fp import search_introspection as si  # noqa: E402
from crypto_regime_lab.fp.evaluator import default_economics  # noqa: E402
from crypto_regime_lab.fp.verifier_fp03 import (  # noqa: E402
    REQUIRED_GATES, verify_fp03,
)
from crypto_regime_lab.ra.ra05_market import load_real_bars  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402
from crypto_regime_lab.safety.process import lab_worker_env  # noqa: E402
from crypto_regime_lab.time_edge.compute_cache import ComputeCache  # noqa: E402

PHASE_ID = "FP-03"
CONFIG_DIR = LAB / "configs" / "forward_persistence_fp_v1"
RAW_SEARCH_CACHE = LAB / ".cache" / "fp03_search_raw"
CACHE_ROOT = "evidence/forward_persistence_fp_v1/compute-cache"
TRIALS_PER_ORIGIN = 256
SEARCH_SEED = 20260922
FIXTURE_WINDOW_START = "2023-06-01"
FIXTURE_WINDOW_END = "2023-06-11"

TEST_NODE_IDS = [
    "test_fp03_t_schema_mapping_matches_declared_bounds",
    "test_fp03_t_unknown_values_are_typed_rejections_not_silent_acceptance",
    "test_fp03_t_fixed_dimensions_never_enter_the_search_ranges",
    "test_fp03_t_sampler_identity_is_read_not_assumed",
    "test_fp03_t_ask_tell_sequence_empirically_concentrates",
    "test_fp03_t_classify_real_trials_counts_duplicates_and_uniques",
    "test_fp03_g_prefix_lower_checkpoint_is_a_true_prefix_of_higher",
    "test_fp03_g_prefix_not_reached_when_fewer_trials_than_level",
    "test_fp03_g_coverage_is_measured_not_a_fixed_adjective",
    "test_fp03_checkpoint_search_raises_on_missing_trial_records",
    "test_fp03_verifier_passes_on_a_valid_bundle",
    "test_fp03_verifier_fails_on_empty_dir",
    "test_fp03_verifier_fails_on_tampered_artifact",
    "test_fp03_verifier_fails_when_a_checkpoint_leaks_higher_budget_information",
]


def utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="microseconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _apply_resource_limits(policy) -> dict:
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


def build_schema_qualification(cache, *, producer: str) -> dict:
    frame, partitions = load_real_bars("BTCUSDT", start=FIXTURE_WINDOW_START,
                                       end=FIXTURE_WINDOW_END)
    frame = frame[["open", "high", "low", "close", "volume"]].copy()
    cutoff = frame.index[-1]
    base = {"coeff": 4, "AP": 20, "alpha.condition_threshold": 55,
           "novolumedata": False, "src_col": "close"}
    fixtures = [
        pq.behavioral_effect_fixture(cache, LAB, "A-SC", frame, base, "coeff", 2, 7,
                                     cutoff=cutoff, producer=f"{producer}-coeff"),
        pq.behavioral_effect_fixture(cache, LAB, "A-SC", frame, base, "AP", 10, 45,
                                     cutoff=cutoff, producer=f"{producer}-AP"),
        pq.behavioral_effect_fixture(cache, LAB, "A-SC", frame, base,
                                     "alpha.condition_threshold", 35, 75,
                                     cutoff=cutoff, producer=f"{producer}-threshold"),
    ]
    return {
        "schema": "regime_lab.fp03_schema_qualification.v1",
        "alpha_id": "A-SC",
        "fixture_window": {"start": FIXTURE_WINDOW_START, "end": FIXTURE_WINDOW_END,
                           "rows": int(len(frame)), "market_partitions_used": partitions},
        "schema_mapping": pq.schema_mapping_rows("A-SC"),
        "unknown_value_rejections": pq.unknown_value_rejections("A-SC", base_params=base),
        "fixed_dimensions": pq.fixed_dimensions_never_vary("A-SC"),
        "behavioral_fixtures": fixtures,
    }


def load_or_run_origin(origin_cutoff: str, *, trials: int, seed: int) -> dict:
    """Sequential-prefix / incremental-archive discipline applied at the
    orchestration level (guide 11.2): a raw search already on disk is
    reused verbatim, never re-run to produce a nicer number."""
    RAW_SEARCH_CACHE.mkdir(parents=True, exist_ok=True)
    cache_path = RAW_SEARCH_CACHE / f"origin_{origin_cutoff}.json"
    if cache_path.is_file():
        cached = json.loads(cache_path.read_text())
        if (cached.get("wf_result", {}).get("ok") is True
                and cached.get("trials_requested") == trials
                and cached.get("seed") == seed):
            cached["reused_from_cache"] = str(cache_path)
            return cached
    result = cs.run_origin_search(origin_cutoff=origin_cutoff, trials=trials, seed=seed,
                                  route="event")
    cache_path.write_text(json.dumps(result, default=str))
    result["reused_from_cache"] = None
    return result


def build_origin_record(cache, origin_cutoff: str, *, economics: dict, producer: str) -> dict:
    raw = load_or_run_origin(origin_cutoff, trials=TRIALS_PER_ORIGIN, seed=SEARCH_SEED)
    wf_result = raw["wf_result"]
    trial_records = cs._trial_records(wf_result) if wf_result.get("ok") else []
    checkpoints = (cs.checkpoints_from_prefix("A-SC", wf_result)
                  if wf_result.get("ok") else [])

    forward_rows = []
    if wf_result.get("ok") and checkpoints:
        import pandas as pd

        cutoff_ts = pd.Timestamp(origin_cutoff, tz="UTC")
        forward_end = cutoff_ts + pd.Timedelta(days=raw.get("forward_days", 28))
        frame, _partitions = load_real_bars(
            "BTCUSDT", start=raw["load_start"],
            end=(forward_end + pd.Timedelta(days=1)).strftime("%Y-%m-%d"))
        frame = frame[["open", "high", "low", "close", "volume"]].copy()
        level_wall = {c["level"]: c.get("estimated_wall_seconds") for c in checkpoints
                     if c.get("status") == "REACHED"}
        forward_rows = fc.checkpoint_forward_comparison(
            cache, LAB, "A-SC", frame, checkpoints, origin_cutoff=cutoff_ts,
            economics=economics, producer=f"{producer}-fwd",
            cumulative_wall_seconds_by_level=level_wall)

    return {
        "origin_cutoff": origin_cutoff, "wf_ok": bool(wf_result.get("ok")),
        "wf_error": wf_result.get("error"), "reused_from_cache": raw.get("reused_from_cache"),
        "trials_requested": raw["trials_requested"], "seed": raw["seed"],
        "frame_rows": raw["frame_rows"], "wall_seconds_measured": raw.get("wall_seconds_measured"),
        "instrumentation": raw.get("instrumentation"),
        "trial_records": trial_records, "checkpoints": checkpoints,
        "forward_comparison": forward_rows,
    }


def freeze_search_policy(origins: list[dict]) -> dict:
    """FP03.5: chosen from what was ACTUALLY measured affordable across the
    real origin searches above, never asserted ahead of the measurement.
    Guide's own escape clause applies verbatim if 256 truly was not
    affordable at every origin: reduce origins before reducing depth."""
    reached_256 = [o for o in origins if any(
        c.get("level") == 256 and c.get("status") == "REACHED" for c in o.get("checkpoints", []))]
    max_reached = max((max((c["level"] for c in o.get("checkpoints", [])
                           if c.get("status") == "REACHED"), default=0)
                      for o in origins), default=0)
    chosen_b_search = 256 if len(reached_256) == len(origins) and origins else max_reached
    blocker = (None if chosen_b_search == 256 else
              f"256 trials were not reached at every calibration origin "
              f"({len(reached_256)}/{len(origins)} reached it); "
              f"B_search frozen at the highest level ALL origins actually reached "
              f"({chosen_b_search}), per guide FP03.5's explicit rule "
              "(reduce origins before reducing committed depth, never silently lower both)")
    return {
        "schema": "regime_lab.fp03_search_policy.v1",
        "B_search": chosen_b_search,
        "Q_probe": 0,  # FP-03 ran no independent probes (guide 6.5 is optional in v1;
                       # not exercised this phase -- disclosed, not silently assumed)
        "representative_subset_size": 16,  # guide 6.6's own stated default ceiling
        "startup_exploration_policy": (
            f"optuna.samplers.TPESampler default (n_startup_trials="
            f"{si.installed_sampler_identity()['n_startup_trials_default']}, random "
            "sampling before it, TPE-guided after -- verified empirically on this "
            "install, not assumed from documentation)"),
        "pruning_policy": "none (stock Mode 4's own walk_forward call constructs no pruner "
                          "beyond Optuna's own defaults; verified from installed source, "
                          "not assumed)",
        "seed_policy": f"one fixed seed ({SEARCH_SEED}) per calibration origin this phase; "
                       "seed-randomness replication is not in FP-03's scope (guide 3.2: "
                       "'Initial optimizer seed count: một seed trong discovery')",
        "calibration_origins": list(cs.CALIBRATION_ORIGINS),
        "train_memory_days": cs.TRAIN_MEMORY_DAYS,
        "engine_report_level_used": "score",
        "engine_report_level_reason": "engine default profile hit a real, RLIMIT_AS-caught "
                                      "MemoryError on this exact scale (~300k-bar train "
                                      "window); score is FUP-04-proven equity-exact",
        "blocker": blocker,
        "frozen_at_utc": utcnow(),
    }


def run_fp03(pytest_xml: str | None) -> tuple[int, dict]:
    policy = SandboxPolicy.discover(LAB)
    policy.assert_lab_root_ok()
    limits = _apply_resource_limits(policy)
    started = utcnow()
    economics = default_economics()

    lab_run_id = new_lab_run_id("fp03")
    writer = EvidenceWriter(policy=policy, study_id=STUDY_ID, lab_run_id=lab_run_id)
    run_dir = writer.run_dir
    cache = ComputeCache(LAB, "fp03", cache_root=CACHE_ROOT)

    search_intro = si.demonstrate_ask_tell_sequence()
    schema_qual = build_schema_qualification(cache, producer=f"{lab_run_id}-sq")

    origin_records = []
    for origin_cutoff in cs.CALIBRATION_ORIGINS:
        origin_records.append(build_origin_record(cache, origin_cutoff, economics=economics,
                                                   producer=f"{lab_run_id}-{origin_cutoff}"))
    origins_doc = {"schema": "regime_lab.fp03_origin_searches.v1", "origins": origin_records}
    forward_doc = {"schema": "regime_lab.fp03_forward_comparison.v1",
                   "origins": [{"origin_cutoff": o["origin_cutoff"],
                               "forward_comparison": o["forward_comparison"]}
                              for o in origin_records]}
    search_policy = freeze_search_policy(origin_records)

    resource_budget = {
        "schema": "regime_lab.fp03_resource_budget.v1", "lab_run_id": lab_run_id,
        "fp03_wall_seconds_charged_to_shared_ledger": 0,
        "engine_calls_search_trials": sum(len(o["trial_records"]) for o in origin_records),
        "resource_limits_applied": limits,
        "note": "FP-03's own real engine calls; no shared TE ledger touched",
    }
    test_registry = {"schema": "regime_lab.fp03_test_registry.v1", "lab_run_id": lab_run_id,
                     "test_node_ids": TEST_NODE_IDS, "pytest_xml": pytest_xml}
    manifest = {
        "schema": "regime_lab.fp03_phase_manifest.v1", "lab_run_id": lab_run_id,
        "study_id": STUDY_ID, "phase_id": PHASE_ID, "guide_version": GUIDE_VERSION,
        "started_at_utc": started, "required_gates": list(REQUIRED_GATES), "artifacts": [],
    }

    with writer.attempt("fp03_build") as att:
        writer.write_json("schema_qualification.json", schema_qual,
                          schema="regime_lab.fp03_schema_qualification.v1")
        writer.write_json("search_introspection.json", search_intro,
                          schema="regime_lab.fp03_search_introspection.v1")
        writer.write_json("origin_searches.json", origins_doc,
                          schema="regime_lab.fp03_origin_searches.v1")
        writer.write_json("forward_comparison.json", forward_doc,
                          schema="regime_lab.fp03_forward_comparison.v1")
        writer.write_json("resource_budget.json", resource_budget,
                          schema="regime_lab.fp03_resource_budget.v1")
        writer.write_json("test_registry.json", test_registry,
                          schema="regime_lab.fp03_test_registry.v1")
        writer.write_json("phase_manifest.json", manifest,
                          schema="regime_lab.fp03_phase_manifest.v1")
        att.detail = {"run_dir": str(run_dir)}

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (CONFIG_DIR / "search_policy.json").write_text(
        json.dumps(search_policy, indent=2) + "\n", encoding="utf-8")
    (run_dir / "search_policy.json").write_text(
        json.dumps(search_policy, indent=2) + "\n", encoding="utf-8")

    report_text = render_report(lab_run_id=lab_run_id, run_dir=run_dir, schema_qual=schema_qual,
                                origin_records=origin_records, search_policy=search_policy,
                                resource_budget=resource_budget, started=started)
    handoff_text = render_handoff(lab_run_id=lab_run_id, run_dir=run_dir,
                                  search_policy=search_policy)
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
        for name in ("schema_qualification.json", "search_introspection.json",
                     "origin_searches.json", "forward_comparison.json", "search_policy.json",
                     "resource_budget.json", "test_registry.json", "report.md", "handoff.md",
                     "gate_receipt.json")
    ]
    (run_dir / "phase_manifest.json").write_text(
        json.dumps({**manifest, "written_at_utc": utcnow()}, indent=2) + "\n", encoding="utf-8")
    manifest["artifacts"].append(
        {"path": "phase_manifest.json", "sha256": sha256_file(run_dir / "phase_manifest.json")})

    verdict = verify_fp03(run_dir, pytest_xml=pytest_xml)
    receipt = json.loads((run_dir / "gate_receipt.json").read_text())
    receipt.update({"technical_gate": verdict["overall"], "verification": verdict,
                    "verified_at_utc": utcnow()})
    (run_dir / "gate_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n",
                                               encoding="utf-8")
    print(json.dumps({"run_dir": str(run_dir), "gates": verdict["gates"],
                      "overall": verdict["overall"]}, indent=2))
    return (0 if verdict["overall"] == "PASS" else 1), {"lab_run_id": lab_run_id,
                                                        "run_dir": str(run_dir)}


def render_report(*, lab_run_id, run_dir, schema_qual, origin_records, search_policy,
                  resource_budget, started) -> str:
    lines = [f"# FP-03 — Search-space qualification and learning curve ({lab_run_id})", "",
            f"- run_dir: {run_dir}", f"- started_at: {started}",
            f"- alpha: A-SC, calibration origins: {list(cs.CALIBRATION_ORIGINS)}",
            f"- real search-trial engine calls: {resource_budget['engine_calls_search_trials']}",
            "",
            "## FP03.1 — Schema qualification",
            f"- schema mapping consistent: "
            f"{all(r['engine_mapping_consistent'] for r in schema_qual['schema_mapping'])}",
            f"- unknown-value probes correctly rejected: "
            f"{all(r['correctly_rejected'] for r in schema_qual['unknown_value_rejections'])}",
            "- behavioral fixtures (real engine, real window):"]
    for f in schema_qual["behavioral_fixtures"]:
        lines.append(f"  - {f['dimension']} ({f['low_value']} vs {f['high_value']}): "
                     f"{f['outcome']}")
    lines += ["", "## FP03.2/03.3 — Calibration origins and checkpoint search"]
    for o in origin_records:
        lines.append(f"### {o['origin_cutoff']}")
        lines.append(f"- wf_ok: {o['wf_ok']}, error: {o['wf_error']}, "
                     f"reused_from_cache: {o['reused_from_cache']}")
        lines.append(f"- trials: {len(o['trial_records'])}/{o['trials_requested']} requested, "
                     f"wall: {o['wall_seconds_measured']}s, "
                     f"peak_mib: {(o['instrumentation'] or {}).get('peak_mib')}")
        for cp in o["checkpoints"]:
            if cp["status"] != "REACHED":
                lines.append(f"  - checkpoint {cp['level']}: {cp['status']}")
                continue
            lines.append(f"  - checkpoint {cp['level']}: selected trial "
                         f"{cp['selected']['trial_id']} obj={cp['selected']['objective']:.4f}, "
                         f"raw_coverage={cp['coverage']['raw_coverage_fraction']:.5f}, "
                         f"startup/adaptive={cp['search_classification']['startup_trial_count']}/"
                         f"{cp['search_classification']['adaptive_trial_count']}, "
                         f"unique={cp['search_classification']['unique_effective_candidates']}, "
                         f"est_wall={cp['estimated_wall_seconds']}s")
        lines.append("")
    lines += ["## FP03.4 — Forward comparison (IS vs forward, real engine both sides)"]
    for o in origin_records:
        lines.append(f"### {o['origin_cutoff']}")
        for row in o["forward_comparison"]:
            if row.get("status") != "REACHED":
                lines.append(f"  - checkpoint {row['level']}: {row.get('status')}")
                continue
            d = row["decay"]
            wall_delta = row["incremental_estimated_wall_seconds_vs_prior_checkpoint"]
            lines.append(
                f"  - checkpoint {row['level']}: IS obj={row['is_search_objective']:.4f} "
                f"(Δ vs prior={row['is_improvement_vs_prior_checkpoint']}), "
                f"forward mean_daily_return={d['forward_metrics']['mean_daily_return']:.6f} "
                f"(Δ vs prior={row['forward_mean_daily_return_improvement_vs_prior_checkpoint']}), "
                f"D_mean_daily_return={d['D_mean_daily_return']:.6f} "
                f"(D=IS-FWD, positive=worse decay), "
                f"incremental_est_wall="
                f"{'n/a' if wall_delta is None else f'{wall_delta}s'}")
        lines.append("")
    lines += ["## FP03.5 — Frozen search policy",
             f"```json\n{json.dumps(search_policy, indent=2)}\n```", "",
             "## Permitted conclusions",
             "- Technical: schema qualified, sequential-prefix checkpoints extracted from "
             "real engine search history, forward comparison computed on real IS/forward "
             "candidate evaluations, budget frozen from measured affordability.",
             "- Research: NOT_ASSESSED -- no market/edge claim in FP-03; forward-vs-IS numbers "
             "describe search-depth behavior on calibration data only.",
             "- Owner review: PENDING; FP-04 needs its own approval (R-18).", ""]
    return "\n".join(lines)


def render_handoff(*, lab_run_id, run_dir, search_policy) -> str:
    return "\n".join([
        f"# FP-03 handoff ({lab_run_id})", "",
        f"- run_dir: {run_dir}",
        f"- frozen B_search: {search_policy['B_search']}"
        + (f" -- BLOCKER: {search_policy['blocker']}" if search_policy.get("blocker") else ""),
        "- next authorized action: NONE until the owner approves FP-03 -> FP-04 (R-18), "
        "unless already pre-approved and recorded.",
        "- FP-04 (guide 16) must reuse: the frozen search_policy.json budget, "
        "fp.evaluator for forward-label evaluations, the calibration-origin selection rule.",
        ""])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pytest-xml", default=None)
    args = parser.parse_args()
    code, _info = run_fp03(args.pytest_xml)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
