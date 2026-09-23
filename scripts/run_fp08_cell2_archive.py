#!/usr/bin/env python3
"""Build FP-08's cell-2 replication archive (guide FP08.1: a second cell by
a pre-registered rule, not by PnL) -- the SAME historical-forward-ledger
construction FP-04 already built for cell 1 (A-SC/BTCUSDT), reused verbatim
(forward_ledger.py, checkpoint_search.py, verifier_fp04.py are all already
symbol-agnostic or take the origin grid as a parameter -- no new logic, only
a new symbol/grid), applied to cell 2.

Cell 2 = A-SC/ETHUSDT (owner-approved, evidence/regime_time_edge_ra_v1/
owner_decisions.jsonl decision_id dec-b5a96eb125bb80cd): ETHUSDT is the next
symbol after BTCUSDT in the registered 5-symbol list; A-SC is held fixed
because FP-03's search-space qualification (schema, BEHAVIOR_DIFFERS,
B_search=256) is an ALPHA-level property, not symbol-level, so it carries
over unchanged -- FP-03 is never re-run for cell 2.

3 origins (reusing FP-03's OWN precedented CALIBRATION_ORIGINS dates
verbatim: 2021-06-01, 2022-06-01, 2023-06-01 -- not a new number invented
for this phase), a disclosed, cost-proportionate partial scope: a real
8-trial probe measured ETHUSDT running ~2x slower per trial than BTCUSDT
(24.1s vs ~11s), so B_search=256/origin here projects to ~1.7h/origin
search-only, ~5.14h for 3 origins -- already a large real commitment,
measured and disclosed via AskUserQuestion before this script was written.

Usage:
  lab_venv/bin/python scripts/run_fp08_cell2_archive.py --pytest-xml <junit xml>
Exit 0 iff the (reused) FP-04 verifier reports PASS on this cell's own
archive.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import resource
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "src"))

from crypto_regime_lab.fp import GUIDE_VERSION, STUDY_ID  # noqa: E402
from crypto_regime_lab.fp import checkpoint_search as cs  # noqa: E402
from crypto_regime_lab.fp import forward_ledger as fl  # noqa: E402
from crypto_regime_lab.fp.evaluator import default_economics  # noqa: E402
from crypto_regime_lab.fp.verifier_fp04 import (  # noqa: E402
    MIN_SUPPORT_FOR_MODEL_READY, REQUIRED_GATES, verify_fp04,
)
from crypto_regime_lab.evidence.manifest import EvidenceWriter, new_lab_run_id  # noqa: E402
from crypto_regime_lab.ra.ra05_market import load_real_bars  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402
from crypto_regime_lab.safety.process import lab_worker_env  # noqa: E402
from crypto_regime_lab.selector.alpha_schemas import SCHEMAS  # noqa: E402
from crypto_regime_lab.time_edge.compute_cache import ComputeCache  # noqa: E402

PHASE_ID = "FP-08-CELL2-ARCHIVE"
ALPHA_ID = "A-SC"
SYMBOL = "ETHUSDT"
CELL2_ORIGIN_GRID = ("2021-06-01", "2022-06-01", "2023-06-01")
CONFIG_DIR = LAB / "configs" / "forward_persistence_fp_v1"
RAW_SEARCH_CACHE = LAB / ".cache" / "fp08_cell2_search_raw"
CACHE_ROOT = "evidence/forward_persistence_fp_v1/compute-cache"
SEARCH_SEED = 20260922                # same seed as FP-04: guide 3.2, one seed across discovery
FORWARD_HORIZON_DAYS = 28
TRAIN_MEMORY_DAYS = cs.TRAIN_MEMORY_DAYS
DISTANCE_THRESHOLD = 0.12
FROZEN_SEARCH_POLICY = CONFIG_DIR / "search_policy.json"

TEST_NODE_IDS = [
    "test_run_origin_search_defaults_to_btcusdt_unchanged",
    "test_run_origin_search_accepts_a_different_symbol_and_actually_loads_its_own_data",
    "test_run_origin_search_accepts_a_different_alpha_id_too",
    "test_load_origin_is_frame_defaults_to_btcusdt_unchanged",
    "test_load_origin_is_frame_accepts_a_different_symbol",
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


def _frozen_b_search() -> int:
    policy = json.loads(FROZEN_SEARCH_POLICY.read_text())
    if policy.get("blocker") is not None:
        raise SystemExit(f"FP-03 search_policy.json carries a blocker, refusing to proceed: "
                         f"{policy['blocker']}")
    return int(policy["B_search"])


def _frozen_representative_subset_size() -> int:
    policy = json.loads(FROZEN_SEARCH_POLICY.read_text())
    return int(policy["representative_subset_size"])


def load_or_run_origin(origin_cutoff: str, *, trials: int, seed: int) -> dict:
    RAW_SEARCH_CACHE.mkdir(parents=True, exist_ok=True)
    cache_path = RAW_SEARCH_CACHE / f"origin_{origin_cutoff}.json"
    if cache_path.is_file():
        cached = json.loads(cache_path.read_text())
        if (cached.get("wf_result", {}).get("ok") is True
                and cached.get("trials_requested") == trials
                and cached.get("seed") == seed
                and cached.get("symbol") == SYMBOL):
            cached["reused_from_cache"] = str(cache_path)
            return cached
    result = cs.run_origin_search(origin_cutoff=origin_cutoff, trials=trials, seed=seed,
                                  route="event", train_memory_days=TRAIN_MEMORY_DAYS,
                                  forward_days=FORWARD_HORIZON_DAYS, symbol=SYMBOL,
                                  alpha_id=ALPHA_ID)
    cache_path.write_text(json.dumps(result, default=str))
    result["reused_from_cache"] = None
    return result


def build_origin_entry(cache, schema, origin_cutoff: str, *, b_search: int,
                       representative_subset_size: int, economics: dict, producer: str) -> dict:
    raw = load_or_run_origin(origin_cutoff, trials=b_search, seed=SEARCH_SEED)
    wf_result = raw["wf_result"]
    wf_ok = bool(wf_result.get("ok"))
    trial_records = cs._trial_records(wf_result) if wf_ok else []

    regions = []
    if wf_ok and trial_records:
        regions = fl.build_regions_for_origin(
            schema, origin_cutoff=origin_cutoff, trial_records=trial_records,
            distance_threshold=DISTANCE_THRESHOLD,
            max_representatives=representative_subset_size)

        import pandas as pd

        cutoff_ts = pd.Timestamp(origin_cutoff, tz="UTC")
        forward_end = cutoff_ts + pd.Timedelta(days=FORWARD_HORIZON_DAYS)
        frame, _partitions = load_real_bars(
            SYMBOL, start=raw["load_start"],
            end=(forward_end + pd.Timedelta(days=1)).strftime("%Y-%m-%d"))
        frame = frame[["open", "high", "low", "close", "volume"]].copy()
        for region in regions:
            forward_result = fl.evaluate_region_forward(
                cache, LAB, ALPHA_ID, frame, region, origin_cutoff=cutoff_ts,
                forward_horizon_days=FORWARD_HORIZON_DAYS, economics=economics,
                producer=f"{producer}-{region['region_id']}")
            region["_forward_result"] = forward_result

    return {
        "origin_cutoff": origin_cutoff, "wf_ok": wf_ok, "wf_error": wf_result.get("error"),
        "reused_from_cache": raw.get("reused_from_cache"), "seed": raw["seed"],
        "trials_requested": raw["trials_requested"],
        "market_partitions_used": raw["market_partitions_used"],
        "load_start": raw["load_start"], "load_end": raw["load_end"],
        "frame_rows": raw["frame_rows"], "wall_seconds_measured": raw.get("wall_seconds_measured"),
        "instrumentation": raw.get("instrumentation"),
        "trial_records": trial_records,
        "regions": [{k: v for k, v in r.items() if k != "_forward_result"} for r in regions],
        "_regions_with_forward": regions,
    }


def build_ledger_records(origin_entries: list[dict], geometry_version: str) -> dict:
    records = []
    for entry in origin_entries:
        origin_cutoff = entry["origin_cutoff"]
        as_of = (datetime.fromisoformat(origin_cutoff).replace(tzinfo=timezone.utc)
                + timedelta(days=FORWARD_HORIZON_DAYS)).isoformat()
        if not entry["wf_ok"]:
            placeholder_region = {"region_id": "R_NONE", "medoid_trial_id": None,
                                  "medoid_params": None,
                                  "is_quality_distribution": {"mean": None},
                                  "historical_support_within_origin": 0}
            records.append(fl.ledger_record(
                origin_cutoff=origin_cutoff, forward_horizon_days=FORWARD_HORIZON_DAYS,
                region=placeholder_region, forward_result=None, wf_ok=False, as_of=as_of,
                geometry_version=geometry_version))
            continue
        for region in entry["_regions_with_forward"]:
            forward_result = region["_forward_result"]
            records.append(fl.ledger_record(
                origin_cutoff=origin_cutoff, forward_horizon_days=FORWARD_HORIZON_DAYS,
                region=region, forward_result=forward_result, wf_ok=True, as_of=as_of,
                geometry_version=geometry_version))
    model_ready = sum(1 for r in records if r["maturity_state"] == "matured_forward_record"
                      and r["region_support_within_origin"] >= MIN_SUPPORT_FOR_MODEL_READY)
    return {
        "schema": "regime_lab.fp04_ledger_records.v1", "records": records,
        "support_summary": {
            "model_ready_count": model_ready,
            "descriptive_only_count": len(records) - model_ready,
            "min_support_for_model_ready": MIN_SUPPORT_FOR_MODEL_READY,
        },
    }


def freeze_region_policy(*, b_search: int, representative_subset_size: int) -> dict:
    grid_check = fl.validate_origin_grid(CELL2_ORIGIN_GRID, train_memory_days=TRAIN_MEMORY_DAYS,
                                         forward_horizon_days=FORWARD_HORIZON_DAYS)
    if not grid_check["all_valid"]:
        raise SystemExit(f"cell-2 origin grid failed validation: {grid_check}")
    overlaps = fl.flag_window_overlaps(CELL2_ORIGIN_GRID, train_memory_days=TRAIN_MEMORY_DAYS,
                                       forward_horizon_days=FORWARD_HORIZON_DAYS)
    schema = SCHEMAS[ALPHA_ID]
    geometry_version = fl.geometry_version_id(schema, distance_threshold=DISTANCE_THRESHOLD,
                                              max_representatives=representative_subset_size)
    return {
        "schema": "regime_lab.fp04_region_policy.v1",
        "cell": "cell2_replication", "alpha_id": ALPHA_ID, "symbol": SYMBOL,
        "origin_grid": list(CELL2_ORIGIN_GRID),
        "origin_grid_scope_note": (
            f"guide FP08.1's replication cell: {len(CELL2_ORIGIN_GRID)} origins, reusing FP-03's "
            "own precedented CALIBRATION_ORIGINS dates verbatim, not a new number invented for "
            "this phase. A disclosed, cost-proportionate partial scope: a real 8-trial probe "
            "measured ETHUSDT running ~2x slower per trial than BTCUSDT (24.1s vs ~11s), making a "
            "12-origin cell-2 archive (matching cell 1) cost roughly 2x cell 1's own ~9.5h search "
            "-- owner-approved at 3 origins via AskUserQuestion, decision dec-b5a96eb125bb80cd, "
            "evidence/regime_time_edge_ra_v1/owner_decisions.jsonl."),
        "b_search": b_search, "b_search_source": "configs/forward_persistence_fp_v1/search_policy.json "
                                                  "(FP-03's own frozen depth, ALPHA-level, reused "
                                                  "verbatim for this alpha regardless of symbol)",
        "search_seed": SEARCH_SEED, "train_memory_days": TRAIN_MEMORY_DAYS,
        "forward_horizon_days": FORWARD_HORIZON_DAYS,
        "distance_threshold": DISTANCE_THRESHOLD,
        "representative_subset_size": representative_subset_size,
        "geometry_version": geometry_version,
        "window_overlaps": overlaps,
        "frozen_at_utc": utcnow(),
    }


def run_cell2_archive(pytest_xml: str | None) -> tuple[int, dict]:
    policy = SandboxPolicy.discover(LAB)
    policy.assert_lab_root_ok()
    limits = _apply_resource_limits(policy)
    started = utcnow()
    economics = default_economics()
    schema = SCHEMAS[ALPHA_ID]

    b_search = _frozen_b_search()
    representative_subset_size = _frozen_representative_subset_size()
    region_policy = freeze_region_policy(b_search=b_search,
                                         representative_subset_size=representative_subset_size)

    lab_run_id = new_lab_run_id("fp08cell2archive")
    writer = EvidenceWriter(policy=policy, study_id=STUDY_ID, lab_run_id=lab_run_id)
    run_dir = writer.run_dir
    cache = ComputeCache(LAB, "fp08cell2", cache_root=CACHE_ROOT)

    origin_entries = []
    for origin_cutoff in CELL2_ORIGIN_GRID:
        origin_entries.append(build_origin_entry(
            cache, schema, origin_cutoff, b_search=b_search,
            representative_subset_size=representative_subset_size, economics=economics,
            producer=f"{lab_run_id}-{origin_cutoff}"))

    ledger = {"schema": "regime_lab.fp04_origin_ledger.v1", "cell": "cell2_replication", "origins": [
        {k: v for k, v in e.items() if k != "_regions_with_forward"} for e in origin_entries]}
    ledger_records_doc = build_ledger_records(origin_entries, region_policy["geometry_version"])

    fresh_trials = sum(len(e["trial_records"]) for e in origin_entries
                       if e["reused_from_cache"] is None and e["wf_ok"])
    reused_origins = [e["origin_cutoff"] for e in origin_entries if e["reused_from_cache"] is not None]
    wall_times = [e["wall_seconds_measured"] for e in origin_entries
                 if e.get("wall_seconds_measured") is not None]
    resource_budget = {
        "schema": "regime_lab.fp04_resource_budget.v1", "lab_run_id": lab_run_id,
        "cell": "cell2_replication",
        "engine_calls_search_trials_fresh": fresh_trials,
        "reused_origins": reused_origins,
        "resource_limits_applied": limits,
        "measured_search_wall_seconds_total": round(sum(wall_times), 2) if wall_times else None,
        "measured_search_wall_seconds_by_origin": dict(zip(CELL2_ORIGIN_GRID, wall_times)),
    }
    test_registry = {"schema": "regime_lab.fp04_test_registry.v1", "lab_run_id": lab_run_id,
                     "test_node_ids": TEST_NODE_IDS, "pytest_xml": pytest_xml}
    manifest = {
        "schema": "regime_lab.fp04_phase_manifest.v1", "lab_run_id": lab_run_id,
        "study_id": STUDY_ID, "phase_id": PHASE_ID, "guide_version": GUIDE_VERSION,
        "started_at_utc": started, "required_gates": list(REQUIRED_GATES), "artifacts": [],
    }

    with writer.attempt("fp08_cell2_archive_build") as att:
        writer.write_json("origin_ledger.json", ledger, schema="regime_lab.fp04_origin_ledger.v1")
        writer.write_json("ledger_records.json", ledger_records_doc,
                          schema="regime_lab.fp04_ledger_records.v1")
        writer.write_json("region_policy.json", region_policy,
                          schema="regime_lab.fp04_region_policy.v1")
        writer.write_json("resource_budget.json", resource_budget,
                          schema="regime_lab.fp04_resource_budget.v1")
        writer.write_json("test_registry.json", test_registry,
                          schema="regime_lab.fp04_test_registry.v1")
        writer.write_json("phase_manifest.json", manifest,
                          schema="regime_lab.fp04_phase_manifest.v1")
        att.detail = {"run_dir": str(run_dir)}

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (CONFIG_DIR / "fp08_cell2_region_policy.json").write_text(
        json.dumps(region_policy, indent=2) + "\n", encoding="utf-8")

    finished = utcnow()
    report_text = render_report(lab_run_id=lab_run_id, run_dir=run_dir, origin_entries=origin_entries,
                                ledger_records_doc=ledger_records_doc, region_policy=region_policy,
                                resource_budget=resource_budget, started=started, finished=finished)
    (run_dir / "report.md").write_text(report_text, encoding="utf-8")
    (run_dir / "handoff.md").write_text(
        f"# FP-08 cell-2 archive handoff ({lab_run_id})\n\nrun_dir: {run_dir}\n"
        "next: fp.selector_b/selector_c fit + fp.locked_study for this cell, "
        "then run_fp08.py combines both cells.\n", encoding="utf-8")
    (run_dir / "gate_receipt.json").write_text(json.dumps({
        "schema": "regime_lab.fp_gate.v1", "phase_id": PHASE_ID, "guide_version": GUIDE_VERSION,
        "lab_run_id": lab_run_id, "required_gates": list(REQUIRED_GATES),
        "technical_gate": "PENDING_VERIFICATION", "research_status": "NOT_ASSESSED",
        "owner_review": {"status": "PENDING", "decision_ref": "dec-b5a96eb125bb80cd"},
        "can_start_next_phase": False,
    }, indent=2) + "\n", encoding="utf-8")
    manifest["artifacts"] = [
        {"path": name, "sha256": sha256_file(run_dir / name)}
        for name in ("origin_ledger.json", "ledger_records.json", "region_policy.json",
                     "resource_budget.json", "test_registry.json", "report.md", "handoff.md",
                     "gate_receipt.json")
    ]
    (run_dir / "phase_manifest.json").write_text(
        json.dumps({**manifest, "written_at_utc": utcnow()}, indent=2) + "\n", encoding="utf-8")
    manifest["artifacts"].append(
        {"path": "phase_manifest.json", "sha256": sha256_file(run_dir / "phase_manifest.json")})

    verdict = verify_fp04(run_dir, pytest_xml=pytest_xml)
    receipt = json.loads((run_dir / "gate_receipt.json").read_text())
    receipt.update({"technical_gate": verdict["overall"], "verification": verdict,
                    "verified_at_utc": utcnow()})
    (run_dir / "gate_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n",
                                               encoding="utf-8")
    print(json.dumps({"run_dir": str(run_dir), "gates": verdict["gates"],
                      "overall": verdict["overall"]}, indent=2))
    return (0 if verdict["overall"] == "PASS" else 1), {"lab_run_id": lab_run_id,
                                                        "run_dir": str(run_dir)}


def render_report(*, lab_run_id, run_dir, origin_entries, ledger_records_doc, region_policy,
                  resource_budget, started, finished) -> str:
    support = ledger_records_doc["support_summary"]
    records = ledger_records_doc["records"]
    matured = [r for r in records if r["maturity_state"] == "matured_forward_record"]
    censored = [r for r in records if r["maturity_state"] == "censored_or_failed_record"]
    decays = [r["decay_D_mean_daily_return"] for r in matured
             if r["decay_D_mean_daily_return"] is not None]
    wall_times = [e["wall_seconds_measured"] for e in origin_entries
                 if e.get("wall_seconds_measured") is not None]
    total_wall_search = sum(wall_times)
    n_ok = sum(1 for e in origin_entries if e["wf_ok"])
    lines = [f"# FP-08 cell-2 archive — A-SC/ETHUSDT ({lab_run_id})", "",
            f"- run_dir: {run_dir}", f"- started_at: {started}, finished_at: {finished}",
            f"- alpha: {ALPHA_ID}, symbol: {SYMBOL}, origins: {len(region_policy['origin_grid'])} "
            "(guide FP08.1 replication cell, owner-approved scope dec-b5a96eb125bb80cd)",
            f"- B_search (reused from FP-03's frozen search_policy.json, alpha-level): "
            f"{region_policy['b_search']}",
            f"- origins searched OK / total: {n_ok}/{len(origin_entries)}",
            f"- total records: {len(records)}, matured: {len(matured)}, censored: {len(censored)}",
            f"- fresh engine search-trial calls this run: "
            f"{resource_budget['engine_calls_search_trials_fresh']}",
            f"- sum of per-origin search-only wall_seconds_measured: {total_wall_search:.1f}s "
            f"({total_wall_search / 3600:.2f}h) over {len(wall_times)} origins, "
            f"mean {(total_wall_search / len(wall_times) if wall_times else 0):.1f}s/origin "
            "(compare cell 1/BTCUSDT's own ~2786-3042s/origin -- ETHUSDT measured ~2x slower "
            "per trial in the pre-run probe, disclosed before this run)"]
    if decays:
        positive = sum(1 for d in decays if d > 0)
        lines += [f"- decay_D_mean_daily_return (IS - forward; positive=worse) over {len(decays)} "
                 f"matured records: min={min(decays):.6f}, max={max(decays):.6f}, "
                 f"mean={sum(decays) / len(decays):.6f}",
                 f"- positive (worse) decay: {positive}/{len(decays)}"]
    lines += ["", "## Per-origin results"]
    for e in origin_entries:
        lines.append(f"### {e['origin_cutoff']}")
        if not e["wf_ok"]:
            lines.append(f"- wf_ok: False, error: {e['wf_error']} -- CENSORED, no region built")
            lines.append("")
            continue
        lines.append(f"- wf_ok: True, trials: {len(e['trial_records'])}/{e['trials_requested']}, "
                     f"wall: {e['wall_seconds_measured']}s, "
                     f"peak_mib: {(e['instrumentation'] or {}).get('peak_mib')}, "
                     f"reused_from_cache: {e['reused_from_cache']}")
        lines.append(f"- regions built: {len(e['regions'])}")
        for region in e["_regions_with_forward"]:
            fwd = region["_forward_result"]
            if fwd and fwd["forward_ok"]:
                d = fwd["decay"]
                lines.append(
                    f"  - {region['region_id']}: support={region['historical_support_within_origin']}, "
                    f"is_objective_mean={region['is_quality_distribution']['mean']:.4f}, "
                    f"forward_mean_daily_return={d['forward_metrics']['mean_daily_return']:.6f}, "
                    f"D_mean_daily_return={d['D_mean_daily_return']:.6f}")
            else:
                reason = fwd["reason"] if fwd else "no forward attempt recorded"
                lines.append(f"  - {region['region_id']}: CENSORED -- {reason}")
        lines.append("")
    lines += ["## Support summary",
             f"- model_ready_count: {support['model_ready_count']}, "
             f"descriptive_only_count: {support['descriptive_only_count']}",
             "", "## Permitted conclusions",
             "- Technical: a real historical forward ledger was built at 3 real chronological "
             "origins on A-SC/ETHUSDT, reusing FP-04's own already-tested archive machinery "
             "unchanged (forward_ledger.py, checkpoint_search.py, verifier_fp04.py).",
             "- Research: NOT_ASSESSED -- this stage builds cell 2's raw candidate archive only; "
             "it makes no market/edge claim. Selector B/C fit and the locked A/B/C study for this "
             "cell come next, then run_fp08.py combines both cells for guide FP08.3-.5.",
             "- Scope: 3 of cell 1's 12 origins -- an explicit, disclosed, cost-proportionate "
             "partial replication (ETHUSDT measured ~2x slower per search trial than BTCUSDT).",
             ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pytest-xml", default=None)
    args = parser.parse_args()
    code, _info = run_cell2_archive(args.pytest_xml)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
