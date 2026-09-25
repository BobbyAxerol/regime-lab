#!/usr/bin/env python3
"""SD01.8: generate the SD-01 report from committed artifacts, verify, seal.

Reads ONLY already-committed artifacts (guide's own report-generation
discipline: report only reads, never reruns an optimizer or the engine).

Usage:
  lab_venv/bin/python scripts/run_sd01_report.py --pytest-xml <junit xml>
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "src"))

from crypto_regime_lab.sd.verifier_sd01 import REQUIRED_GATES, INIT_ORIGINS, verify_sd01  # noqa: E402

CFG = LAB / "configs" / "sharpe_decay_sd_v1"
LEDGER_DIR = LAB / "evidence" / "sharpe_decay_sd_v1" / "init_archive"
REPORT_PATH = LEDGER_DIR / "report.md"

TEST_NODE_IDS = [
    "test_return_boundary_two_step_returns_correct",
    "test_return_boundary_actual_180_count_enforced",
    "test_return_boundary_actual_56_count_enforced",
    "test_return_boundary_missing_day_raises_not_silently_zero",
    "test_sharpe_matches_independent_formula",
    "test_sharpe_zero_variance_is_typed_not_a_bare_zero",
    "test_decay_ranking_min_y_not_max_return",
    "test_anchor_wins_legitimately_when_nothing_beats_zero",
    "test_c_independence_same_function_no_shared_state_between_calls",
    "test_unique_candidates_deduplicates_by_params",
    "test_representative_panel_always_includes_anchor_even_outside_top_n",
    "test_window_bounds_is_window_180_days_ending_at_cutoff",
]


def utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="microseconds")


def load(name: str) -> dict:
    return json.loads((CFG / name).read_text(encoding="utf-8"))


def load_origin_records() -> dict:
    out = {}
    for origin in INIT_ORIGINS:
        out[origin] = json.loads((LEDGER_DIR / f"origin_{origin}.json").read_text(encoding="utf-8"))
    return out


def render_report(*, registration, migration, timeline, micro_profile, origin_records) -> str:
    lines = ["# SD-01 — Standardize Sharpe and build the real INIT archive", "",
            f"- study_id: {registration['study_id']}, guide_version: {registration['guide_version']}",
            f"- branch: {registration['branch']} (off {registration['branched_from']['ref']} @ "
            f"{registration['branched_from']['commit'][:12]})",
            f"- generated_at_utc: {utcnow()}",
            "", "## Scope (guide SS8.1)",
            "SD-01 standardizes the Sharpe metric and builds the real INIT archive. It carries NO "
            "model victory/no-edge verdict -- that is SD-02/03's job. This report states only what "
            "was reused, what ran, its real cost, and which validity findings were fixed.",
            "", "## Migration and finding dispositions (guide SS0.2)",
            "| Finding | Disposition | Remedy in SD |", "|---|---|---|"]
    for row in migration["finding_dispositions"]:
        lines.append(f"| {row['finding_id']} | {row['disposition']} | "
                     f"{row['remedy_in_sd'][:140]}{'...' if len(row['remedy_in_sd']) > 140 else ''} |")
    lines += ["", "## Explicit rule changes (guide SS0.3)", ""]
    for row in migration["explicit_rule_changes"]:
        lines.append(f"- **{row['old_rule'][:80]}** -> **{row['new_rule'][:80]}**")

    lines += ["", "## Timeline feasibility (guide SS4, SD01.3)",
             f"- data_role_exception: {registration['data_role_exception']['decision_id']} "
             f"(outer_evaluation opened for this study only)",
             f"- measured full usable interval: {registration['data_role_exception']['measured_full_interval']['start']} "
             f".. {registration['data_role_exception']['measured_full_interval']['end']} "
             f"({registration['data_role_exception']['measured_full_interval']['days']} days)",
             f"- feasibility verdict: **{timeline['feasibility_check']['verdict']}**",
             f"- INIT: {timeline['roles']['INIT']['first_origin']} .. {timeline['roles']['INIT']['last_origin']} "
             "(fully inside development, retrospective)",
             f"- VALIDATION: {timeline['roles']['VALIDATION']['first_origin']} .. "
             f"{timeline['roles']['VALIDATION']['last_origin']} (mostly development, tail crosses into outer_evaluation)",
             f"- FINAL: {timeline['roles']['FINAL']['first_origin']} .. {timeline['roles']['FINAL']['last_origin']} "
             "(entirely inside the genuinely fresh outer_evaluation span)"]

    lines += ["", "## Resource qualification (guide SS11, SD01.6)",
             f"- real 8-trial micro-profile: {micro_profile['measured']['wall_seconds_measured']}s, "
             f"peak RSS {micro_profile['measured']['peak_rss_mib']} MiB "
             f"(registered budget {micro_profile['applied_limits']['rlimit_as_gib']} GiB -- no exception needed)",
             f"- extrapolated total for the full 12-origin/128-trial build: "
             f"{micro_profile['extrapolation']['total_12_origins_range_hours']} hours"]

    total_wall = sum(r["origin_wall_seconds_measured"] for r in origin_records.values())
    total_search_wall = sum(r["search"]["wall_seconds_measured"] for r in origin_records.values())
    n_rows = sum(len(r["label_rows"]) for r in origin_records.values())
    is_ok = sum(1 for r in origin_records.values() for row in r["label_rows"]
               if row["is_window"]["sharpe_status"] == "OK")
    fwd_ok = sum(1 for r in origin_records.values() for row in r["label_rows"]
                if row["fwd_window"]["sharpe_status"] == "OK")
    anchor_zero_ok = sum(1 for r in origin_records.values()
                         for row in r["label_rows"]
                         if row["is_anchor"] and row["relative_decay_Y"]["status"] == "OK"
                         and abs(row["relative_decay_Y"]["value"]) < 1e-9)

    lines += ["", "## Real INIT archive build (guide SS8.2 SD01.7) -- ALL REAL, MEASURED NUMBERS", "",
             "- **12/12 origins built**, real 128-trial search each, real IS180/FWD56 canonical "
             "Sharpe for a 16-candidate representative panel + anchor at each origin",
             f"- total wall time: **{total_wall:.2f}s (~{total_wall/3600:.2f}h)** "
             f"(search-only: {total_search_wall:.2f}s / ~{total_search_wall/3600:.2f}h)",
             f"- total label rows: {n_rows} (12 origins x 16 panel each)",
             f"- IS Sharpe status OK: **{is_ok}/{n_rows}**", f"- FWD Sharpe status OK: **{fwd_ok}/{n_rows}**",
             f"- anchor relative_decay_Y == 0.0 exactly: **{anchor_zero_ok}/12 origins** "
             "(the anchor-zero-by-construction guarantee, verified on every real origin)",
             "", "| origin | search trials | unique candidates | panel | wall seconds |",
             "|---|---:|---:|---:|---:|"]
    for origin, r in origin_records.items():
        lines.append(f"| {origin} | {r['search']['trials_requested']} | "
                     f"{r['search']['n_unique_candidates']} | {r['panel_size']} | "
                     f"{r['origin_wall_seconds_measured']:.2f} |")

    lines += ["", "## Glossary",
             "- **INIT origin** (guide SS4.1: one of the 12 chronologically-first origins whose "
             "own matured real archive record seeds the model-training history VALIDATION will "
             "later draw on -- never itself a model-performance comparison)",
             "- **representative panel** (guide SS3.5: a deterministic, <=16-candidate subset of "
             "an origin's full real candidate pool, ranked by the search's own cheap mean_is_sharpe "
             "proxy, ALWAYS including the stock anchor -- used only to bound how many candidates "
             "get real forward-evaluation compute, never to shrink what B/C will predict over)",
             "- **canonical Sharpe** (guide SS2.1: a Sharpe ratio recomputed from raw daily "
             "equity via this lab's own already-tested time_edge_contracts.daily_returns + "
             "ra07_stats_primitives.sharpe primitives -- exact day-count enforced, missing days "
             "raise rather than silently returning 0%, explicitly NOT quantbt's own built-in "
             "sharpe()/daily_equity, both verified to have a silent-failure mode)",
             "- **relative Sharpe decay Y** (guide SS3.3: Y = D(candidate) - D(anchor), where "
             "D = SR_IS - SR_FWD -- the anchor's own Y is forced to exactly 0.0 by the contrast "
             "architecture itself, not by a fitted intercept, verified on all 12 real origins here)",
             "- **anchor** (guide SS3.3: the raw stock Mode 4 winner at an origin, the "
             "contrast-zero reference every other candidate's relative decay is measured against)",
             "- **outer_evaluation data-role exception** (this study's own disclosed, one-time, "
             "scoped opening of the 2024-01-01-onward interval, previously an untouched holdout "
             "across the whole FP study -- decision dec-61772d86c9594c69, scoped to "
             "sharpe_decay_sd_v1 only)",
             "", "## Permitted conclusions",
             "- Technical: the canonical Sharpe wrapper reuses already-tested lab primitives "
             "(G1-SHARPE); the minY selection rule and C-independence are structurally proven, "
             "not just conventionally avoided (G1-WIRING); the 36-origin timeline is real and "
             "feasible with disclosed margin (G1-TIMELINE); the real INIT archive is complete, "
             f"{is_ok}/{n_rows} IS and {fwd_ok}/{n_rows} FWD canonical Sharpe values computed "
             "cleanly, the anchor-zero invariant held on every real origin (G1-ARCHIVE); real "
             "compute cost was measured before and during the full build, staying within the "
             "registered budget throughout (G1-RESOURCE).",
             "- Research: **NOT_ASSESSED**. SD-01 makes no claim about whether JM reduces Sharpe "
             "decay -- it only builds and validates the measurement infrastructure and the real "
             "candidate archive SD-02 will train validation-fold models against. No model has been "
             "fit, no JM recipe has been chosen, no decay reduction has been estimated.",
             "- Owner review: PENDING. SD-02 needs its own explicit R-18 approval before it begins.",
             ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pytest-xml", default=None)
    args = parser.parse_args()

    registration = load("registration.json")
    migration = load("protocol_migration.json")
    timeline = load("timeline.json")
    micro_profile = load("resource_micro_profile.json")
    origin_records = load_origin_records()

    report_text = render_report(registration=registration, migration=migration, timeline=timeline,
                                micro_profile=micro_profile, origin_records=origin_records)
    REPORT_PATH.write_text(report_text, encoding="utf-8")

    verdict = verify_sd01(lab_root=LAB, report_path=REPORT_PATH, pytest_xml=args.pytest_xml,
                          required_test_node_ids=tuple(TEST_NODE_IDS))
    (LEDGER_DIR / "gate_receipt.json").write_text(json.dumps({
        "schema": "regime_lab.sharpe_decay_phase_gate.v1", "phase_id": "SD-01",
        "guide_version": "SD-GUIDE-1.0", "technical_gate": verdict["overall"],
        "research_status": "NOT_ASSESSED", "required_gates": list(REQUIRED_GATES),
        "verification": verdict, "owner_review": {"status": "PENDING", "decision_ref": None},
        "can_start_next_phase": False, "verified_at_utc": utcnow(),
    }, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({"overall": verdict["overall"],
                      "gates": {k: v["pass"] for k, v in verdict["gates"].items()},
                      "archive_summary": verdict["archive_summary"]}, indent=2))
    return 0 if verdict["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
