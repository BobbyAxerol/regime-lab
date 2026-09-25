#!/usr/bin/env python3
"""SD02.4: run the 12 real VALIDATION folds (guide SS9.2 SD02.4).

At each of the 12 VALIDATION origins (chronological), in order:

  1. A real 128-trial search + representative panel + real IS/FWD canonical
     Sharpe for the panel (IDENTICAL machinery to SD-01's own INIT archive
     build, ``fp.checkpoint_search.run_origin_search`` +
     ``sd.archive.candidate_window_sharpe`` -- never a second, different
     search or evaluation path).
  2. A real causal JM fit for this origin, all 3 penalty recipes
     (``sd.jm_vintage.fit_all_recipes_at_origin``).
  3. B's global model, and one C-family model per conditional arm
     (R_RULE, JM_C0.5, JM_C1.0, JM_C2.0), fit ONLY from chronologically
     matured training rows (INIT's 12 + any earlier VALIDATION folds that
     have matured by this origin's own decision time -- the REAL,
     verbatim-reused ``fp.chronology``/``fp.forward_ledger`` guard).
  4. All 6 arms (A_M4, B_SD_GLOBAL, R_RULE, JM_C0.5, JM_C1.0, JM_C2.0)
     scored on the SAME panel pool (guide SD02.1 panel-only scope
     revision, owner dec-c94ea602aeac0f1a) and put through the minY
     selection rule.

Checkpointed per origin, same discipline as run_sd01_archive.py: a fold
whose own record already exists on disk is skipped, so a restart resumes
cleanly (the underlying ComputeCache also makes every individual
search/evaluate_candidate call independently resumable).

Usage:
  lab_venv/bin/python scripts/run_sd02_validation.py
"""
from __future__ import annotations

import json
import os
import resource
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "src"))

from crypto_regime_lab.fp.checkpoint_search import run_origin_search, _trial_records  # noqa: E402
from crypto_regime_lab.fp.evaluator import default_economics  # noqa: E402
from crypto_regime_lab.fp.forward_ledger import training_view  # noqa: E402
from crypto_regime_lab.ra.ra05_market import load_real_bars  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy, sha256_file  # noqa: E402
from crypto_regime_lab.safety.process import lab_worker_env  # noqa: E402
from crypto_regime_lab.selector.alpha_schemas import A_SC  # noqa: E402
from crypto_regime_lab.sd import archive as ar  # noqa: E402
from crypto_regime_lab.sd import fold_scoring as fsc  # noqa: E402
from crypto_regime_lab.sd import jm_vintage as jv  # noqa: E402
from crypto_regime_lab.sd import metrics as m  # noqa: E402
from crypto_regime_lab.sd import model_bc as mbc  # noqa: E402
from crypto_regime_lab.sd import r_rule as rr  # noqa: E402
from crypto_regime_lab.sd import training_rows as tr  # noqa: E402
from crypto_regime_lab.sd.candidate_descriptors import build_descriptor_row  # noqa: E402
from crypto_regime_lab.sd.verifier_sd01 import INIT_ORIGINS  # noqa: E402
from crypto_regime_lab.time_edge.compute_cache import ComputeCache  # noqa: E402

STUDY_ID = "sharpe_decay_sd_v1"
PHASE_ID = "SD-02"
ALPHA_ID = "A-SC"
SYMBOL = "BTCUSDT"
SEARCH_SEED = 20260925
SEARCH_TRIALS = 128
RECIPES = (0.5, 1.0, 2.0)
CACHE_ROOT = "evidence/sharpe_decay_sd_v1/compute-cache"
INIT_LEDGER_DIR = LAB / "evidence" / "sharpe_decay_sd_v1" / "init_archive"
MODEL_DIR = LAB / "evidence" / "sharpe_decay_sd_v1" / "sd02_model"
VAL_LEDGER_DIR = LAB / "evidence" / "sharpe_decay_sd_v1" / "validation_folds"
TIMELINE_PATH = LAB / "configs" / "sharpe_decay_sd_v1" / "timeline.json"
PROGRESS_LOG = VAL_LEDGER_DIR / "progress.jsonl"

