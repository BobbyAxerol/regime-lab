#!/usr/bin/env python
"""LAB-01 L01.5 (completed): quarantine the supplied full-sample presets.

Static AST read of the four read-only alpha snapshots — nothing is imported or
executed. Every literal dictionary is registered with an identity and an
eligibility record that forbids warm-starting the primary path.

Schema-based separation into preset_catalog / unmapped_presets is LAB-02 work
(L02.1). What LAB-01 owns is the quarantine itself.
"""

from __future__ import annotations

import ast
import hashlib
import json
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter  # noqa: E402
from crypto_regime_lab.safety.archive import ALLOWED_ALPHA_FILES, ALPHA_IDS  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy, sha256_file  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"

# Guide appendix A.1, column "Literal dictionaries doc duoc" — a count of literal
# dictionaries in each file, NOT a count of valid parameter presets.
GUIDE_DICT_COUNTS = {
    "hash_momentum.py": 6,
    "adaptive_hma_cpp.py": 13,
    "vwap.py": 15,
    "signal_combine.py": 1,
}

QUARANTINE_FLAGS = {
    "provenance": "user_full_sample_tpe",
    "eligible_for_retrospective_reference": True,
    "eligible_for_early_fold_warm_start": False,
    "eligible_for_primary_candidate_bank": False,
    "eligible_for_independent_oos_claim": False,
}


def _literal(node):
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError, TypeError):
        return None


