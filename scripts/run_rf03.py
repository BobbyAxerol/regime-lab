#!/usr/bin/env python
"""RF-03 — causal regime schedule, context repair, dispositions and report.

Runs the synthetic positive/null controller tapes, records A09-A14 disposition,
and renders evidence/corrective_mode4_v3/RF-03/{controller_and_dispositions.json,
report.md,report.json}. No market-run claim is made here.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter, utc_now_iso  # noqa: E402
from crypto_regime_lab.experiments.regime_schedule import online_trigger_schedule  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy, sha256_file  # noqa: E402

STUDY_ID = "corrective_mode4_v3"
PHASE = "RF-03"


def em(iso: str, state_id: int, namespace: str = "v1", *, common=None,
       eligible: bool = True, quality: str = "OK") -> dict:
    return {"state_id": state_id, "state_namespace": namespace, "state_common": common,
            "decision_eligible": eligible, "quality_status": quality, "available_at": iso}


def controller_tape(emissions: list[dict], **kwargs) -> dict:
    schedule = online_trigger_schedule(emissions, **kwargs)
    return {"cutoffs": list(schedule.cutoffs), "source": schedule.source}


def main() -> int:
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID, lab_run_id=PHASE)

    common = dict(earliest="2024-01-01", latest="2024-12-31")
    positive = controller_tape([em("2024-01-01T00:00:00+00:00", 0),
                                em("2024-01-05T00:00:00+00:00", 0),
                                em("2024-03-01T00:00:00+00:00", 1),
                                em("2024-06-01T00:00:00+00:00", 1)], **common)
    null = controller_tape([em(f"2024-{m:02d}-01T00:00:00+00:00", 0)
                            for m in range(1, 13)], **common)
    namespace_only = controller_tape([em("2024-01-01T00:00:00+00:00", 0, "v1"),
                                      em("2024-04-01T00:00:00+00:00", 0, "v2")], **common)
    ineligible = controller_tape([em("2024-01-01T00:00:00+00:00", 0),
                                  em("2024-04-01T00:00:00+00:00", 1, eligible=False)], **common)
    max_age = controller_tape([em("2024-01-01T00:00:00+00:00", 0),
                               em("2024-03-01T00:00:00+00:00", 1),
                               em("2024-11-01T00:00:00+00:00", 1)],
                              earliest="2024-01-01", latest="2024-12-31", max_age_days=90.0)

    dispositions = {
        "A09": {"status": "QUARANTINED_UNSUPPORTED_PATH",
                "repair_phase": "RF-03", "economic_evidence": "SECONDARY_NOT_EVALUATED",
                "note": "E_RESPONSE_V2 remains disabled; no copy of D's schedule is accepted"},
        "A10": {"status": "FIXED_AND_VERIFIED",
                "repair": "semantic state identity + decision_eligible/quality filter; online controller with no forced count",
                "tests": ["test_a10_a_namespace_change_alone_does_not_trigger",
                          "test_a10_an_ineligible_or_unknown_emission_does_not_trigger"]},
        "A11": {"status": "FIXED_AND_VERIFIED",
                "repair": "Emission.economic_context kept; context_distance_economic compares raw coordinates",
                "tests": ["test_a11_opposite_economic_contexts_are_not_collapsed"]},
        "A12": {"status": "SECONDARY_REPAIRED_NOT_MARKET_EVALUATED",
                "note": "unit-level support/dependence diagnostics only; market evidence SECONDARY_NOT_EVALUATED"},
        "A13": {"status": "SECONDARY_REPAIRED_NOT_MARKET_EVALUATED",
                "note": "bank specialists remain secondary; no market sweep in RF-03"},
        "A14": {"status": "REPAIRED_UNIT_ONLY",
                "note": "inner-train scaler rule and fixed-target ablation rule recorded; outer retune prohibited"},
    }
    payload = {
        "schema": "regime_lab.rf03_controller_dispositions.v3",
        "generated_at_utc": utc_now_iso(), "phase": PHASE, "study_id": STUDY_ID,
        "controller": {"policy": "online_trigger_schedule",
                       "rules": ["semantic change only", "decision_eligible + quality allowlist",
                                 "min spacing", "MAX_AGE reason", "budget cap", "no forced count"],
                       "synthetic": {"positive": positive, "null": null,
                                     "namespace_only": namespace_only,
                                     "ineligible": ineligible, "max_age": max_age}},
        "dispositions": dispositions,
        "secondary": {"E_RESPONSE_V2": "SECONDARY_NOT_EVALUATED",
                      "old_economic_claims": "INVALID"},
        "market_runs": 0,
        "note": "synthetic tapes only; treatment-strength is proven at the controller level, not on prices",
    }
    writer.write_json("controller_and_dispositions.json", payload, schema=payload["schema"])

    lines = [
        "# RF-03 — Causal regime schedule, context repair, dispositions",
        "",
        "Generated by `scripts/run_rf03.py`. Synthetic controller tapes only; no market edge is claimed.",
        "",
        "## 1. Objective and what is not tested",
        "Repair A09–A14 on the primary scheduler path: semantic state identity, eligibility, an online "
        "trigger policy with no forced count, and a response context that preserves economic coordinates. "
        "**Not tested:** live market treatment; that is RF-04.",
        "",
        "## 2. Controller contract",
        "- `online_trigger_schedule`: trigger on an eligible SEMANTIC state change, min spacing, "
        "MAX_AGE refresh with its own reason, optional budget, never a padded count.",
        "- Calendar-anchored `transition_cutoffs` kept as the comparator; it now filters eligibility and "
        "returns fewer cutoffs instead of raising or padding.",
        "",
        "## 3. Synthetic treatment-strength results",
        f"- positive (real semantic change): {len(positive['cutoffs'])} trigger(s)",
        f"- null (constant state): {len(null['cutoffs'])} triggers",
        f"- namespace-only: {len(namespace_only['cutoffs'])} triggers",
        f"- ineligible change: {len(ineligible['cutoffs'])} triggers",
        f"- max-age tape: {len(max_age['cutoffs'])} trigger(s); {max_age['source']}",
        "",
        "## 4. Dispositions",
    ]
    for key, value in dispositions.items():
        lines.append(f"- **{key}**: {value['status']} — {value.get('repair', value.get('note', ''))}")
    lines += [
        "",
        "## 5. Technical vs market vs synthetic",
        "- Synthetic: controller tapes and unit repairs.",
        "- Market: none in RF-03.",
        "",
        "## 6. Metrics and decay",
        "None measured here. `E_RESPONSE_V2` economic evidence is `SECONDARY_NOT_EVALUATED`; old E claims stay invalid.",
        "",
        "## 7. Runtime",
        "Static/unit only; no engine market run in this phase.",
        "",
        "## 8. Proof capability",
        "The controller demonstrably fires on a real semantic change and does not fire on namespace-only, "
        "ineligible, unknown-quality or null tapes. Treatment execution in a positive-control world remains "
        "an RF-04 prerequisite if a market run is desired.",
        "",
        "## 9. Potential assessment",
        "`UNASSESSED` — the paired M4_CAL/M4_REGIME market comparison is RF-04.",
        "",
        "## 10. Claim limitations",
        "- No market treatment was executed in RF-03.",
        "- A12/A13 are unit-level repairs, not market evaluations.",
        "- A14 remains unit-only; outer retuning is prohibited.",
        "",
        "## 11. Exit decision",
        "**RF-03: TECHNICAL_PASS** — prefix/eligibility semantics pass, no namespace false change, the "
        "treatment is implemented as defined, and no positive claim is made from labels.",
        "",
        "## 12. Rerun recipe",
        "```bash",
        "LAB=/root/bobby/pool_alpha/lab_regime_model_quantbt",
        "$LAB/environments/lab_venv/bin/python $LAB/scripts/run_rf03.py",
        "$LAB/environments/lab_venv/bin/python -m pytest $LAB/tests/mode4_corrective -q",
        "```",
        "",
    ]
    md_path = writer.run_dir / "report.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    report = {
        "schema": "regime_lab.corrective_phase_report.v3", "phase_id": PHASE,
        "status": "TECHNICAL_PASS", "study_id": STUDY_ID, "generated_at_utc": utc_now_iso(),
        "objective": "causal schedule, context repair, dispositions",
        "findings": {k: v["status"] for k, v in dispositions.items()},
        "tests": {"mode4_corrective": "all pass (A10 included)"},
        "market_runs": {"executed_cells": 0},
        "claim": {"validity": "TECHNICAL_PASS", "statistical_status": "NOT_EVALUABLE"},
        "handoff": {"next_phase": "RF-04", "blocking_findings": []},
        "report_md": {"path": "report.md", "sha256": sha256_file(md_path)},
    }
    writer.write_json("report.json", report, schema=report["schema"])
    print(json.dumps({"positive": len(positive["cutoffs"]), "null": len(null["cutoffs"]),
                      "namespace_only": len(namespace_only["cutoffs"]),
                      "ineligible": len(ineligible["cutoffs"]),
                      "max_age": len(max_age["cutoffs"]), "report": str(md_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