CONDITIONAL_ARMS = (fsc.ARM_R_RULE,) + tuple(fsc.jm_arm_name(c) for c in RECIPES)
ALL_ARMS = (fsc.ARM_A, fsc.ARM_B) + CONDITIONAL_ARMS


def utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="microseconds")


def log_progress(event: str, **fields) -> None:
    PROGRESS_LOG.parent.mkdir(parents=True, exist_ok=True)
    row = {"utc": utcnow(), "event": event, **fields}
    with open(PROGRESS_LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")
    print(json.dumps(row, default=str), flush=True)


def apply_resource_limits(policy) -> dict:
    env = lab_worker_env(policy)
    for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
               "NUMEXPR_NUM_THREADS", "NUMBA_NUM_THREADS"):
        os.environ[key] = env[key]
    budget = policy.raw["resource_budget"]
    cap_bytes = int(budget["working_memory_gib"] * (1 << 30))
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    resource.setrlimit(resource.RLIMIT_AS, (cap_bytes, hard))
    return {"rlimit_as_gib": budget["working_memory_gib"], "cpu_limit": env["OMP_NUM_THREADS"]}


def candidate_id(params: dict) -> str:
    return "|".join(f"{k}={v}" for k, v in sorted(params.items()))


def fold_record_path(origin_cutoff: str) -> Path:
    return VAL_LEDGER_DIR / f"fold_{origin_cutoff}.json"


# ---------------------------------------------------------------------------
# Step 1: real search + panel + IS/FWD Sharpe (identical to SD-01's own build)
# ---------------------------------------------------------------------------

def build_panel(cache, *, origin_cutoff: str, economics: dict) -> dict:
    search = run_origin_search(origin_cutoff=origin_cutoff, trials=SEARCH_TRIALS, seed=SEARCH_SEED,
                               train_memory_days=180, forward_days=56, symbol=SYMBOL, alpha_id=ALPHA_ID)
    if not search["wf_result"].get("ok"):
        raise SystemExit(f"origin {origin_cutoff}: real search did not return ok=True")
    records = _trial_records(search["wf_result"])
    candidates = ar.unique_candidates(records)
    anchor_params = search["wf_result"]["selected_params"]
    panel = ar.representative_panel(candidates, anchor_params=anchor_params)
    anchor_id = candidate_id(anchor_params)
    log_progress("search_done", origin=origin_cutoff, n_trials=len(records),
                n_unique_candidates=len(candidates), panel_size=len(panel),
                wall_seconds=round(search["wall_seconds_measured"], 2))

    label_rows = []
    for i, row in enumerate(panel):
        params = row["params"]
        cid = candidate_id(params)
        is_result = ar.candidate_window_sharpe(cache, LAB, ALPHA_ID, load_real_bars, params,
                                               origin_cutoff=origin_cutoff, kind="IS", symbol=SYMBOL,
                                               economics=economics,
                                               producer=f"sd02validation-{origin_cutoff}")
        fwd_result = ar.candidate_window_sharpe(cache, LAB, ALPHA_ID, load_real_bars, params,
                                                origin_cutoff=origin_cutoff, kind="FWD", symbol=SYMBOL,
                                                economics=economics,
                                                producer=f"sd02validation-{origin_cutoff}")
        decay = m.signed_decay(
            {"sharpe": is_result["sharpe"], "sharpe_status": is_result["sharpe_status"]},
            {"sharpe": fwd_result["sharpe"], "sharpe_status": fwd_result["sharpe_status"]})
        label_rows.append({"candidate_id": cid, "params": params, "is_anchor": cid == anchor_id,
                          "trial_id": row["trial_id"], "mean_is_sharpe_search_proxy": row["mean_is_sharpe"],
                          "is_window": is_result, "fwd_window": fwd_result, "decay": decay})
        log_progress("candidate_done", origin=origin_cutoff, candidate_index=i, total=len(panel),
                    candidate_id=cid, is_status=is_result["sharpe_status"],
                    fwd_status=fwd_result["sharpe_status"], entries=is_result.get("entries"))

    anchor_rows = [r for r in label_rows if r["is_anchor"]]
    if not anchor_rows:
        raise SystemExit(f"origin {origin_cutoff}: anchor not present in label_rows")
    anchor_decay = anchor_rows[0]["decay"]
    for r in label_rows:
        r["relative_decay_Y"] = m.relative_decay(r["decay"], anchor_decay)

    return {"origin_cutoff": origin_cutoff, "alpha_id": ALPHA_ID, "symbol": SYMBOL,
           "search": {"trials_requested": SEARCH_TRIALS, "seed": SEARCH_SEED,
                     "wall_seconds_measured": search["wall_seconds_measured"],
                     "n_trial_records": len(records), "n_unique_candidates": len(candidates)},
           "anchor_params": anchor_params, "anchor_id": anchor_id, "panel_size": len(panel),
           "label_rows": label_rows}


