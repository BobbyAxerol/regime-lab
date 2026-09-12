#!/usr/bin/env python
"""LAB-02 exit — alpha certification records, golden traces and the domain gate.

Every alpha ends with either READY_FOR_RESEARCH or a SPECIFIC blocker. An alpha
that is not ready keeps its place in the 20-cell matrix with null metrics; it is
never swapped for another alpha and never dropped from the denominator.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.alphas.contracts import AlphaCertification  # noqa: E402
from crypto_regime_lab.alphas.findings import SEMANTIC_DELTAS  # noqa: E402
from crypto_regime_lab.alphas.fixtures import run_all_fixtures  # noqa: E402
from crypto_regime_lab.alphas.golden import golden_trace  # noqa: E402
from crypto_regime_lab.alphas.probes import run_all_probes  # noqa: E402
from crypto_regime_lab.alphas.legacy import divergence_report  # noqa: E402
from crypto_regime_lab.alphas.reference.numba_parity import numba_parity  # noqa: E402
from crypto_regime_lab.alphas.reference.parity import parity_report  # noqa: E402
from crypto_regime_lab.evidence.manifest import EvidenceWriter  # noqa: E402
from crypto_regime_lab.quantbt_bridge.capability_probe import capability_matrix  # noqa: E402
from crypto_regime_lab.quantbt_bridge.intent_tape import contract_snapshot  # noqa: E402
from crypto_regime_lab.quantbt_bridge.parity import parity_report as engine_parity  # noqa: E402
from crypto_regime_lab.safety.archive import ALLOWED_ALPHA_FILES, ALPHA_IDS  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"
FILE_FOR = {v: k for k, v in ALPHA_IDS.items()}

INDICATOR_CONVENTION = {
    "A-SC": "ta.AverageTrueRange + ta.MFIIndicator (or RSIIndicator when volume is declared absent); "
            "the library is authoritative because the alpha calls it directly",
    "A-HMA": "true range smoothed by an EMA (2/(n+1)), NOT Wilder; RSI flat case repaired to 50 "
             "(SD-HMA-03); dynamic Hull MA with the source's index clamping preserved",
    "A-VWAP": "session VWAP on hlc3 with a UTC daily reset; Wilder-style RSI and ATR seeded by an "
              "SMA, exactly as this file defines them",
    "A-HASH": "the 'ATR' is the absolute close-to-close move (AH-02), preserved as the legacy "
              "convention; a true-range variant exists as a separate research revision",
}
PARTIAL_QUANTITY_CONVENTION = {
    "A-SC": "not applicable (long-flat, single exit)",
    "A-HMA": "not applicable (single bracket)",
    "A-VWAP": "not applicable (single bracket)",
    "A-HASH": "fraction_of_remaining",
}


def main() -> int:
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    policy.assert_lab_marker_ok(STUDY_ID)
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)
    warnings.simplefilter("ignore")

    with writer.attempt("L02.1.probes") as att:
        probes = run_all_probes(policy.lab_root)
        att.detail = {"confirmed": probes["confirmed_count"], "total": probes["probe_count"]}
    writer.write_json("appendix_b_probes.json", probes, schema="crypto_regime_lab.probes.v1")

    with writer.attempt("L02.2.reference_parity") as att:
        parity = parity_report(policy.lab_root / "vendor_readonly" / "alphas_raw")
        att.detail = {"status": parity["status"], "failures": parity["failures"]}
    writer.write_json("reference_parity.json", parity, schema=parity["schema"])

    with writer.attempt("L02.2.numba_parity") as att:
        nparity = numba_parity(policy.lab_root / "vendor_readonly" / "alphas_raw")
        att.detail = {"status": nparity["status"], "kernels": nparity["kernel_count"],
                      "decision_failures": nparity["decision_failures"]}
    writer.write_json("numba_parity.json", nparity, schema=nparity["schema"])

    divergences: dict[str, dict] = {}
    with writer.attempt("L02.8.legacy_divergence") as att:
        for alpha_id in ("A-SC", "A-HMA", "A-VWAP", "A-HASH"):
            divergences[alpha_id] = divergence_report(
                alpha_id, policy.lab_root / "vendor_readonly" / "alphas_raw")
            writer.write_json(f"legacy_divergence/{alpha_id}.json", divergences[alpha_id],
                              schema=divergences[alpha_id]["schema"])
        att.detail = {a: d["attribution"]["kind"] for a, d in divergences.items()}

    with writer.attempt("L02.7.execution_fixtures") as att:
        fixtures = run_all_fixtures()
        att.detail = {"passed": fixtures["passed"], "total": fixtures["fixture_count"]}
    writer.write_json("execution_fixtures.json", fixtures, schema=fixtures["schema"])

    with writer.attempt("L02.7.capability_matrix") as att:
        caps = capability_matrix()
        att.detail = {"blocked": caps["blocked_capabilities"],
                      "hash_ladder": caps["a_hash_ladder_route"]["status"]}
    writer.write_json("engine_capability_matrix.json", caps, schema=caps["schema"])

    with writer.attempt("L02.8.engine_parity") as att:
        eparity = engine_parity()
        att.detail = {"status": eparity["status"], "failures": eparity["account_trace_failures"]}
    writer.write_json("engine_parity.json", eparity, schema=eparity["schema"])

    goldens: dict[str, dict] = {}
    with writer.attempt("L02.certification.golden_traces") as att:
        for alpha_id in ("A-SC", "A-HMA", "A-VWAP", "A-HASH"):
            goldens[alpha_id] = golden_trace(alpha_id)
            writer.write_json(f"golden_traces/{alpha_id}.json", goldens[alpha_id],
                              schema="crypto_regime_lab.golden_trace.v1")
        att.detail = {"alphas": sorted(goldens), "digests": {k: v["golden_digest"][:12]
                                                            for k, v in goldens.items()}}

    verified_caps = [cap for cap, rec in caps["by_capability"].items() if rec["supported"]]
    hash_blocked = caps["a_hash_ladder_route"]["status"] == "BLOCKED_CAPABILITY"
    unexplained = [a for a, d in divergences.items() if not d["attribution"]["explained"]]
    suites_ok = (probes["confirmed_count"] == probes["probe_count"]
                 and parity["status"] == "PASS"
                 and nparity["status"] == "PASS"
                 and fixtures["status"] == "PASS"
                 and eparity["status"] == "PASS"
                 and not unexplained)

    certifications = {}
    for alpha_id in ("A-SC", "A-HMA", "A-VWAP", "A-HASH"):
        blockers: list[str] = []
        if not suites_ok:
            blockers.append("a shared suite (probes / parity / numba / fixtures / divergence) "
                            "did not pass")
        if alpha_id == "A-HASH" and hash_blocked:
            blockers.append(
                "BLOCKED_CAPABILITY: the canonical three-rung partial ladder needs a next-open "
                "entry, a protective stop and partial reduce-only exits on ONE route. "
                "intrabar_bracket_v1 provides the first two but a single take-profit level; the "
                "orders route provides the ladder but fills the entry at the stamped bar's close "
                "and rejects stop_market. Measured, not assumed."
            )
        golden = goldens[alpha_id]
        cert = AlphaCertification(
            alpha_id=alpha_id,
            raw_source_digest=ALLOWED_ALPHA_FILES[FILE_FOR[alpha_id]],
            adapter_version="canonical_v1",
            status="READY_FOR_RESEARCH" if not blockers else "NOT_READY_SPECIFIC_BLOCKER",
            indicator_convention=INDICATOR_CONVENTION[alpha_id],
            timing_contract=contract_snapshot()["engine_id"],
            partial_quantity_convention=PARTIAL_QUANTITY_CONVENTION[alpha_id],
            engine_capabilities_verified=tuple(verified_caps),
            semantic_delta_refs=tuple(d.delta_id for d in SEMANTIC_DELTAS if d.alpha_id == alpha_id),
            golden_trace_refs=(f"golden_traces/{alpha_id}.json#{golden['golden_digest'][:16]}",),
            market_test_evidence_refs=(),
            blockers=tuple(blockers),
        )
        record = cert.as_record()
        record["market_test_evidence_note"] = (
            "empty by design: LAB-02 runs synthetic fixtures only. Market qualification is LAB-03."
        )
        record["legacy_divergence"] = {
            "kind": divergences[alpha_id]["attribution"]["kind"],
            "explained": divergences[alpha_id]["attribution"]["explained"],
            "attributed_to": (divergences[alpha_id]["attribution"].get("attributed_delta")
                              or divergences[alpha_id]["attribution"].get("attributed_blocker")),
            "artifact": f"legacy_divergence/{alpha_id}.json",
        }
        record["version_tiers_built"] = ["raw_supplied", "legacy_reproduction", "canonical_v1"]
        record["synthetic_suite"] = {
            "decisions": golden["decision_count"], "entries": golden["entries"],
            "technical_exits": golden["technical_exits"],
            "engine_fills": len(golden["engine_fills"]),
            "warmup_blocked_bars": golden["warmup_blocked_bars"],
        }
        if alpha_id == "A-HASH":
            record["declared_reduced_fidelity_variant"] = {
                "variant_id": "A-HASH-single-tp-v1",
                "definition": "the ladder collapsed to its FINAL rung only, executed on "
                              "intrabar_bracket_v1 with a next-open entry and a protective stop",
                "status": "AVAILABLE_BUT_NOT_THE_CANONICAL_ALPHA",
                "rule": "results from this variant are labelled and may never be reported as the "
                        "canonical A-HASH; the partial-exit thesis is not being tested by it",
            }
        certifications[alpha_id] = record
        writer.write_json(f"alpha_certification/{alpha_id}.json", record,
                          schema=record["schema"])
        writer.write_config(f"alpha_certification/{alpha_id}.json", record)

    ready = [a for a, r in certifications.items() if r["status"] == "READY_FOR_RESEARCH"]
    summary = {
        "schema": "crypto_regime_lab.lab02_certification_summary.v1",
        "study_id": STUDY_ID,
        "engine_contract": contract_snapshot(),
        "suites": {
            "appendix_b_probes": f"{probes['confirmed_count']}/{probes['probe_count']} CONFIRMED",
            "reference_parity": parity["status"],
            "numba_fastmath_parity": (f"{nparity['status']} "
                                      f"({nparity['kernel_count']} kernels, "
                                      f"{len(nparity['decision_failures'])} decision differences)"),
            "legacy_divergence": ("all explained" if not unexplained
                                  else f"UNEXPLAINED: {unexplained}"),
            "execution_fixtures": f"{fixtures['passed']}/{fixtures['fixture_count']} {fixtures['status']}",
            "engine_parity": eparity["status"],
            "fill_trace_parity": eparity["fill_trace_parity"]["status"],
        },
        "certifications": {a: {"status": r["status"], "blockers": r["blockers"]}
                           for a, r in certifications.items()},
        "ready_for_research": ready,
        "not_ready": [a for a in certifications if a not in ready],
        "matrix_rule": (
            "an alpha that is not ready keeps all five of its cells in the 20-cell matrix with null "
            "metrics and a reason; it is never replaced by another alpha and never removed from the "
            "denominator of any conclusion"
        ),
        "market_optimization_allowed_for": ready,
        "exit": "PASS" if suites_ok else "FAIL",
    }
    writer.write_json("lab02_certification_summary.json", summary, schema=summary["schema"])
    writer.write_config("lab02_certification_summary.json", summary)

    print(f"probes            : {summary['suites']['appendix_b_probes']}")
    print(f"reference parity  : {summary['suites']['reference_parity']}")
    print(f"numba parity      : {summary['suites']['numba_fastmath_parity']}")
    print(f"legacy divergence : {summary['suites']['legacy_divergence']}")
    for alpha_id, d in divergences.items():
        print(f"   {alpha_id:<8} {d['attribution']['kind']}")
    print(f"execution fixtures: {summary['suites']['execution_fixtures']}")
    print(f"engine parity     : {summary['suites']['engine_parity']} "
          f"(fill trace: {summary['suites']['fill_trace_parity']})")
    print("certifications:")
    for alpha_id, rec in certifications.items():
        print(f"   {alpha_id:<8} {rec['status']}")
        for b in rec["blockers"]:
            print(f"            blocker: {b[:150]}")
    print(f"exit              : {summary['exit']}")
    print(f"evidence -> {writer.run_dir}")
    return 0 if summary["exit"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
