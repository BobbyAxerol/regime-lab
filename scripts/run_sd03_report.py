#!/usr/bin/env python3
"""SD03.7-3.8: analysis (no engine calls), decision, freeze, report.

Reads ONLY already-committed real artifacts: the FINAL archive's fold_*.json
(required), D2 continuations and continuous-account deployment (both
optional -- reported as NOT_YET_RUN if missing, never silently skipped from
the headline). Guide SS10.2 SD03.7: "Kiem du 12 paired folds truoc
scientific verdict."

Usage:
  lab_venv/bin/python scripts/run_sd03_report.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "src"))

from crypto_regime_lab.sd import inference_sd03 as inf  # noqa: E402
from crypto_regime_lab.sd import preflight_sd03 as pf  # noqa: E402
from crypto_regime_lab.sd import verifier_sd03 as v3  # noqa: E402

CFG = LAB / "configs" / "sharpe_decay_sd_v1"
FINAL_DIR = LAB / "evidence" / "sharpe_decay_sd_v1" / "final_folds"
D2_DIR = LAB / "evidence" / "sharpe_decay_sd_v1" / "d2_continuations"
DEPLOY_DIR = LAB / "evidence" / "sharpe_decay_sd_v1" / "continuous_accounts"
REPORT_PATH = FINAL_DIR / "report.md"
FREEZE_PATH = CFG / "sd03_freeze.json"
ARMS = ("A_M4", "B_SD_GLOBAL", "JM_C2.0")
INFERENCE_SEED = 20260926   # frozen here, before any real FINAL result is read


def utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="microseconds")


def load_final_folds() -> dict:
    final_origins = json.loads((CFG / "timeline.json").read_text())["roles"]["FINAL"]["origins"]
    out = {}
    for origin in final_origins:
        path = FINAL_DIR / f"fold_{origin}.json"
        if path.is_file():
            out[origin] = json.loads(path.read_text(encoding="utf-8"))
    return out


def load_d2(origins: list) -> dict:
    out = {}
    for origin in origins:
        for arm in ARMS:
            path = D2_DIR / f"d2_{origin}_{arm}.json"
            if path.is_file():
                out[(origin, arm)] = json.loads(path.read_text(encoding="utf-8"))
    return out


def load_deployment() -> dict:
    out = {}
    for arm in ARMS:
        path = DEPLOY_DIR / f"account_{arm}.json"
        if path.is_file():
            out[arm] = json.loads(path.read_text(encoding="utf-8"))
    return out


def d1_table_rows(fold_records: dict) -> list:
    rows = []
    for origin, fold in sorted(fold_records.items()):
        row = {"origin": origin}
        for arm in ARMS:
            out = fold["arms"][arm]
            row[f"{arm}_winner"] = out["selection"]["winner_id"]
            row[f"{arm}_is_anchor"] = out["selection"]["is_anchor"]
            row[f"{arm}_SR_IS"] = out.get("SR_IS_selected")
            row[f"{arm}_SR_FWD"] = out.get("SR_FWD_selected")
            row[f"{arm}_D"] = out.get("D_selected")
        d_b, d_c = row["B_SD_GLOBAL_D"], row["JM_C2.0_D"]
        row["R_B_minus_C"] = (d_b - d_c) if d_b is not None and d_c is not None else None
        rows.append(row)
    return rows


def render_report(*, registration, fold_records, d1_rows, d2_records, deployment, decision,
                  preflight_result) -> str:
    n_paired = sum(1 for r in d1_rows if r["R_B_minus_C"] is not None)
    lines = ["# SD-03 — Final A/B/C run: D1/D2/continuous-account Sharpe, inference, conclusion",
            "", f"- study_id: {registration['study_id']}, guide_version: SD-GUIDE-1.0",
            f"- generated_at_utc: {utcnow()}",
            f"- real FINAL folds found: {len(fold_records)}/12",
            f"- preflight: {preflight_result['overall']}",
            "", "## Scope (guide SS10)",
            "SD-03 is the one final A/B/C run on >=12 paired OOS folds. Technical PASS does NOT "
            "require Sharpe improvement (guide SS10.5). This is the FIRST and ONLY final run -- "
            "no re-selection of hyperparameters after seeing results, no SD-04.",
            "", "## Registered primary hypothesis",
            f"- id: {registration['primary_hypothesis']['id']}",
            f"- contrast: {registration['primary_hypothesis']['contrast']}",
            f"- estimand: {registration['primary_hypothesis']['estimand']}",
            f"- safeguard: {registration['primary_hypothesis']['safeguard']}",
            "", "## D1 table (guide SS10.3) — REAL, MEASURED, every fold shown", "",
            "| origin | A winner | B winner | C winner | D_B | D_C | R=D_B-D_C |",
            "|---|---|---|---|---:|---:|---:|"]
    for row in d1_rows:
        lines.append(f"| {row['origin']} | "
                     f"{'ANCHOR' if row['A_M4_is_anchor'] else 'other'} | "
                     f"{'ANCHOR' if row['B_SD_GLOBAL_is_anchor'] else 'other'} | "
                     f"{'ANCHOR' if row['JM_C2.0_is_anchor'] else 'other'} | "
                     f"{row['B_SD_GLOBAL_D']} | {row['JM_C2.0_D']} | {row['R_B_minus_C']} |")
    n_zero_by_construction = sum(1 for row in d1_rows if row["B_SD_GLOBAL_winner"] == row["JM_C2.0_winner"])
    lines += ["", f"- n paired-valid D1 folds: **{n_paired}/{len(d1_rows)}**"]
    if n_zero_by_construction > 0:
        lines += ["",
                 f"**HONEST FINDING, DISCLOSED**: {n_zero_by_construction}/{len(d1_rows)} of these paired "
                 "folds have R = 0 EXACTLY, by construction, because B_SD_GLOBAL and JM_C2.0 selected "
                 "the IDENTICAL candidate at those origins (checked directly against each arm's own "
                 "winner_id) -- not a measured absence of effect at those folds, a structural non-event. "
                 f"Only {len(d1_rows) - n_zero_by_construction}/{len(d1_rows)} folds carry real, "
                 "non-trivial evidence about whether the JM correction helps or hurts. This is the same "
                 "'more than half the evidence could not have shown an edge' shape LAB-06's own OP-14 "
                 "finding already named in this lab's history -- the primary R estimate below is "
                 "computed over all 12 folds (guide's own registered procedure), but its EFFECTIVE "
                 "sample size for detecting a real effect is much thinner than 12 folds suggests."]

    lines += ["", "## D2 frozen continuations (guide SS2.4)"]
    if d2_records:
        lines += ["", "| origin | arm | SR_H1 | SR_H2 | D_age |", "|---|---|---:|---:|---:|"]
        for (origin, arm), rec in sorted(d2_records.items()):
            r = rec["result"]
            lines.append(f"| {origin} | {arm} | {r.get('sr_h1')} | {r.get('sr_h2')} | {r.get('d_age')} |")
    else:
        lines.append("- **NOT_YET_RUN** (scripts/run_sd03_d2.py has not been executed)")

    lines += ["", "## Continuous-account Sharpe (guide SS2.5)"]
    if deployment:
        lines += ["", "| arm | n_bars | n_fills | n_entries | cache_event |",
                 "|---|---:|---:|---:|---|"]
        for arm, rec in sorted(deployment.items()):
            lines.append(f"| {arm} | {rec['n_bars']} | {rec['n_fills']} | {rec['n_entries']} | "
                         f"{rec['cache_event']} |")
    else:
        lines.append("- **NOT_YET_RUN** (scripts/run_sd03_deployment.py has not been executed)")

    lines += ["", "## Inference (guide SS7.2/7.4, sd/inference_sd03.py — locked before FINAL)",
             f"- **decision: {decision['decision']}**"]
    if "r_ci" in decision:
        r_ci = decision["r_ci"]
        lines.append(f"- R point estimate: {r_ci.get('point_estimate')}, "
                     f"95% CI [{r_ci.get('ci_lower')}, {r_ci.get('ci_upper')}] "
                     f"(block length {r_ci.get('block_length')}, {r_ci.get('resamples')} resamples, "
                     f"seed {r_ci.get('seed')})")
    if "reason" in decision:
        lines.append(f"- reason: {decision['reason']}")

    lines += ["", "## Glossary",
             "- **D1** (guide SS2.2: primary decay label, same params, IS->forward Sharpe, "
             "measured fresh at each real FINAL origin)",
             "- **D2** (guide SS2.4: a frozen 112-day continuation of the SAME selected params, "
             "H1 (first 56 days) vs H2 (next 56 days), no account reset at the boundary -- "
             "measures whether the SAME candidate's own performance ages within one deployment)",
             "- **R = D_B - D_C** (guide SS2.3: paired reduction in Sharpe decay from adding the "
             "state-conditioned correction; positive means C decayed less than B)",
             "- **continuous account** (guide SS2.5/SD03.5: one account per arm running the WHOLE "
             "real path with actual admission/activation/fills, never 12 reset-and-restitched "
             "accounts)",
             "", "## Permitted conclusions",
             f"- Technical: preflight {preflight_result['overall']}, {len(fold_records)}/12 real "
             "FINAL folds present.",
             f"- Research: **{decision['decision']}** (guide SS7.4's own registered decision "
             "vocabulary). Technical PASS does not require Sharpe improvement.",
             "- Owner review: PENDING.", ""]
    return "\n".join(lines)


def main() -> int:
    preflight_result = pf.preflight(LAB)
    fold_records = load_final_folds()
    registration = json.loads((CFG / "registration.json").read_text(encoding="utf-8"))

    if len(fold_records) != 12:
        print(f"D1 archive incomplete: only {len(fold_records)}/12 real FINAL folds found -- "
             "rendering a PARTIAL report; run scripts/run_sd03_final_archive.py to completion "
             "for the real verdict")

    d1_rows = d1_table_rows(fold_records)
    d2_records = load_d2(sorted(fold_records))
    deployment = load_deployment()

    r_series = inf.paired_r_series([{"arms": fold["arms"]} for fold in fold_records.values()])
    q_series = inf.paired_q_series([{"arms": fold["arms"]} for fold in fold_records.values()])
    decision = inf.decide(r_series=r_series, q_series=q_series, seed=INFERENCE_SEED,
                          fold_records=list(fold_records.values()),
                          data_valid=len(fold_records) > 0)

    report_text = render_report(registration=registration, fold_records=fold_records, d1_rows=d1_rows,
                                d2_records=d2_records, deployment=deployment, decision=decision,
                                preflight_result=preflight_result)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report_text, encoding="utf-8")

    complete = (len(fold_records) == 12 and len(d2_records) == 12 * len(ARMS)
               and len(deployment) == len(ARMS))
    freeze = {
        "schema": "regime_lab.sd03_freeze.v1", "study_id": "sharpe_decay_sd_v1", "phase_id": "SD-03",
        "sealed_at_utc": utcnow(), "n_final_folds": len(fold_records), "n_d2_records": len(d2_records),
        "n_deployment_accounts": len(deployment), "complete": complete,
        "decision": decision["decision"],
    }
    FREEZE_PATH.write_text(json.dumps(freeze, indent=2, default=str) + "\n", encoding="utf-8")

    verdict = v3.verify_sd03(lab_root=LAB)
    (FINAL_DIR / "gate_receipt.json").write_text(json.dumps({
        "schema": "regime_lab.sharpe_decay_phase_gate.v1", "phase_id": "SD-03",
        "guide_version": "SD-GUIDE-1.0", "technical_gate": verdict["overall"],
        "research_decision": verdict["decision"], "required_gates": list(v3.REQUIRED_GATES),
        "verification": verdict, "owner_review": {"status": "PENDING", "decision_ref": None},
        "verified_at_utc": utcnow(),
    }, indent=2, default=str) + "\n", encoding="utf-8")

    print(json.dumps({"n_final_folds": len(fold_records), "n_d2_records": len(d2_records),
                      "n_deployment_accounts": len(deployment), "complete": complete,
                      "decision": decision["decision"], "verification_overall": verdict["overall"],
                      "gates": {k: g["pass"] for k, g in verdict["gates"].items()}}, indent=2))
    return 0 if complete and verdict["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