# ---------------------------------------------------------------------------
# Step 2-4: JM tapes, chronology pool, model fits, per-fold scoring
# ---------------------------------------------------------------------------

def load_init_state():
    """SD-01's committed archive + SD02.1/2.3's own descriptor backfill and
    JM tapes -- all already-committed artifacts, read once."""
    archive_by_origin, descriptors_by_origin = {}, {}
    desc_payload = json.loads((MODEL_DIR / "init_descriptors.json").read_text(encoding="utf-8"))
    for origin in INIT_ORIGINS:
        archive_by_origin[origin] = json.loads((INIT_LEDGER_DIR / f"origin_{origin}.json")
                                               .read_text(encoding="utf-8"))
        descriptors_by_origin[origin] = desc_payload["origins"][origin]
    tapes_payload = json.loads((MODEL_DIR / "init_jm_tapes.json").read_text(encoding="utf-8"))
    jm_tapes = {}   # {c: {origin: VintageOriginRecord}}
    ratio_by_origin = {}   # every origin present, None when the tape has no ratio (never dropped)
    for c_str, rows in tapes_payload["tapes"].items():
        c = float(c_str)
        jm_tapes[c] = {}
        for row in rows:
            rec = jv.VintageOriginRecord(**row)
            jm_tapes[c][rec.origin_cutoff] = rec
            ratio_by_origin[rec.origin_cutoff] = rec.origin_log_rv_ratio
    return archive_by_origin, descriptors_by_origin, jm_tapes, ratio_by_origin


def panel_scoring_rows(panel_record: dict) -> list:
    """Build fold_scoring-ready rows for this origin's own panel, using its
    already-computed real descriptor (is_window.sharpe + entries, both
    real -- panel-only scope, guide SD02.1). A non-anchor candidate whose
    IS window failed (sharpe_status != OK) is EXCLUDED from scoring here --
    a real search already ran for this origin, so a defect in one
    candidate's own descriptor must not waste that compute by crashing the
    whole fold; the anchor itself failing is a genuine emergency and is
    NOT silently dropped."""
    out = []
    for row in panel_record["label_rows"]:
        if row["is_window"]["sharpe_status"] != "OK":
            if row["is_anchor"]:
                raise SystemExit(f"{panel_record['origin_cutoff']}: anchor's own IS window failed "
                                 f"({row['is_window']['sharpe_status']}) -- cannot score this fold")
            continue
        features = build_descriptor_row(A_SC, row, activity_entries=row["is_window"]["entries"])
        out.append({"candidate_id": row["candidate_id"], "params": row["params"],
                   "features": features, "sr_is": row["is_window"]["sharpe"],
                   "is_anchor": row["is_anchor"]})
    return out


