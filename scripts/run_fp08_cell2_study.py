#!/usr/bin/env python3
"""Build FP-08's cell-2 (A-SC/ETHUSDT) Selector B/C fit + locked A/B/C study
-- the SAME mechanism FP-05/06/07 already proved for cell 1
(fp.selector_b/selector_c/locked_study are reused verbatim; the only new
code here is cell-2's own data plumbing), applied to cell 2's 3-origin
archive (guide FP08.1's owner-approved replication scope).

Cell 2 CANNOT run its own walk-forward OOF alpha selection (fp.selector_b.
walk_forward_oof needs >= MIN_TRAIN_ORIGINS+1 = 5 origins to produce even
one validation fold; cell 2 has 3 total) -- ALPHA_B/ALPHA_C are reused
verbatim from cell 1's own already-selected values (10.0 for both, read
from FP-05/06's committed evidence), a necessary reuse, not a choice among
alternatives, and consistent with guide 19 item 9's own 'do not change the
algorithm from a prefix outcome' principle extended across cells.

Correction on record (evidence/regime_time_edge_ra_v1/owner_decisions.jsonl,
decision dec-61a43dad79d0ec5c): fp.locked_study.walk_forward_b_selection/
walk_forward_c_selection do NOT enforce selector_b.MIN_FIT_ORIGINS=12 (that
floor gates a different, diagnostic-only scoring path selector_b.py itself
uses, never called from locked_study.py) -- they only require the training
view to be non-empty, true from cell 2's 2nd origin onward. Selector B/C
DO genuinely attempt a fit and scoring at origins 2 and 3; whether anything
clears the registered utility/support floor is real, measured, not
foreclosed by construction.

The continuous frame (2021-06-01..2024-01-01, ~1.36M bars) is close to
FP-07's own ~1.58M-bar scale and needs the SAME disclosed working-memory
exception (registered 4 GiB -> 7 GiB) FP-07 already established and the
owner already approved (decision dec-9cc3ec3e712cf61b) for exactly this
failure mode (a single continuous account this large is a virtual-address-
space ceiling issue, not a host RAM shortage) -- reused here under the
same precedent, disclosed in this run's own artifacts, not a silent reuse.

Usage:
  lab_venv/bin/python scripts/run_fp08_cell2_study.py --archive-run-dir <path> \
      --pytest-xml <junit xml>
"""
from __future__ import annotations

import argparse
import json
import os
import resource
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "src"))

from crypto_regime_lab.fp import locked_study as ls  # noqa: E402
from crypto_regime_lab.fp import selector_b as sb  # noqa: E402
from crypto_regime_lab.fp import selector_c as sc  # noqa: E402
from crypto_regime_lab.fp.evaluator import default_economics, run_deployment  # noqa: E402
from crypto_regime_lab.ra.ra05_market import load_real_bars  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402
from crypto_regime_lab.safety.process import lab_worker_env  # noqa: E402
from crypto_regime_lab.selector.alpha_schemas import SCHEMAS  # noqa: E402
from crypto_regime_lab.time_edge.compute_cache import ComputeCache  # noqa: E402

ALPHA_ID = "A-SC"
SYMBOL = "ETHUSDT"
CELL2_ORIGIN_GRID = ("2021-06-01", "2022-06-01", "2023-06-01")
RAW_SEARCH_CACHE = LAB / ".cache" / "fp08_cell2_search_raw"
FEATURE_CACHE = LAB / ".cache" / "fp08_cell2_features" / "rows.json"
CACHE_ROOT = "evidence/forward_persistence_fp_v1/compute-cache"
FRAME_START = "2021-06-01"
FRAME_END = "2024-01-01"

ALPHA_B = 10.0
ALPHA_B_SOURCE = ("evidence/forward_persistence_fp_v1/fp05-20260923T163839Z-79516650/"
                  "model_selection.json:selected_alpha (reused verbatim -- cell 2's 3 origins "
                  "cannot run their own walk-forward OOF alpha selection)")
ALPHA_C = 10.0
ALPHA_C_SOURCE = ("evidence/forward_persistence_fp_v1/fp06-20260923T173537Z-1fa316c7/"
                  "oof_diagnostics_c.json:selected_alpha_c (reused verbatim, same reason)")

