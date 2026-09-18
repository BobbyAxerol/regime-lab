#!/usr/bin/env python
"""LAB-02 L02.1 — catalog the four alphas, their presets and the semantic deltas.

Outputs: alpha_registry.json, preset_catalog.json, unmapped_presets.json,
semantic_delta.json. Everything is derived by static AST from the read-only
snapshots; no alpha is imported.
"""

from __future__ import annotations

import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.alphas.catalog import (  # noqa: E402
    classify_presets, inventory_file, unused_knobs,
)
from crypto_regime_lab.alphas.findings import FINDINGS, SEMANTIC_DELTAS  # noqa: E402
from crypto_regime_lab.evidence.manifest import EvidenceWriter  # noqa: E402
from crypto_regime_lab.safety.archive import ALLOWED_ALPHA_FILES  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy, sha256_file  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"
ADAPTERS = {
    "A-SC": "crypto_regime_lab.alphas.a_sc.SignalCombineAdapterV1",
    "A-HMA": "crypto_regime_lab.alphas.a_hma.AdaptiveHmaEventAdapterV1",
    "A-VWAP": "crypto_regime_lab.alphas.a_vwap.VwapMeanReversionEventAdapterV1",
    "A-HASH": "crypto_regime_lab.alphas.a_hash.HashMomentumEventAdapterV1",
}


def main() -> int:
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    policy.assert_lab_marker_ok(STUDY_ID)
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)
    raw = policy.lab_root / "vendor_readonly" / "alphas_raw"

    with writer.attempt("L02.1.inventory") as att:
        inventories = {}
        for filename, expected in ALLOWED_ALPHA_FILES.items():
            digest = sha256_file(raw / filename)
            if digest != expected:
                raise RuntimeError(f"{filename} digest drifted; refusing to catalog")
            inv = inventory_file(raw / filename, digest)
            inventories[inv.alpha_id] = inv
        att.detail = {"alphas": sorted(inventories)}

    catalog, unmapped = classify_presets(inventories)

    registry = {
        "schema": "crypto_regime_lab.alpha_registry.v1",
        "study_id": STUDY_ID,
        "method": "static AST of the read-only snapshots; no alpha module is imported or executed",
        "alphas": {},
    }
    for alpha_id, inv in inventories.items():
        source = (raw / inv.filename).read_text(encoding="utf-8")
        alpha_findings = [f.__dict__ for f in FINDINGS if f.alpha_id == alpha_id]
        deltas = [d.as_record() for d in SEMANTIC_DELTAS if d.alpha_id == alpha_id]
        registry["alphas"][alpha_id] = {
            **inv.as_record(),
            "adapter": ADAPTERS[alpha_id],
            "adapter_version": "canonical_v1",
            "version_tiers": {
                "raw_supplied": f"vendor_readonly/alphas_raw/{inv.filename}",
                "legacy_reproduction": "reference indicators tagged *_legacy plus the source harness",
                "canonical_v1": ADAPTERS[alpha_id],
                "research_revision_N": [d["delta_id"] for d in deltas
                                        if not d["applies_to_experiment_arms"]],
            },
            "unused_knobs": unused_knobs(inv, source),
            "finding_count": len(alpha_findings),
            "findings": alpha_findings,
            "semantic_delta_ids": [d["delta_id"] for d in deltas],
            "preset_count": sum(1 for p in catalog if p["declared_in_alpha"] == alpha_id),
            "unmapped_count": sum(1 for p in unmapped if p["declared_in_alpha"] == alpha_id),
        }

    preset_doc = {
        "schema": "crypto_regime_lab.preset_catalog.v1",
        "study_id": STUDY_ID,
        "classification_rule": (
            "a literal dictionary is a parameter preset for the alpha that declares it only when at "
            "least half of its keys are parameter names that alpha's own code reads; nothing is "
            "assigned by dictionary name or by shape"
        ),
        "quarantine": (
            "every preset is provenance=user_full_sample_tpe: retrospective reference only, never a "
            "warm start, never in the primary candidate bank, never an independent OOS claim"
        ),
        "count": len(catalog),
        "presets": catalog,
    }
    unmapped_doc = {
        "schema": "crypto_regime_lab.unmapped_presets.v1",
        "study_id": STUDY_ID,
        "rule": (
            "these dictionaries do not match the parameter schema of the alpha whose file declares "
            "them. They are NOT a fifth alpha and are never executed (guide 2.3); they are retained "
            "only so the audit trail is complete."
        ),
        "count": len(unmapped),
        "presets": unmapped,
    }
    delta_doc = {
        "schema": "crypto_regime_lab.semantic_delta.v1",
        "study_id": STUDY_ID,
        "change_kinds": ["packaging_fix", "execution_repair", "indicator_repair", "thesis_change"],
        "rule": (
            "a delta with an empty applies_to_experiment_arms is NOT part of any canonical arm; its "
            "effect may never be credited to regime work"
        ),
        "count": len(SEMANTIC_DELTAS),
        "deltas": [d.as_record() for d in SEMANTIC_DELTAS],
    }

    for name, doc in (("alpha_registry.json", registry), ("preset_catalog.json", preset_doc),
                      ("unmapped_presets.json", unmapped_doc), ("semantic_delta.json", delta_doc)):
        writer.write_config(name, doc)
        writer.write_json(name, doc, schema=doc["schema"])

    print(f"alphas catalogued   : {len(registry['alphas'])}")
    for alpha_id, rec in registry["alphas"].items():
        print(f"   {alpha_id:<8} fns={len(rec['functions']):<2} schema={len(rec['parameter_schema']):<3} "
              f"presets={rec['preset_count']:<3} unmapped={rec['unmapped_count']:<3} "
              f"findings={rec['finding_count']:<2} deltas={len(rec['semantic_delta_ids'])}")
    print(f"preset_catalog      : {len(catalog)}")
    print(f"unmapped_presets    : {len(unmapped)}")
    print(f"semantic_deltas     : {len(SEMANTIC_DELTAS)}")
    print(f"evidence -> {writer.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