def run() -> int:
    policy = SandboxPolicy.discover(LAB)
    policy.assert_lab_root_ok()
    limits = apply_resource_limits(policy)
    log_progress("run_start", limits=limits)

    timeline = json.loads(TIMELINE_PATH.read_text())
    val_origins = timeline["roles"]["VALIDATION"]["origins"]

    cache = ComputeCache(LAB, "sd01archive", cache_root=CACHE_ROOT)
    economics = default_economics()
    VAL_LEDGER_DIR.mkdir(parents=True, exist_ok=True)

    archive_by_origin, descriptors_by_origin, jm_tapes, ratio_by_origin = load_init_state()
    # running pool of ALL chronology records seen so far (INIT, then each
    # completed VALIDATION fold appended in order)
    all_records = tr.chronology_records(archive_by_origin, descriptors_by_origin, A_SC)

    peak_rss_overall = 0.0
    t_run_start = time.perf_counter()
    for origin_cutoff in val_origins:
        path = fold_record_path(origin_cutoff)
        if path.is_file():
            log_progress("fold_already_built_skipping", origin=origin_cutoff)
            fold_record = json.loads(path.read_text(encoding="utf-8"))
            panel_record = fold_record["panel"]
            archive_by_origin[origin_cutoff] = panel_record
            descriptors_by_origin[origin_cutoff] = [
                {"candidate_id": r["candidate_id"], "activity_entries": r["is_window"]["entries"]}
                for r in panel_record["label_rows"]]
            for c in RECIPES:
                jm_tapes[c][origin_cutoff] = jv.VintageOriginRecord(**fold_record["jm_this_origin"][str(c)])
            ratio_by_origin[origin_cutoff] = fold_record["jm_this_origin"][str(RECIPES[0])]["origin_log_rv_ratio"]
            all_records = tr.chronology_records(archive_by_origin, descriptors_by_origin, A_SC)
            continue

        t_fold_start = time.perf_counter()
        log_progress("fold_start", origin=origin_cutoff)

        panel_record = build_panel(cache, origin_cutoff=origin_cutoff, economics=economics)
        archive_by_origin[origin_cutoff] = panel_record
        descriptors_by_origin[origin_cutoff] = [
            {"candidate_id": r["candidate_id"], "activity_entries": r["is_window"]["entries"]}
            for r in panel_record["label_rows"]]

        jm_this_origin = jv.fit_all_recipes_at_origin(load_real_bars, SYMBOL, origin_cutoff=origin_cutoff,
                                                       recipes=RECIPES)
        for c in RECIPES:
            jm_tapes[c][origin_cutoff] = jm_this_origin[c]
        ratio_by_origin[origin_cutoff] = jm_this_origin[RECIPES[0]].origin_log_rv_ratio
        log_progress("jm_fit_done", origin=origin_cutoff,
                    statuses={str(c): jm_this_origin[c].status for c in RECIPES})

        all_records = tr.chronology_records(archive_by_origin, descriptors_by_origin, A_SC)
        decision_time = f"{origin_cutoff}T00:00:00+00:00"

        # B: state-independent, one fit shared by every conditional arm
        b_view = training_view(all_records, decision_time=decision_time)
        b_rows = tr.model_b_rows(b_view["usable"])
        model_b_fit = mbc.fit_model_b(b_rows)

        panel_rows = panel_scoring_rows(panel_record)
        anchor_id = panel_record["anchor_id"]
        arms_out = {}
        arms_out[fsc.ARM_A] = fsc.score_pool_arm_a(panel_rows, anchor_id=anchor_id)
        arms_out[fsc.ARM_B] = fsc.score_pool(
            lambda row, anchor: mbc.predict_b(model_b_fit, row["features"], anchor["features"]),
            panel_rows, anchor_id=anchor_id, schema=A_SC)

        # conditional arms: R_RULE (dynamic per-fold threshold) + 3 JM recipes
        r_rule_train_origins = sorted({r["origin_cutoff"] for r in b_view["usable"]})
        r_rule_threshold = rr.fit_threshold([ratio_by_origin[o] for o in r_rule_train_origins
                                            if ratio_by_origin.get(o) is not None])
        r_rule_state_map = rr.state_by_origin(ratio_by_origin, threshold=r_rule_threshold)

        conditional_state_maps = {fsc.ARM_R_RULE: r_rule_state_map}
        for c in RECIPES:
            conditional_state_maps[fsc.jm_arm_name(c)] = {
                o: (rec.state if rec.status == jv.STATUS_OK else None)
                for o, rec in jm_tapes[c].items()}

        for arm_name, state_map in conditional_state_maps.items():
            tagged = tr.retag_states(all_records, state_map)
            c_view = training_view(tagged, decision_time=decision_time)
            c_rows = tr.model_c_rows(c_view["usable"])
            # this_state may legitimately be None (JM fit failed / R_RULE
            # ratio unavailable at THIS origin) -- passed straight into
            # predict_c, which already handles an unrecognised state key via
            # its own typed GLOBAL_FALLBACK/UNKNOWN_STATE path (guide SS5.6);
            # never special-cased here, so C's own fallback logic is what
            # actually runs, not a manufactured substitute.
            this_state = state_map.get(origin_cutoff)
            fit_c = mbc.fit_model_c(model_b_fit, c_rows)

            def predict_fn(row, anchor, _fit_c=fit_c, _state=this_state):
                return mbc.predict_c(_fit_c, row["features"], anchor["features"], state=_state)["y_hat"]

            arms_out[arm_name] = fsc.score_pool(predict_fn, panel_rows, anchor_id=anchor_id, schema=A_SC)
            arms_out[arm_name]["train_mature_origin_count"] = len({r["origin_id"] for r in c_rows})
            scoring_c = mbc.predict_c(fit_c, panel_rows[0]["features"],
                                      next(r for r in panel_rows if r["is_anchor"])["features"],
                                      state=this_state)
            arms_out[arm_name]["fallback_reason"] = scoring_c["reason"]
            arms_out[arm_name]["context_prediction_called"] = True

        label_by_id = {r["candidate_id"]: r for r in panel_record["label_rows"]}
        for arm_name, out in arms_out.items():
            winner_id = out["selection"]["winner_id"]
            winner_label = label_by_id.get(winner_id)
            out["SR_IS_selected"] = winner_label["is_window"]["sharpe"] if winner_label else None
            out["SR_FWD_selected"] = winner_label["fwd_window"]["sharpe"] if winner_label else None
            out["D_selected"] = winner_label["decay"].get("value") if winner_label else None

        fold_wall = time.perf_counter() - t_fold_start
        fold_record = {
            "schema": "regime_lab.sd02_validation_fold.v1", "study_id": STUDY_ID, "phase_id": PHASE_ID,
            "origin_cutoff": origin_cutoff, "decision_cutoff": decision_time,
            "panel": panel_record,
            "jm_this_origin": {str(c): jm_this_origin[c].__dict__ for c in RECIPES},
            "r_rule_threshold": r_rule_threshold, "r_rule_train_origin_count": len(r_rule_train_origins),
            "b_train_mature_origin_count": model_b_fit.n_train_origins,
            "arms": arms_out,
            "fold_wall_seconds_measured": round(fold_wall, 2), "written_at_utc": utcnow(),
        }
        path.write_text(json.dumps(fold_record, indent=2, default=str) + "\n", encoding="utf-8")
        peak_rss_overall = max(peak_rss_overall, resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0)
        log_progress("fold_complete", origin=origin_cutoff, fold_wall_seconds=round(fold_wall, 2),
                    peak_rss_mib_so_far=round(peak_rss_overall, 1),
                    winners={a: r["selection"]["winner_id"] for a, r in arms_out.items()},
                    sha256=sha256_file(path))

    total_wall = time.perf_counter() - t_run_start
    log_progress("run_complete", total_wall_seconds=round(total_wall, 2),
                peak_rss_mib=round(peak_rss_overall, 1),
                n_folds_built=sum(1 for o in val_origins if fold_record_path(o).is_file()))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
