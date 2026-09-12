#!/usr/bin/env python
"""Which numbered guide subsection does nothing in this lab reference?

The phase audits ask *did every L0N.M task get done*. They cannot ask whether a
guide requirement belongs to no task at all — and that blind spot has produced
four findings so far: the compute-budget contract (§10.5), the CLI stage
contract (§13.5), the identity taxonomy (§13.1), and the six captures §10.1 asks
for from the installed selector.

So the question is asked directly. Every `## N.M` heading in the guide is
searched for across the lab's checklists, tests, source and artifacts. A
subsection nothing mentions is not necessarily unimplemented — but it is
certainly unclaimed, and unclaimed is where those four were found.

Not a pass/fail gate on its own: some subsections are prose about method with
nothing to check. The output is a worklist, and the ones the lab has decided are
prose-only are listed here by name so the decision is recorded rather than
implied.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))
sys.path.insert(0, str(LAB_ROOT / "scripts"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter, utc_now_iso  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402
from audit_lab09 import walk  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"
GUIDE = LAB_ROOT / "QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md"
SEARCH_DIRS = ("configs", "scripts", "src", "tests", "reports")

#: Subsections the lab has decided carry no separately checkable requirement:
#: they are framing, a table of contents, or restate a rule enforced elsewhere.
#: Listed BY NAME so the decision is on the record instead of being implied by a
#: silent absence, and so adding to this list is a visible act.
PROSE_ONLY = {
    "0.3": "how to read the document",
    "1.2": "what was verified while WRITING the guide, in an environment that was not the pinned "
           "one. Its one actionable line -- confirm the installed signatures, lockfiles and "
           "source SHA -- is LAB-01's and was discharged there",
    "1.3": "which repository pages were cross-read while writing the guide, explicitly not a "
           "consistent checkout. Its actionable line is the same one, and the guide says so",
    "5.1": "the target directory tree, realised as the tree itself",
}

#: Guide 0.1 is the user's own list of twelve approved conditions. It is not
#: prose: every line is a standing constraint. It is also not a phase task, so
#: nothing claimed it -- the same blind spot that hid the compute budget, the CLI
#: contract and the identity taxonomy. Each is mapped to where it is ENFORCED,
#: and the pointer is resolved rather than asserted.
APPROVED_CONDITIONS = [
    ("0.1.1", "run as .py and CLI; a notebook is not the harness",
     "src/crypto_regime_lab/cli.py"),
    ("0.1.2", "a new lab directory, separate from QuantBT and the production alpha directory",
     "configs/sandbox_policy.json:protected_roots"),
    ("0.1.3", "strategy/model/features stay in the research layer; QuantBT does simulation",
     "configs/api_binding_map.json:operations"),
    ("0.1.4", "the jump model is primary; rule-based and HMM/GMM are budgeted comparators",
     "configs/lab08_data_ablation.json:complexity_ladder"),
    ("0.1.5", "inference, parameter switching, bank refresh and retraining are four clocks",
     "configs/lab06_policy_spec.json:clocks"),
    ("0.1.6", "use the informative blocks with coverage, not every column",
     "configs/feature_schema.json:primary_core_features"),
    ("0.1.7", "spot from 2020-01-01 is treated as clean; operational checks only",
     "configs/study_registration.json:spot_clean_from"),
    ("0.1.8", "the market-context universe is point-in-time eligible",
     "configs/data_eligibility.json:per_symbol"),
    ("0.1.9", "the supplied presets are retrospective reference, never an OOS claim",
     "configs/lab08_pilot_protocol.json:preset_role"),
    ("0.1.10", "the four alpha copies are versioned, and execution repair is separated from a "
               "thesis change",
     "configs/semantic_delta.json:change_kinds"),
    ("0.1.11", "every report, JSON and chart source is kept; negatives are not dropped",
     "configs/lab08_discovery.json:design_selection"),
    ("0.1.12", "nothing is published, merged, sent live, or upgraded in production",
     "configs/study_registration.json:live_execution_allowed"),
]


def headings() -> list[tuple[str, str]]:
    out = []
    for line in GUIDE.read_text().splitlines():
        match = re.match(r"^#{1,3} (\d+(?:\.\d+)?)\s+(.*)$", line)
        if match:
            out.append((match.group(1), match.group(2).strip()))
    return out


def references(section: str) -> dict:
    """Where the lab mentions this subsection, in any of the forms it uses."""
    patterns = [f"G{section}.", f"guide {section}", f"guide_{section}",
                f"§{section}", f"guide §{section}", f'"{section}"']
    hits: dict[str, list[str]] = {}
    for pattern in patterns:
        found = subprocess.run(
            ["grep", "-rlF", pattern, *SEARCH_DIRS],
            cwd=str(LAB_ROOT), capture_output=True, text=True).stdout.split()
        for path in found:
            if "audit_guide_section_coverage" in path or "guide_section_coverage" in path:
                continue          # this file and its own output do not count
            hits.setdefault(path, []).append(pattern)
    return hits


def main() -> int:
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    rows = []
    condition_sections = {identifier.rsplit(".", 1)[0] for identifier, _c, _p
                          in APPROVED_CONDITIONS}
    for section, title in headings():
        hits = references(section)
        rows.append({
            "section": section,
            "title": title,
            "referenced_by": sorted(hits)[:8],
            "reference_count": len(hits),
            "in_a_checklist": any("checklist" in path for path in hits),
            "in_a_test": any(path.startswith("tests/") for path in hits),
            "status": ("PROSE_ONLY" if section in PROSE_ONLY
                       else "ENFORCED_VIA_CONDITION_MAP" if section in condition_sections
                       else "REFERENCED" if hits else "UNCLAIMED"),
            "prose_reason": PROSE_ONLY.get(section),
        })

    approved = []
    for identifier, condition, pointer in APPROVED_CONDITIONS:
        name, _, path = pointer.partition(":")
        artifact = LAB_ROOT / name
        if not artifact.exists():
            approved.append({"id": identifier, "condition": condition, "pointer": pointer,
                             "status": "BROKEN", "detail": f"no such path {name}"})
            continue
        if not path or not name.endswith(".json"):
            approved.append({"id": identifier, "condition": condition, "pointer": pointer,
                             "status": "ENFORCED", "detail": "path exists"})
            continue
        ok, detail = walk(json.loads(artifact.read_text()), path)
        approved.append({"id": identifier, "condition": condition, "pointer": pointer,
                         "status": "ENFORCED" if ok else "BROKEN", "detail": detail})

    unclaimed = [r for r in rows if r["status"] == "UNCLAIMED"]
    untested = [r for r in rows if r["status"] == "REFERENCED" and not r["in_a_test"]]
    document = {
        "schema": "crypto_regime_lab.guide_section_coverage.v1",
        "generated_at_utc": utc_now_iso(),
        "guide": GUIDE.name,
        "question": ("which numbered guide subsection does nothing in this lab reference? That "
                     "is the blind spot the phase audits cannot see, and four findings have come "
                     "out of it"),
        "sections_total": len(rows),
        "referenced": sum(1 for r in rows if r["status"] == "REFERENCED"),
        "enforced_via_condition_map": [r["section"] for r in rows
                                       if r["status"] == "ENFORCED_VIA_CONDITION_MAP"],
        "prose_only": sorted(PROSE_ONLY),
        "scope": ("numbered SUBSECTIONS (`## N.M`). Top-level `# N.` headings are chapter "
                  "titles and carry no separate requirement of their own"),
        "unclaimed": [r["section"] for r in unclaimed],
        "referenced_but_no_test_mentions_it": [r["section"] for r in untested],
        "approved_conditions": {
            "source": "guide 0.1, the user's own list of twelve approved conditions",
            "why_here": ("every line is a standing constraint and none is a phase task, so "
                         "nothing claimed it -- the same blind spot that hid the compute budget, "
                         "the CLI contract and the identity taxonomy"),
            "conditions": approved,
            "enforced": sum(1 for a in approved if a["status"] == "ENFORCED"),
            "total": len(approved),
            "broken": [a["id"] for a in approved if a["status"] != "ENFORCED"],
        },
        "not_a_pass_fail_gate": (
            "a referenced section is not a verified one, and an unclaimed section is not "
            "necessarily unimplemented. This is a worklist, and the prose-only decisions are "
            "listed by name so they cannot hide in a silent absence"),
        "sections": rows,
    }
    with writer.attempt("cross_phase.guide_section_coverage") as att:
        att.detail = {"unclaimed": len(unclaimed)}
    writer.write_config("guide_section_coverage.json", document)
    writer.write_json("guide_section_coverage.json", document, schema=document["schema"])

    print(f"guide subsections: {document['sections_total']}, "
          f"referenced {document['referenced']}, "
          f"prose-only {len(PROSE_ONLY)}, unclaimed {len(unclaimed)}")
    for row in unclaimed:
        print(f"  UNCLAIMED  {row['section']:<6} {row['title'][:70]}")
    conditions = document["approved_conditions"]
    print(f"guide 0.1 approved conditions enforced: {conditions['enforced']}/"
          f"{conditions['total']}  broken={conditions['broken'] or 'none'}")
    for entry in conditions["conditions"]:
        if entry["status"] != "ENFORCED":
            print(f"  BROKEN  {entry['id']:<8} {entry['pointer']} — {entry['detail'][:70]}")
    print(f"referenced but no test mentions them: "
          f"{document['referenced_but_no_test_mentions_it']}")
    print(f"evidence -> {writer.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
