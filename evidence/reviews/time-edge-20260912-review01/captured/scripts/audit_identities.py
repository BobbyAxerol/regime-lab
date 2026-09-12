#!/usr/bin/env python
"""Guide 13.1 — which research-record identities exist, and which are still owed.

Scans every committed artifact for each of the twelve identity names and writes
`configs/id_taxonomy.json`. Also demonstrates the three derivations added for
completed phases against REAL records, so "the identity can be derived" is a
measured claim rather than a function that exists.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.evidence.identities import (  # noqa: E402
    TAXONOMY,
    execution_id,
    observation_id,
    probe_design_id,
    taxonomy_status,
)
from crypto_regime_lab.evidence.manifest import EvidenceWriter  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"


#: Files that MENTION every identity because describing them is their job. Left
#: in the scan they make the audit pass on its own output -- the first run of
#: this script reported 12/12 purely because it had just written id_taxonomy.json.
SELF_REFERENTIAL = ("identities.py", "id_taxonomy.json", "audit_identities.py")


def scan(name: str) -> list[str]:
    """Where is this identity actually USED? Not: where is it talked about."""
    found = subprocess.run(
        ["grep", "-rl", f'"{name}"', "configs", "evidence", "src"],
        cwd=str(LAB_ROOT), capture_output=True, text=True).stdout.split()
    return sorted({p for p in found
                   if not any(marker in p for marker in SELF_REFERENTIAL)})[:6]


def demonstrate() -> dict:
    """Derive each newly added identity from a record that already exists."""
    out: dict = {}

    designs = json.loads((LAB_ROOT / "configs" / "lab04_probe_designs.json").read_text())
    baseline = json.loads((LAB_ROOT / "configs" / "lab04_calendar_baseline.json").read_text())
    budget = baseline["search_budget"]
    cell = next(c for c in baseline["cells"] if c["status"] == "RUN")
    out["probe_design_id"] = {
        "derived": probe_design_id(
            alpha_id=cell["alpha_id"], symbol=cell["symbol"],
            cutoff=baseline["calendar"]["first_cutoff"], seed=designs["seed"],
            anchors=budget["anchors"], probes_per_anchor=budget["probes_per_anchor"],
            radius=budget["radius"],
            space_filling_anchors=budget.get("space_filling_anchors", 0)),
        "from": "configs/lab04_probe_designs.json + lab04_calendar_baseline.json",
        "inputs": {"alpha_id": cell["alpha_id"], "symbol": cell["symbol"],
                   "seed": designs["seed"], "anchors": budget["anchors"]},
    }

    account = baseline["account_contract"]
    out["execution_id"] = {
        "derived": execution_id(
            candidate_id="incumbent_seed", symbol=cell["symbol"], interval="15m",
            start=baseline["calendar"]["first_cutoff"], end="2023-12-31",
            initial_state="flat_at_episode_start", economics=account, seed=designs["seed"]),
        "from": "configs/lab04_calendar_baseline.json account_contract",
        "economics_is_part_of_the_identity": True,
        "why": ("the same candidate over the same bars at a different fee is a different "
                "measurement; sharing an ID would let a cost-stress run be compared against a "
                "headline one as if they were the same thing"),
    }

    registry = json.loads((LAB_ROOT / "configs" / "lab05_regime_model_registry.json").read_text())
    tapes = sorted((LAB_ROOT / "evidence").rglob("emission_tape.json"))
    emission = None
    for tape in reversed(tapes):
        doc = json.loads(tape.read_text())
        if doc.get("emissions"):
            emission = doc["emissions"][0]
            break
    if emission is not None:
        out["observation_id"] = {
            "derived": observation_id(
                model_id=registry["models"][0]["model_id"],
                state_namespace=emission["state_namespace"],
                observed_at=emission["observed_at"],
                available_at=emission["available_at"]),
            "from": "an emission_tape.json record in evidence/",
            "inputs": {"state_namespace": emission["state_namespace"],
                       "observed_at": emission["observed_at"],
                       "available_at": emission["available_at"]},
        }
    return out


def main() -> int:
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    present = {name: scan(name) for name in TAXONOMY}
    with writer.attempt("identities.audit") as att:
        document = taxonomy_status(present)
        document["derivations_demonstrated"] = demonstrate()
        att.detail = {"present": document["present_count"], "total": document["total"]}

    document["owed_by_phase"] = sorted(
        {rec["owner"] for rec in document["identities"].values() if rec["status"] == "OWED"})
    document["derivable"] = sorted(
        n for n, rec in document["identities"].items() if rec["status"] == "DERIVABLE")
    document["note"] = (
        "an identity marked OWED is minted by a phase that has not run. The three that completed "
        "phases owed -- probe_design_id, execution_id, observation_id -- are DERIVED from records "
        "that already exist (see derivations_demonstrated) rather than back-filled into artifacts, "
        "so no measurement moves and no run is repeated")
    writer.write_config("id_taxonomy.json", document)
    writer.write_json("id_taxonomy.json", document, schema=document["schema"])

    for name, rec in document["identities"].items():
        mark = {"PRESENT": "PRESENT",
                "DERIVABLE": f"DERIVABLE (minted by {rec['owner']}, not yet a stored field)",
                "OWED": f"OWED by {rec['owner']}"}[rec["status"]]
        print(f"  {name:<18} {mark}")
    for name, rec in document["derivations_demonstrated"].items():
        print(f"  derived {name:<16} -> {rec['derived']}")
    print(f"{document['present_count']} present, {document['derivable_count']} derivable, "
          f"{document['owed_count']} owed of {document['total']}; "
          f"owed by {document['owed_by_phase']}")
    print(f"evidence -> {writer.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