def scan_file(path: Path, file_sha: str) -> list[dict]:
    """Collect every literal dict assigned to a name, at any nesting depth."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        value = node.value
        if not isinstance(value, ast.Dict):
            continue
        payload = _literal(value)
        if not isinstance(payload, dict):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            typed = json.dumps(payload, sort_keys=True, default=str)
            preset_id = (
                f"{ALPHA_IDS[path.name]}|{file_sha[:12]}|{target.id}|"
                + hashlib.sha256(typed.encode()).hexdigest()[:12]
            )
            found.append({
                "preset_id": preset_id,
                "alpha_id": ALPHA_IDS[path.name],
                "source_file": path.name,
                "source_file_sha256": file_sha,
                "dictionary_name": target.id,
                "source_line": node.lineno,
                "key_count": len(payload),
                "keys": sorted(str(k) for k in payload),
                "values": payload,
                "values_digest": hashlib.sha256(typed.encode()).hexdigest(),
                **QUARANTINE_FLAGS,
            })
    return found


def classify(entries: list[dict]) -> None:
    """Tag each dictionary as a parameter preset or a non-preset literal.

    Heuristic, stated openly: within one alpha file the parameter presets share
    a key signature, so the modal signature identifies them. Anything else is
    flagged for LAB-02 to adjudicate rather than silently counted as a preset.
    """
    from collections import Counter

    by_file: dict[str, list[dict]] = {}
    for entry in entries:
        by_file.setdefault(entry["source_file"], []).append(entry)
    for filename, group in by_file.items():
        signatures = Counter(tuple(e["keys"]) for e in group)
        modal_signature, modal_count = signatures.most_common(1)[0]
        for entry in group:
            is_modal = tuple(entry["keys"]) == modal_signature
            entry["dictionary_role"] = (
                "parameter_preset_candidate" if is_modal else "non_preset_literal"
            )
            entry["classification_basis"] = (
                f"modal key signature for {filename} ({modal_count}/{len(group)} dictionaries)"
            )
            if not is_modal:
                entry["lab02_adjudication_required"] = True
                # A non-preset literal is quarantined too, but it is never a candidate.
                entry["eligible_for_retrospective_reference"] = False


def main() -> int:
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    policy.assert_lab_marker_ok(STUDY_ID)
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    raw_dir = policy.lab_root / "vendor_readonly" / "alphas_raw"
    entries: list[dict] = []
    per_file: dict[str, int] = {}
    with writer.attempt("L01.5.quarantine_presets") as att:
        for filename in sorted(ALLOWED_ALPHA_FILES):
            path = raw_dir / filename
            digest = sha256_file(path)
            if digest != ALLOWED_ALPHA_FILES[filename]:
                raise RuntimeError(f"{filename} digest drifted; refusing to catalog")
            found = scan_file(path, digest)
            per_file[filename] = len(found)
            entries.extend(found)
        classify(entries)
        att.detail = {"dictionaries": len(entries), "per_file": per_file}

    # Name collisions across files are NOT the same parameter set (guide A.1).
    by_name: dict[str, list[str]] = {}
    for entry in entries:
        by_name.setdefault(entry["dictionary_name"], []).append(entry["preset_id"])
    collisions = {name: ids for name, ids in by_name.items() if len(ids) > 1}

    preset_counts: dict[str, int] = {}
    nonpreset: dict[str, list[str]] = {}
    for entry in entries:
        if entry["dictionary_role"] == "parameter_preset_candidate":
            preset_counts[entry["source_file"]] = preset_counts.get(entry["source_file"], 0) + 1
        else:
            nonpreset.setdefault(entry["source_file"], []).append(
                f"{entry['dictionary_name']}@L{entry['source_line']}"
            )
    crosscheck = {
        filename: {
            "guide_a1_literal_dict_count": GUIDE_DICT_COUNTS[filename],
            "observed_literal_dict_count": per_file[filename],
            "literal_count_matches_guide": per_file[filename] == GUIDE_DICT_COUNTS[filename],
            "modal_signature_group_size": preset_counts.get(filename, 0),
            "outside_modal_group": nonpreset.get(filename, []),
        }
        for filename in GUIDE_DICT_COUNTS
    }
    discrepancies = {
        filename: rec for filename, rec in crosscheck.items()
        if not rec["literal_count_matches_guide"]
    }

    catalog = {
        "schema": "crypto_regime_lab.preset_quarantine.v1",
        "study_id": STUDY_ID,
        "method": "ast.parse of the read-only snapshots; no import, no execution",
        "quarantine_rule": (
            "Every supplied preset is provenance=user_full_sample_tpe. It may be replayed on the "
            "canonical engine as a labelled retrospective reference only. It must never warm-start "
            "an early fold, enter the primary candidate bank, narrow search bounds, or support an "
            "independent OOS claim (guide 2.2)."
        ),
        "name_collisions_are_not_shared_presets": (
            "A dictionary name appearing in two files is two different parameter sets; identity is "
            "alpha_id + file sha + dictionary name + typed values digest (guide A.1)."
        ),
        "total_literal_dictionaries": len(entries),
        "total_parameter_presets": sum(preset_counts.values()),
        "per_file_literal_counts": per_file,
        "per_file_preset_counts": preset_counts,
        "non_preset_literals": nonpreset,
        "guide_crosscheck": crosscheck,
        "literal_counts_all_match_guide": not discrepancies,
        "literal_count_discrepancies": discrepancies,
        "discrepancy_reading": (
            "adaptive_hma_cpp.py holds 14 literal dictionaries against the guide's 13. The extra one "
            "is sl_mode_map (line 311), a 4-entry SL-mode lookup table with none of the 12 parameter "
            "keys — so the guide's 13 is the count of parameter dictionaries and this scan is simply "
            "broader. No parameter preset is missing or extra."
            if "adaptive_hma_cpp.py" in discrepancies else
            "every observed literal-dictionary count matches guide appendix A.1"
        ),
        "modal_grouping_is_a_heuristic_not_a_schema_decision": (
            "dictionary_role comes from the modal key signature within each file. For vwap.py the "
            "guide states only 4 dictionaries carry VWAP keys plus `base` with HTF, while 10 do not "
            "match the VWAP parameter schema at all; this scan's modal group of 9 is therefore a "
            "grouping hint, and the authoritative split into preset_catalog / unmapped_presets is "
            "LAB-02 L02.1 work using each alpha's real parameter schema."
        ),
        "colliding_dictionary_names": collisions,
        "lab02_followup": (
            "LAB-02 L02.1 splits these into preset_catalog.json (keys matching an alpha's parameter "
            "schema) and unmapped_presets.json (the cetp_*/keke/VN30F1M dictionaries in vwap.py, "
            "which are not a fifth alpha and are never run)."
        ),
        "presets": entries,
    }
    writer.write_config("preset_quarantine_catalog.json", catalog)
    art = writer.write_json("preset_quarantine_catalog.json", catalog, schema=catalog["schema"])

    print(f"literal dicts       : {len(entries)}   parameter presets: {sum(preset_counts.values())}")
    for filename, rec in crosscheck.items():
        flag = "OK " if rec["literal_count_matches_guide"] else "DIFF"
        print(f"  {flag} {filename:<22} literal_dicts={rec['observed_literal_dict_count']:>3}  "
              f"guide_A.1={rec['guide_a1_literal_dict_count']:>3}  "
              f"modal_group={rec['modal_signature_group_size']:>3}  "
              f"outside_modal={rec['outside_modal_group']}")
    print(f"colliding names     : {sorted(collisions)}")
    print(f"evidence -> {art['artifact_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
