#!/usr/bin/env python3
"""SD03.2-3.4: the real FINAL archive -- A/B/C on the 12 real FINAL origins
(guide section 10). Only 3 arms this time (A_M4, B_SD_GLOBAL, C_SD_JM) --
SD-02 already froze the JM recipe (c=2.0); FINAL never re-selects it (guide
10.1: 'khong chon lai hyperparameters').

Reuses scripts/run_sd02_validation.py's own build_panel/candidate_id/
panel_scoring_rows verbatim (the identical real search+panel+IS/FWD Sharpe
machinery) and jm_vintage/model_bc/training_rows/fold_scoring exactly as
SD-02 did. The training pool for B/C now spans INIT (12, committed) +
VALIDATION (12, committed) + FINAL-so-far (growing) -- guide SD03.3: "B/C
fit weights tu matured archive".

Checkpointed per origin, same discipline as SD-01/02.

Usage:
  lab_venv/bin/python scripts/run_sd03_final_archive.py
"""
from __future__ import annotations

import json
import resource
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "src"))
sys.path.insert(0, str(LAB / "scripts"))

import run_sd02_validation as sd02  # noqa: E402
from crypto_regime_lab.fp.evaluator import default_economics  # noqa: E402
from crypto_regime_lab.fp.forward_ledger import training_view  # noqa: E402
from crypto_regime_lab.ra.ra05_market import load_real_bars  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy, sha256_file  # noqa: E402
from crypto_regime_lab.selector.alpha_schemas import A_SC  # noqa: E402
from crypto_regime_lab.sd import fold_scoring as fsc  # noqa: E402
from crypto_regime_lab.sd import jm_vintage as jv  # noqa: E402
from crypto_regime_lab.sd import model_bc as mbc  # noqa: E402
from crypto_regime_lab.sd import training_rows as tr  # noqa: E402
from crypto_regime_lab.sd.verifier_sd01 import INIT_ORIGINS  # noqa: E402
from crypto_regime_lab.time_edge.compute_cache import ComputeCache  # noqa: E402

STUDY_ID = "sharpe_decay_sd_v1"
PHASE_ID = "SD-03"
SYMBOL = "BTCUSDT"
FROZEN_C = 2.0
INIT_LEDGER_DIR = LAB / "evidence" / "sharpe_decay_sd_v1" / "init_archive"
VAL_LEDGER_DIR = LAB / "evidence" / "sharpe_decay_sd_v1" / "validation_folds"
MODEL_DIR = LAB / "evidence" / "sharpe_decay_sd_v1" / "sd02_model"
FINAL_LEDGER_DIR = LAB / "evidence" / "sharpe_decay_sd_v1" / "final_folds"
TIMELINE_PATH = LAB / "configs" / "sharpe_decay_sd_v1" / "timeline.json"
PROGRESS_LOG = FINAL_LEDGER_DIR / "progress.jsonl"

ARM_NAMES = (fsc.ARM_A, fsc.ARM_B, fsc.jm_arm_name(FROZEN_C))


def utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="microseconds")