FP08_RLIMIT_AS_GIB = 7.0
FP08_RLIMIT_AS_PRECEDENT = "dec-9cc3ec3e712cf61b"


class Cell2StudyError(RuntimeError):
    """A cell-2 study step was internally inconsistent."""


def utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="microseconds")


def _apply_resource_limits(policy) -> dict:
    env = lab_worker_env(policy)
    for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
               "NUMEXPR_NUM_THREADS", "NUMBA_NUM_THREADS"):
        os.environ[key] = env[key]
    budget = policy.raw["resource_budget"]
    registered_gib = budget["working_memory_gib"]
    applied_gib = FP08_RLIMIT_AS_GIB
    cap_bytes = int(applied_gib * (1 << 30))
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    resource.setrlimit(resource.RLIMIT_AS, (cap_bytes, hard))
    return {"cpu_limit": env["OMP_NUM_THREADS"], "rlimit_as_gib": applied_gib,
            "registered_rlimit_as_gib": registered_gib,
            "exception_applied": applied_gib != registered_gib,
            "exception_precedent_decision_id": FP08_RLIMIT_AS_PRECEDENT}


def load_cell2_wf_result(origin_cutoff: str) -> dict:
    path = RAW_SEARCH_CACHE / f"origin_{origin_cutoff}.json"
    if not path.is_file():
        raise Cell2StudyError(f"no cached cell-2 search result for origin {origin_cutoff} at {path}")
    raw = json.loads(path.read_text())
    if not raw.get("wf_result", {}).get("ok"):
        raise Cell2StudyError(f"cell-2 origin {origin_cutoff}'s cached search was not wf_ok")
    return raw["wf_result"]


def load_or_build_feature_rows(cache, archive_run_dir: Path) -> tuple[list[dict], bool]:
    ledger = json.loads((archive_run_dir / "ledger_records.json").read_text())
    origins_doc = json.loads((archive_run_dir / "origin_ledger.json").read_text())
    if FEATURE_CACHE.is_file():
        cached = json.loads(FEATURE_CACHE.read_text())
        if len(cached) == len(ledger["records"]):
            return cached, True

    regions_by_key = {}
    for origin in origins_doc["origins"]:
        for region in origin.get("regions", []):
            regions_by_key[(origin["origin_cutoff"], region["region_id"])] = region

    schema = SCHEMAS[ALPHA_ID]
    economics = default_economics()
    rows, frame_cache = [], {}
    for record in ledger["records"]:
        origin_cutoff = record["origin_cutoff"]
        if origin_cutoff not in frame_cache:
            frame_cache[origin_cutoff] = sb.load_origin_is_frame(ALPHA_ID, origin_cutoff, symbol=SYMBOL)
        region = regions_by_key[(origin_cutoff, record["region_id"])]
        row = sb.build_feature_row(cache, LAB, ALPHA_ID, schema, record, region,
                                   economics=economics, producer="fp08-cell2-features",
                                   is_frame=frame_cache[origin_cutoff])
        rows.append(row)
    FEATURE_CACHE.parent.mkdir(parents=True, exist_ok=True)
    FEATURE_CACHE.write_text(json.dumps(rows))
    return rows, False


def build_c_rows(b_rows: list[dict]) -> list[dict]:
    origins = sorted({r["origin_cutoff"] for r in b_rows})
    context_by_origin = {o: sc.compute_context_features(sb.load_origin_is_frame(ALPHA_ID, o, symbol=SYMBOL))
                         for o in origins}
    return [sc.build_c_row(row, context_by_origin[row["origin_cutoff"]]) for row in b_rows]


def record_id_for_d1(result: dict, *, fallback_result) -> tuple[str | None, str | None]:
    rid = result.get("record_id")
    if rid is not None:
        return rid, None
    if result.get("source") == "FALLBACK_TO_B" and fallback_result is not None:
        rid2 = fallback_result.get("record_id")
        if rid2 is not None:
            return rid2, None
    return None, (f"{result.get('source')}: no forward-labelled record for this origin's "
                  f"selection ({result.get('reason', 'no reason given')})")


