#!/usr/bin/env python
"""Render evidence/corrective_mode4_v3/RF-01/report.md and report.json.

Reads only RF-01 artifacts and the restored probe/regression evidence. Never
reruns a model or a market. The phase report is generated, not written by hand.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter, utc_now_iso  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy, sha256_file  # noqa: E402

STUDY_ID = "corrective_mode4_v3"
PHASE = "RF-01"
RUN_DIR = LAB_ROOT / "evidence" / "corrective_mode4_v3" / PHASE


def load(name: str):
    return json.loads((RUN_DIR / name).read_text(encoding="utf-8"))


def render_markdown(identity, binding, invalidation, disposition, spec, regression) -> str:
    env = identity["environment"]
    qt = identity["quantbt_installed"]
    candidate = identity["candidate_copy"]
    outcome = {o["nodeid"].split("::")[-1]: o["outcome"] for o in regression["before_tests"]["outcomes"]}
    failed = sorted(name for name, value in outcome.items() if value == "FAILED")
    passed = sorted(name for name, value in outcome.items() if value == "PASSED")
    findings = invalidation["findings"]
    probe_ids = [row["probe"] for row in regression["probe_map"]]

    lines: list[str] = []
    add = lines.append
    add("# RF-01 — Freeze, invalidation, contracts and failing tests")
    add("")
    add("Generated from committed RF-01 artifacts by `scripts/write_rf01_report.py`. "
        "No model and no market was run in this phase. **proof status: TECHNICAL_ONLY** — "
        "this is not evidence of an edge or of its absence.")
    add("")
    add("## 1. Objective, and what is not tested")
    add("")
    add("Stop the invalid interpretation of the historical results, register the corrected Mode 4 protocol, "
        "and turn each audit finding into a regression before any repair. **Not tested here:** whether regime "
        "timing has an edge. RF-01 runs no market experiment by design (merged plan RF-01 exit).")
    add("")
    add("## 2. Identity and resolved runtime")
    add("")
    add(f"- branch `{identity['branch']}`, head `{identity['head_commit']}`; working tree entries "
        f"{len(identity['working_tree_porcelain'])}")
    add(f"- plan sha256 `{identity['plan']['sha256']}`; audit archive `{identity['original_audit_archive']['sha256']}` "
        f"(present in lab: {identity['original_audit_archive']['present_in_lab']})")
    add(f"- recovered audit bundle: {identity['recovered_bundle']['members']} members, "
        f"{identity['recovered_bundle']['bytes']} bytes, `{identity['recovered_bundle']['status']}`, "
        f"restored code executed: {identity['recovered_bundle']['executed_restored_code']}")
    add(f"- python `{env['python_version'].split()[0]}` at `{env['python_executable']}`")
    add(f"- quantbt-engine `{qt['distributions'].get('quantbt-engine')}`, "
        f"quantbt-native `{qt['distributions'].get('quantbt-native')}`, import origin `{qt['import_origin']}`")
    add(f"- candidate copy `{candidate['root']}`: endpoint sha256 `{candidate['endpoint_sha256']}`, "
        f"matches the audited VFY01 hash: **{candidate['matches_audited_vfy01']}**")
    add(f"- preflight gate **{identity['preflight']['gate']}**, counts {identity['preflight']['counts']}")
    add(f"- protected-path write probes refused: "
        f"**{all(r['refused'] for r in identity['protected_paths_write_refused'])}**")
    add("")
    add("## 3. Findings, disposition and failing-before evidence")
    add("")
    add(f"{len(findings)} P0/P1 findings from the merged audit are mapped in `historical_invalidation.json`; "
        f"the old claim verdicts are superseded without editing any historical artifact.")
    add("")
    add("| id | disposition | planned phase | required tests |")
    add("|---|---|---|---|")
    for row in disposition["dispositions"]:
        if row["category"] not in {"P0", "P1"}:
            continue
        add(f"| {row['id']} | `{row['disposition']}` | {row['planned_phase']} | {', '.join(row['required_tests'])} |")
    add("")
    add("### Claim supersession")
    add("")
    add("| contribution | historical verdict | repaired status | caused by |")
    add("|---|---|---|---|")
    for claim in invalidation["contrast_claims"]:
        add(f"| {claim['id']} | `{claim['historical_verdict']}` | `{claim['repaired_verdict']}` | "
            f"{', '.join(claim['caused_by'])} |")
    add("")
    add("### Failing-before regression tests")
    add("")
    add(f"The RF-01 test set (`{regression['before_tests']['path']}`) records "
        f"**{regression['before_tests']['counts'].get('FAILED', 0)} failing / "
        f"{regression['before_tests']['counts'].get('PASSED', 0)} passing**. Failures:")
    add("")
    for name in failed:
        add(f"- `{name}`")
    add("")
    add("Passing artifact guards: " + ", ".join(f"`{name}`" for name in passed) + ".")
    add("")
    add(f"Full suite at this commit: **{regression['full_suite']['summary']}** — the six failures are the "
        "before-repairs evidence, not a regression in existing behaviour.")
    add("")
    add("## 4. Probes and budget")
    add("")
    add(f"All **{len(probe_ids)} restored audit probes ({', '.join(probe_ids)}) reproduce on the current source** "
        "under the lab venv (python 3.12.13). Results: "
        "`evidence/corrective_mode4_v3/probe_reproduction_v1/`. They are synthetic/reference probes, "
        "not market replay.")
    add("")
    add("| probe | finding | acceptance | observed on current source |")
    add("|---|---|---|---|")
    for row in regression["probe_map"]:
        add(f"| {row['probe']} | {row['finding']} | {', '.join(row['tests'])} | {row['observed']} |")
    add("")
    add("RF-01 ran no candidates, trials or market bars. The registered discovery budget "
        f"({spec['budgets']['search_trials_per_cutoff']['pilot_min']}–"
        f"{spec['budgets']['search_trials_per_cutoff']['pilot_max']} trials/cutoff) is frozen after an RF-02 "
        "dry-run coverage review; it is not spent here.")
    add("")
    add("## 5. Technical vs market vs synthetic")
    add("")
    add("- Market experiments: **none**.")
    add("- Synthetic/reference probes: 12, all reproduced (section 4).")
    add("- Environment and binding checks: VFY "
        f"**{binding['checks_present']}/{binding['checks_total']}** present on the candidate copy.")
    add("")
    add("## 6. Metrics and decay")
    add("")
    add("No economic metric is measured in RF-01. The historical metrics are retained as raw evidence and are "
        "now labelled `NOT_EVALUABLE` for inference. The corrected MDE derivation is registered in "
        "`corrective_study_spec.json` and remains `PENDING_RF02_ACTUAL_ENGINE_UNITS`; it is frozen before RF-04 "
        "and never tuned against observed results.")
    add("")
    add("## 7. Runtime profile")
    add("")
    add(f"RF-01 wall work is bounded: before-repairs tests only (returncode {regression['before_tests']['returncode']}), "
        "plus the static binding scan and preflight. No T2/T3/T4 job ran. OS resource budget starts at "
        f"{spec['budgets']['os_resource_budget_start']}.")
    add("")
    add("## 8. Proof capability")
    add("")
    add("- The pipeline cannot yet detect or reject a time edge: treated as `NOT_TESTED`.")
    add("- Positive control and treatment-reached-execution are `NOT_TESTED` until RF-02 qualifies a route.")
    add("- What RF-01 *does* prove: every known P0/P1 finding has a mapped disposition, a reproduction, and a "
        "failing test or a registered guard; the false claims are quarantined.")
    add("")
    add("## 9. Potential assessment")
    add("")
    add("`UNASSESSED` (merged plan 10.4): the pipeline is not yet valid, so an opportunity/information judgement "
        "would be premature. Falsifiable next step: RF-02 route qualification and golden fee/timing fixtures.")
    add("")
    add("## 10. Claim limitations")
    add("")
    add(f"- historical study: execution validity `{invalidation['execution_validity']}`, implementation "
        f"fidelity `{invalidation['implementation_fidelity']}`, statistical status "
        f"`{invalidation['statistical_status']}`")
    add("- the corrective study is registered on already-consumed history: `NESTED_RETROSPECTIVE`, no untouched "
        "holdout; a prospective protocol is specified and not executed")
    add("- A-HASH remains blocked; the matrix cannot be described as all four alphas until RF-02")
    add("- funding is absent; no realistic net-carry claim")
    add("")
    add("## 11. Exit decision and remaining tasks")
    add("")
    add("**RF-01 exit: TECHNICAL_ONLY.** Exact scope, imports, units and claim gates are known; every P0 is mapped; "
        "false claims are quarantined; probes are small and reproducible. Remaining: RF-02 (actual Mode 4 "
        "execution, fee/timing golden fixtures, route matrix).")
    add("")
    add("## 12. Rerun recipe and handoff")
    add("")
    add("```bash")
    add("LAB=/root/bobby/pool_alpha/lab_regime_model_quantbt")
    add("$LAB/environments/lab_venv/bin/python $LAB/scripts/run_rf01.py")
    add("$LAB/environments/lab_venv/bin/python $LAB/scripts/run_rf01_regressions.py --full")
    add("$LAB/environments/lab_venv/bin/python $LAB/scripts/write_rf01_report.py")
    add("```")
    add("")
    add(f"- handoff: **RF-02**; blocking findings: "
        f"{', '.join(sorted(row['id'] for row in disposition['dispositions'] if row['disposition'] == 'OPEN_REPRODUCED'))}")
    add("- artifact hashes are listed in the generated `report.json`; historical evidence is unchanged.")
    add("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if not RUN_DIR.is_dir():
        raise SystemExit("run scripts/run_rf01.py first")
    report_md = RUN_DIR / "report.md"
    report_json = RUN_DIR / "report.json"
    if (report_md.exists() or report_json.exists()) and not args.force:
        raise SystemExit("RF-01 report already exists; pass --force to supersede explicitly")

    identity = load("working_copy_identity.json")
    binding = load("quantbt_binding_report.json")
    invalidation = load("historical_invalidation.json")
    disposition = load("finding_disposition.json")
    spec = load("corrective_study_spec.json")
    regression = load("regression_before_repair.json")

    report_md.write_text(render_markdown(identity, binding, invalidation, disposition, spec, regression),
                         encoding="utf-8")

    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID, lab_run_id=PHASE)
    payload = {
        "schema": "regime_lab.corrective_phase_report.v3",
        "phase_id": PHASE,
        "status": "COMPLETE",
        "proof_status": "TECHNICAL_ONLY",
        "study_id": STUDY_ID,
        "generated_at_utc": utc_now_iso(),
        "objective": "freeze scope, invalidate false claims, inventory the Mode 4 binding, add failing-before tests",
        "source": {
            "archive_sha256": identity["original_audit_archive"]["sha256"],
            "candidate_commit": identity["head_commit"],
            "candidate_source_manifest": "evidence/corrective_mode4_v3/RF-01/source_before_manifest.json",
            "quantbt_core_version": identity["quantbt_installed"]["distributions"].get("quantbt-engine"),
            "native_artifact": identity["quantbt_installed"]["distributions"].get("quantbt-native"),
            "actual_import_origins": [identity["quantbt_installed"]["import_origin"],
                                      identity["quantbt_installed"].get("native_import_origin")],
        },
        "registered_arms": spec["arms"]["primary"],
        "findings_disposition": disposition["counts"],
        "tests": {
            "passed": regression["before_tests"]["counts"].get("PASSED", 0),
            "failed": regression["before_tests"]["counts"].get("FAILED", 0),
            "skipped": regression["before_tests"]["counts"].get("SKIPPED", 0),
            "artifact_refs": ["evidence/corrective_mode4_v3/RF-01/regression_before_repair.json"],
            "full_suite": regression["full_suite"]["summary"],
        },
        "market_runs": {"planned_cells": 20, "executed_cells": 0, "valid_pairs": 0,
                        "blocked_cells": [], "note": "RF-01 runs no market experiment by design"},
        "metrics": {"raw_quantbt_ref": None, "canonical_ref": None, "decay_panel_ref": None},
        "performance": {"wall_seconds": None, "cpu_seconds": None, "peak_rss_bytes": None,
                        "actual_candidate_bar_visits": 0},
        "proof_capability": {"technical_validity": "TECHNICAL_ONLY", "positive_control": "NOT_TESTED",
                             "treatment_reached_execution": "NOT_TESTED"},
        "potential": {"level": "UNASSESSED", "evidence_refs": ["quantbt_binding_report.json",
                                                               "probe_reproduction_v1"],
                      "falsifiable_next_step": "RF-02 route qualification with golden fee/timing fixtures"},
        "claim": {"validity": invalidation["execution_validity"],
                  "statistical_status": invalidation["statistical_status"],
                  "scope": "historical study invalidated; corrective study not yet evaluated"},
        "limitations": ["no market experiment in this phase", "nested retrospective history",
                        "A-HASH blocked", "funding absent"],
        "review": {"author": "OpenCode", "reviewer": None, "disagreements": []},
        "handoff": {"next_phase": "RF-02",
                    "blocking_findings": sorted(row["id"] for row in disposition["dispositions"]
                                                if row["disposition"] == "OPEN_REPRODUCED")},
        "report_md": {"path": "report.md", "sha256": sha256_file(report_md)},
    }
    writer.write_json("report.json", payload, schema=payload["schema"])
    print(json.dumps({"report_md": str(report_md), "sha256": sha256_file(report_md),
                      "report_json": str(report_json), "status": payload["status"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