def log_progress(event: str, **fields) -> None:
    PROGRESS_LOG.parent.mkdir(parents=True, exist_ok=True)
    row = {"utc": utcnow(), "event": event, **fields}
    with open(PROGRESS_LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")
    print(json.dumps(row, default=str), flush=True)


def fold_record_path(origin_cutoff: str) -> Path:
    return FINAL_LEDGER_DIR / f"fold_{origin_cutoff}.json"


def load_init_and_validation_state():
    """INIT (SD-01's committed archive + SD02's descriptor backfill) +
    VALIDATION (SD-02's own committed fold records, entries already inline
    since archive.py's SD02.1 patch) -- 24 origins total, real, committed."""
    archive_by_origin, descriptors_by_origin, jm_tape, ratio_by_origin = {}, {}, {}, {}

    desc_payload = json.loads((MODEL_DIR / "init_descriptors.json").read_text(encoding="utf-8"))
    tapes_payload = json.loads((MODEL_DIR / "init_jm_tapes.json").read_text(encoding="utf-8"))
    tape_rows_by_origin = {r["origin_cutoff"]: r for r in tapes_payload["tapes"][str(FROZEN_C)]}
    for origin in INIT_ORIGINS:
        archive_by_origin[origin] = json.loads((INIT_LEDGER_DIR / f"origin_{origin}.json")
                                               .read_text(encoding="utf-8"))
        descriptors_by_origin[origin] = desc_payload["origins"][origin]
        rec = jv.VintageOriginRecord(**tape_rows_by_origin[origin])
        jm_tape[origin] = rec
        ratio_by_origin[origin] = rec.origin_log_rv_ratio

    val_origins = json.loads(TIMELINE_PATH.read_text())["roles"]["VALIDATION"]["origins"]
    for origin in val_origins:
        fold = json.loads((VAL_LEDGER_DIR / f"fold_{origin}.json").read_text(encoding="utf-8"))
        archive_by_origin[origin] = fold["panel"]
        descriptors_by_origin[origin] = [
            {"candidate_id": r["candidate_id"], "activity_entries": r["is_window"]["entries"]}
            for r in fold["panel"]["label_rows"]]
        rec = jv.VintageOriginRecord(**fold["jm_this_origin"][str(FROZEN_C)])
        jm_tape[origin] = rec
        ratio_by_origin[origin] = rec.origin_log_rv_ratio

    return archive_by_origin, descriptors_by_origin, jm_tape, ratio_by_origin


def run() -> int:
    policy = SandboxPolicy.discover(LAB)
    policy.assert_lab_root_ok()
    limits = sd02.apply_resource_limits(policy)
    log_progress("run_start", limits=limits, frozen_recipe_c=FROZEN_C)

    final_origins = json.loads(TIMELINE_PATH.read_text())["roles"]["FINAL"]["origins"]
    cache = ComputeCache(LAB, "sd01archive", cache_root=sd02.CACHE_ROOT)
    economics = default_economics()
    FINAL_LEDGER_DIR.mkdir(parents=True, exist_ok=True)

    archive_by_origin, descriptors_by_origin, jm_tape, ratio_by_origin = load_init_and_validation_state()
    all_records = tr.chronology_records(archive_by_origin, descriptors_by_origin, A_SC)
    log_progress("training_pool_loaded", n_origins=len(archive_by_origin), n_records=len(all_records))

    peak_rss_overall = 0.0
    t_run_start = time.perf_counter()
    for origin_cutoff in final_origins:
        path = fold_record_path(origin_cutoff)
        if path.is_file():
            log_progress("fold_already_built_skipping", origin=origin_cutoff)
            fold_record = json.loads(path.read_text(encoding="utf-8"))
            panel_record = fold_record["panel"]
            archive_by_origin[origin_cutoff] = panel_record
            descriptors_by_origin[origin_cutoff] = [
                {"candidate_id": r["candidate_id"], "activity_entries": r["is_window"]["entries"]}
                for r in panel_record["label_rows"]]
            jm_tape[origin_cutoff] = jv.VintageOriginRecord(**fold_record["jm_this_origin"])
            ratio_by_origin[origin_cutoff] = fold_record["jm_this_origin"]["origin_log_rv_ratio"]
            all_records = tr.chronology_records(archive_by_origin, descriptors_by_origin, A_SC)
            continue

        t_fold_start = time.perf_counter()
        log_progress("fold_start", origin=origin_cutoff)

        panel_record = sd02.build_panel(cache, origin_cutoff=origin_cutoff, economics=economics)
        archive_by_origin[origin_cutoff] = panel_record
        descriptors_by_origin[origin_cutoff] = [
            {"candidate_id": r["candidate_id"], "activity_entries": r["is_window"]["entries"]}
            for r in panel_record["label_rows"]]

        jm_rec = jv.fit_origin_vintage(load_real_bars, SYMBOL, origin_cutoff=origin_cutoff, c=FROZEN_C)
        jm_tape[origin_cutoff] = jm_rec
        ratio_by_origin[origin_cutoff] = jm_rec.origin_log_rv_ratio
        log_progress("jm_fit_done", origin=origin_cutoff, status=jm_rec.status, state=jm_rec.state)

        all_records = tr.chronology_records(archive_by_origin, descriptors_by_origin, A_SC)
        decision_time = f"{origin_cutoff}T00:00:00+00:00"

        b_view = training_view(all_records, decision_time=decision_time)
        b_rows = tr.model_b_rows(b_view["usable"])
        model_b_fit = mbc.fit_model_b(b_rows)

        state_by_origin = {o: (rec.state if rec.status == jv.STATUS_OK else None)
                           for o, rec in jm_tape.items()}
        tagged = tr.retag_states(all_records, state_by_origin)
        c_view = training_view(tagged, decision_time=decision_time)
        c_rows = tr.model_c_rows(c_view["usable"])
        fit_c = mbc.fit_model_c(model_b_fit, c_rows)
        this_state = state_by_origin.get(origin_cutoff)

        panel_rows = sd02.panel_scoring_rows(panel_record)
        anchor_id = panel_record["anchor_id"]
        arms_out = {}
        arms_out[fsc.ARM_A] = fsc.score_pool_arm_a(panel_rows, anchor_id=anchor_id)
        arms_out[fsc.ARM_B] = fsc.score_pool(
            lambda row, anchor: mbc.predict_b(model_b_fit, row["features"], anchor["features"]),
            panel_rows, anchor_id=anchor_id, schema=A_SC)

        def predict_fn(row, anchor, _fit_c=fit_c, _state=this_state):
            return mbc.predict_c(_fit_c, row["features"], anchor["features"], state=_state)["y_hat"]

        c_arm_name = fsc.jm_arm_name(FROZEN_C)
        arms_out[c_arm_name] = fsc.score_pool(predict_fn, panel_rows, anchor_id=anchor_id, schema=A_SC)
        arms_out[c_arm_name]["train_mature_origin_count"] = len({r["origin_id"] for r in c_rows})
        scoring_c = mbc.predict_c(fit_c, panel_rows[0]["features"],
                                  next(r for r in panel_rows if r["is_anchor"])["features"],
                                  state=this_state)
        arms_out[c_arm_name]["fallback_reason"] = scoring_c["reason"]
        arms_out[c_arm_name]["context_prediction_called"] = True

        label_by_id = {r["candidate_id"]: r for r in panel_record["label_rows"]}
        for arm_name, out in arms_out.items():
            winner_id = out["selection"]["winner_id"]
            winner_label = label_by_id.get(winner_id)
            out["SR_IS_selected"] = winner_label["is_window"]["sharpe"] if winner_label else None
            out["SR_FWD_selected"] = winner_label["fwd_window"]["sharpe"] if winner_label else None
            out["D_selected"] = winner_label["decay"].get("value") if winner_label else None

        fold_wall = time.perf_counter() - t_fold_start
        fold_record = {
            "schema": "regime_lab.sd03_final_fold.v1", "study_id": STUDY_ID, "phase_id": PHASE_ID,
            "origin_cutoff": origin_cutoff, "decision_cutoff": decision_time,
            "frozen_recipe_c": FROZEN_C, "panel": panel_record,
            "jm_this_origin": jm_rec.__dict__,
            "b_train_mature_origin_count": model_b_fit.n_train_origins,
            "c_train_mature_origin_count": len({r["origin_id"] for r in c_rows}),
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
                n_folds_built=sum(1 for o in final_origins if fold_record_path(o).is_file()))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