def run_cell2_study(archive_run_dir: str, pytest_xml: str | None) -> tuple[int, dict]:
    policy = SandboxPolicy.discover(LAB)
    policy.assert_lab_root_ok()
    limits = _apply_resource_limits(policy)
    started = utcnow()
    t_wall_start = time.perf_counter()
    economics = default_economics()
    archive_dir = Path(archive_run_dir)

    cache = ComputeCache(LAB, "fp08cell2", cache_root=CACHE_ROOT)
    b_rows, reused_features = load_or_build_feature_rows(cache, archive_dir)
    c_rows = build_c_rows(b_rows)
    origins_sorted = sorted({r["origin_cutoff"] for r in b_rows},
                            key=lambda o: next(r["origin_time"] for r in b_rows
                                              if r["origin_cutoff"] == o))
    if list(origins_sorted) != list(CELL2_ORIGIN_GRID):
        raise Cell2StudyError(f"archive origins {origins_sorted} do not match the frozen cell-2 "
                              f"grid {CELL2_ORIGIN_GRID}")

    selections_by_origin = {"A_STOCK_CAL": {}, "B_FP_PERSISTENCE": {}, "C_FP_CONTEXT": {}}
    for origin in origins_sorted:
        wf = load_cell2_wf_result(origin)
        a_params = ls.arm_a_selection(wf)
        selections_by_origin["A_STOCK_CAL"][origin] = {"source": "A_STOCK_INSTALLED", "params": a_params}
        b_res = ls.walk_forward_b_selection(b_rows, {}, origin_cutoff=origin, alpha=ALPHA_B,
                                            utility_floor=sb.UTILITY_FLOOR_DAILY,
                                            support_floor=sb.MIN_SUPPORT_FOR_ELIGIBLE)
        selections_by_origin["B_FP_PERSISTENCE"][origin] = b_res
        c_res = ls.walk_forward_c_selection(c_rows, origin_cutoff=origin, alpha=ALPHA_C,
                                            utility_floor=sb.UTILITY_FLOOR_DAILY,
                                            support_floor=sb.MIN_SUPPORT_FOR_ELIGIBLE, b_result=b_res)
        selections_by_origin["C_FP_CONTEXT"][origin] = c_res

    admitted = {arm: ls.build_admitted_schedule(selections_by_origin[arm], arm=arm) for arm in ls.ARMS}

    frame, _partitions = load_real_bars(SYMBOL, start=FRAME_START, end=FRAME_END)
    frame = frame[["open", "high", "low", "close", "volume"]].copy()

    # A real, disclosed possibility this study's own orchestration must
    # handle rather than crash on: an arm that NEVER admits anything across
    # all of cell 2's 3 origins has no schedule to deploy at all -- guide
    # 19 item 8's "whole-policy fallback period" taken to its full extent
    # for this small a cell. Recorded as NEVER_ADMITTED, never a crash and
    # never a fabricated account.
    schedules, never_admitted = {}, {}
    for arm in ls.ARMS:
        try:
            schedules[arm] = ls.build_run_deployment_schedule(admitted[arm], frame_index=frame.index)
        except ls.LockedStudyError as exc:
            never_admitted[arm] = str(exc)

    per_arm_seconds, payloads = {}, {}
    for arm in schedules:
        t0 = time.perf_counter()
        payload, event = run_deployment(cache, LAB, ALPHA_ID, frame, schedules[arm],
                                        ready_at=frame.index[0], report_level="score",
                                        economics=economics, producer=f"fp08cell2-{arm}")
        per_arm_seconds[arm] = time.perf_counter() - t0
        payloads[arm] = {"payload": payload, "cache_event": event["status"]}

    peak_rss_mib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    total_wall = time.perf_counter() - t_wall_start

    daily_returns, accounts_by_arm = {}, {}
    for arm in ls.ARMS:
        if arm in never_admitted:
            accounts_by_arm[arm] = {
                "status": "NEVER_ADMITTED", "reason": never_admitted[arm],
                "fill_count": None, "bars": len(frame), "entries": None,
                "engine_fill_count": None, "cache_event": None, "wall_seconds_measured": None,
                "daily_returns_start": None, "daily_returns_end": None, "daily_return_days": None,
                "initial_capital": economics["initial_capital"], "n_activations_requested": 0,
            }
            continue
        payload = payloads[arm]["payload"]
        audit = payload["selected_audit"]
        dr = ls.account_daily_returns(payload, frame, initial_capital=economics["initial_capital"])
        daily_returns[arm] = dr
        accounts_by_arm[arm] = {
            "status": "OK", "fill_count": len(audit["fills"]), "bars": len(frame),
            "entries": payload["trial_scalar"]["entries"],
            "engine_fill_count": audit["engine_fill_count"],
            "cache_event": payloads[arm]["cache_event"],
            "wall_seconds_measured": round(per_arm_seconds[arm], 3),
            "daily_returns_start": dr[0][0] if dr else None,
            "daily_returns_end": dr[-1][0] if dr else None,
            "daily_return_days": len(dr),
            "initial_capital": economics["initial_capital"],
            "n_activations_requested": len(schedules[arm]),
        }
    accounts_doc = {"schema": "regime_lab.fp08_cell2_accounts.v1", "cell": "cell2_replication",
                    "frame_bars": len(frame), "shared_initial_capital": economics["initial_capital"],
                    "by_arm": accounts_by_arm}

    b_rows_by_id = {r["record_id"]: r for r in b_rows}
    c_rows_by_id = {r["record_id"]: r for r in c_rows}
    d1_rows = []
    for origin in origins_sorted:
        for arm, rows_by_id in (("B_FP_PERSISTENCE", b_rows_by_id), ("C_FP_CONTEXT", c_rows_by_id)):
            result = selections_by_origin[arm][origin]
            fallback_result = selections_by_origin["B_FP_PERSISTENCE"][origin] if arm == "C_FP_CONTEXT" else None
            rid, reason = record_id_for_d1(result, fallback_result=fallback_result)
            if rid is None:
                d1_rows.append({"arm": arm, "origin_cutoff": origin, "record_id": None,
                               "is_mean_daily_return": None, "forward_label": None,
                               "D_mean_daily_return": None, "reason": reason})
                continue
            row = rows_by_id[rid]
            is_v, fwd_v = row["is_mean_daily_return"], row["label"]
            if fwd_v is None:
                d1_rows.append({"arm": arm, "origin_cutoff": origin, "record_id": rid,
                               "is_mean_daily_return": is_v, "forward_label": None,
                               "D_mean_daily_return": None,
                               "reason": f"record {rid}'s own forward label is not yet matured"})
                continue
            d = ls.d1_decay(is_v, fwd_v)
            d1_rows.append({"arm": arm, "origin_cutoff": origin, "record_id": rid,
                           "is_mean_daily_return": is_v, "forward_label": fwd_v,
                           "D_mean_daily_return": d["D_mean_daily_return"], "reason": None})
    a_exact_matches = 0
    for origin in origins_sorted:
        a_params = selections_by_origin["A_STOCK_CAL"][origin]["params"]
        match = [r for r in b_rows if r["origin_cutoff"] == origin and r["params"] == a_params]
        if match:
            a_exact_matches += 1
            row = match[0]
            fwd_v = row["label"]
            d_val = ls.d1_decay(row["is_mean_daily_return"], fwd_v)["D_mean_daily_return"] if fwd_v is not None else None
            d1_rows.append({"arm": "A_STOCK_CAL", "origin_cutoff": origin, "record_id": row["record_id"],
                           "is_mean_daily_return": row["is_mean_daily_return"], "forward_label": fwd_v,
                           "D_mean_daily_return": d_val,
                           "reason": None if d_val is not None else "forward label not yet matured"})
        else:
            d1_rows.append({"arm": "A_STOCK_CAL", "origin_cutoff": origin, "record_id": None,
                           "is_mean_daily_return": None, "forward_label": None,
                           "D_mean_daily_return": None,
                           "reason": "Arm A's stock selection does not exactly match a region-archive "
                                     "medoid at this origin"})
    d1_doc = {"schema": "regime_lab.fp08_cell2_d1_table.v1", "cell": "cell2_replication",
             "convention": "D = IS - forward; positive = worse decay (guide 8.5, FP-01 repaired)",
             "arm_a_exact_match_count": a_exact_matches, "arm_a_exact_match_denominator": len(origins_sorted),
             "rows": d1_rows}

    def _contrast_or_not_evaluable(left_arm: str, right_arm: str, *, label: str) -> dict:
        if left_arm in never_admitted or right_arm in never_admitted:
            missing = [a for a in (left_arm, right_arm) if a in never_admitted]
            return {"label": label, "status": "NOT_EVALUABLE",
                   "reason": f"{'/'.join(missing)} never admitted anything in cell 2 -- no "
                            "deployment account exists to pair"}
        return ls.paired_contrast(daily_returns[left_arm], daily_returns[right_arm], label=label,
                                  delta=sb.UTILITY_FLOOR_DAILY)

    primary = _contrast_or_not_evaluable("C_FP_CONTEXT", "B_FP_PERSISTENCE",
                                         label="C_FP_CONTEXT - B_FP_PERSISTENCE (cell2)")
    sec_ba = _contrast_or_not_evaluable("B_FP_PERSISTENCE", "A_STOCK_CAL",
                                        label="B_FP_PERSISTENCE - A_STOCK_CAL (cell2)")
    sec_ca = _contrast_or_not_evaluable("C_FP_CONTEXT", "A_STOCK_CAL",
                                        label="C_FP_CONTEXT - A_STOCK_CAL (cell2)")
    contrasts_doc = {"schema": "regime_lab.fp08_cell2_paired_contrasts.v1", "cell": "cell2_replication",
                    "primary": primary,
                    "secondary": {"B_FP_PERSISTENCE - A_STOCK_CAL": sec_ba,
                                 "C_FP_CONTEXT - A_STOCK_CAL": sec_ca}}

    selections_doc = {"schema": "regime_lab.fp08_cell2_selections.v1", "cell": "cell2_replication",
                     "by_origin": {origin: {arm: selections_by_origin[arm][origin] for arm in ls.ARMS}
                                  for origin in origins_sorted}}
    resource_budget_doc = {
        "schema": "regime_lab.fp08_cell2_resource_budget.v1",
        "started_at_utc": started,
        "resource_limits_applied": limits,
        "measured": {"peak_rss_mib": round(peak_rss_mib, 1), "total_wall_seconds": round(total_wall, 2),
                    "per_arm_wall_seconds": {a: round(s, 2) for a, s in per_arm_seconds.items()},
                    "frame_bars": len(frame)},
        "feature_rows_reused_from_cache": reused_features,
        "alpha_b": ALPHA_B, "alpha_b_source": ALPHA_B_SOURCE,
        "alpha_c": ALPHA_C, "alpha_c_source": ALPHA_C_SOURCE,
    }

    out_dir = LAB / ".cache" / "fp08_cell2_study"
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, doc in (("selections.json", selections_doc), ("accounts.json", accounts_doc),
                     ("d1_table.json", d1_doc), ("paired_contrasts.json", contrasts_doc),
                     ("resource_budget.json", resource_budget_doc)):
        (out_dir / name).write_text(json.dumps(doc, indent=2))

    print(json.dumps({
        "origins": origins_sorted,
        "selections_summary": {arm: {o: selections_by_origin[arm][o]["source"] for o in origins_sorted}
                               for arm in ls.ARMS},
        "accounts_summary": {arm: {"fills": accounts_by_arm[arm]["fill_count"]} for arm in ls.ARMS},
        "primary_contrast": {"status": primary.get("status"), "estimate": primary.get("estimate")},
        "measured": resource_budget_doc["measured"],
        "out_dir": str(out_dir),
    }, indent=2))
    return 0, {"out_dir": str(out_dir)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-run-dir", required=True)
    parser.add_argument("--pytest-xml", default=None)
    args = parser.parse_args()
    code, _info = run_cell2_study(args.archive_run_dir, args.pytest_xml)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
