#!/usr/bin/env python
"""RF-01 — freeze scope, invalidate false claims, inventory the Mode 4 binding.

Reads the merged corrective plan, the recovered audit bundle, the installed
candidate source and the live environment. Writes only inside LAB_ROOT via the
lab EvidenceWriter, under evidence/corrective_mode4_v3/RF-01/. Historical
evidence is never edited: this phase creates a separate invalidation manifest
and a new study spec, and quarantines the old E arm as not implemented.

Nothing here runs a market experiment. Exit status of the phase is
TECHNICAL_ONLY (plan section RF-01: no edge inference at this phase).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.evidence.manifest import (  # noqa: E402
    EvidenceWriter, environment_fingerprint, utc_now_iso,
)
from crypto_regime_lab.quantbt_bridge.capabilities import InstalledQuantBT  # noqa: E402
from crypto_regime_lab.safety.checks import run_all  # noqa: E402
from crypto_regime_lab.safety.paths import (  # noqa: E402
    SafetyViolation, SandboxPolicy, manifest_directory, sha256_file,
)

PLAN = LAB_ROOT / "REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md"
PLAN_SHA256 = "bf983c2b63dd748d778a3d9c38360bfb6f081cb9b445d7a8044fbae63b2c7434"
AUDIT_ARCHIVE_SHA256 = "2765bd069a5caf16921c3df03dfafd8f090f4fdd2de5e1550a5ce390c87a980f"
STUDY_ID = "corrective_mode4_v3"
PHASE = "RF-01"
CANDIDATE = LAB_ROOT / "quantbt_candidate"
QC = CANDIDATE / "quantbt"

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT")
RUN_ALPHAS = ("A-HMA", "A-SC", "A-VWAP")
ALL_CELLS = tuple(f"{a}/{s}" for a in ("A-HMA", "A-SC", "A-VWAP", "A-HASH") for s in SYMBOLS)
RUN_CELLS = tuple(f"{a}/{s}" for a in RUN_ALPHAS for s in SYMBOLS)


def git(*args: str) -> str:
    out = subprocess.run(["git", "-C", str(LAB_ROOT), *args],
                         capture_output=True, text=True, check=False)
    return out.stdout.strip()


def protected_write_probes(policy: SandboxPolicy) -> list[dict]:
    targets = [
        "../quantbt/README.md",
        "../alphas_storage/_get_data/data_loader.py",
        "../alphas_storage/alpha_to_tes_regime_model/vwap.py",
    ]
    records = []
    for relative in targets:
        target = (LAB_ROOT / relative).resolve()
        try:
            policy.resolve_write_target(target)
            records.append({"target": str(target), "refused": False,
                            "reason": "WRITE WAS ALLOWED — sandbox boundary is broken"})
        except SafetyViolation as exc:
            records.append({"target": str(target), "refused": True, "reason": str(exc)})
    return records


def source_manifest() -> dict:
    roots = {
        "src": (LAB_ROOT / "src", ("*.py",)),
        "scripts": (LAB_ROOT / "scripts", ("*.py",)),
        "tests": (LAB_ROOT / "tests", ("*.py",)),
        "configs": (LAB_ROOT / "configs", ("*.json",)),
        "candidate_quantbt": (QC, ("*.py",)),
    }
    manifest: dict[str, dict[str, str]] = {}
    for name, (root, patterns) in roots.items():
        manifest[name] = manifest_directory(root, patterns) if root.is_dir() else {}
    return manifest


VFY_CHECKS = [
    {
        "id": "VFY01", "file": "endpoint.py",
        "patterns": [r"def pct_equity", r"def signal_notional",
                     r"_run_pct_equity_transition_native"],
        "claim": "pct_equity() builds a legacy factory; the native transition route is opt-in",
        "consequence": "factory name alone does not prove Rust/native routing",
    },
    {
        "id": "VFY02", "files": ["endpoint.py", "walkforward.py"],
        "patterns": [r"mode_4_is_only_robust", r"per_fold_causal", r"is_only_robust"],
        "claim": "walk_forward supports Mode 4 + per_fold_causal + endpoint scoring",
        "consequence": "the corrective study must call this pipeline or reuse its instances/hooks",
    },
    {
        "id": "VFY03", "file": "walkforward.py",
        "patterns": [r"def _run_per_fold_schedule", r"evaluate_oos_candidates=schedule == \"per_fold_decay\""],
        "claim": "per_fold_causal calls optimize_params with evaluate_oos_candidates=False",
        "consequence": "Mode 4 causal selection must freeze before outer OOS; post-selection scoring is reporting only",
    },
    {
        "id": "VFY04", "file": "endpoint.py",
        "patterns": [r"native_prepared_wfo", r"native_prepared_wfo='require' is not available"],
        "claim": "native prepared WFO defaults off; 'require' has an explicit availability gate",
        "consequence": "Rust routing must be qualified, never asserted from metadata",
    },
    {
        "id": "VFY05", "files": ["preparation/native_target_requests.py", "preparation/native_execution.py"],
        "patterns": [r"close_target_v2_same_close"],
        "claim": "the prepared public scorer uses a same-close timing contract",
        "consequence": "it is not next-open execution; a shifted series does not change close into open",
    },
    {
        "id": "VFY06", "file": "endpoint.py",
        "patterns": [r"return self\.fee / 2\.0 if self\.fee_rate is None",
                     r"rust pct_equity_transition requires fee_rate to equal legacy fee / 2"],
        "claim": "legacy fee is a round-trip rate halved at the boundary; rust pct_equity requires fee_rate == fee/2",
        "consequence": "bind the one-way rate per route and verify with golden fills (A01/COR-13)",
    },
    {
        "id": "VFY07", "file": "metrics/performance.py",
        "patterns": [r"def profit_factor", r"_array_profit_factor\(stats_returns\)", r"stats_returns"],
        "claim": "the package profit factor is computed on stats_returns, not a trade ledger",
        "consequence": "keep the raw metric and label it; trade PF is a separate definition",
    },
    {
        "id": "VFY08", "file": "walkforward.py",
        "patterns": [r"candidate_decay_lambda", r"candidate_decay_gamma"],
        "claim": "outer Mode 4 candidate_decay is an IS-OOS selection metric with optional penalties",
        "consequence": "keep raw and penalized fields separate; decay has three distinct definitions (D1/D2/D3)",
    },
    {
        "id": "VFY09", "file": "walkforward.py",
        "patterns": [r"def build_folds"],
        "claim": "build_folds supports calendar frequencies and has no universal regime keyword",
        "consequence": "a dynamic schedule needs a thin lab-only fold provider around the engine, not an invented API",
    },
    {
        "id": "VFY10", "file": "endpoint.py",
        "patterns": [r"def prepare_reactive_walk_forward", r"reset-flat account per fold"],
        "claim": "prepare_reactive_walk_forward is certified for a reset-flat account per fold",
        "consequence": "its output cannot be reported as one carried live account",
    },
    {
        "id": "VFY11", "file": "backends/native_wfo_public.py",
        "patterns": [r'"turnover": float\(result\.report_trade_count',
                     r'"mean_return": float\(result\.total_return',
                     r'"volatility": 0\.0'],
        "claim": "prepared scorer aliases: turnover=report trade count, mean_return=total return, volatility=0 placeholder",
        "consequence": "observer fields are not measured economic metrics; map units explicitly",
    },
]


def binding_report() -> dict:
    checks = []
    for spec in VFY_CHECKS:
        files = spec.get("files") or [spec["file"]]
        matches: list[dict] = []
        for name in files:
            path = QC / name
            text = path.read_text(encoding="utf-8")
            for pattern in spec["patterns"]:
                for hit in re.finditer(pattern, text):
                    line = text.count("\n", 0, hit.start()) + 1
                    matches.append({"file": name, "line": line, "pattern": pattern,
                                    "file_sha256": sha256_file(path)})
        checks.append({
            "id": spec["id"],
            "claim": spec["claim"],
            "consequence": spec["consequence"],
            "files": files,
            "present": bool(matches),
            "matches": matches,
            "status": "VERIFIED_PRESENT_ON_CANDIDATE" if matches else "NOT_FOUND",
        })
    return {
        "candidate_root": str(CANDIDATE.relative_to(LAB_ROOT)),
        "candidate_endpoint_sha256": sha256_file(QC / "endpoint.py"),
        "candidate_walkforward_sha256": sha256_file(QC / "walkforward.py"),
        "installed_quantbt": InstalledQuantBT.load().identity(),
        "checks": checks,
        "checks_total": len(checks),
        "checks_present": sum(1 for c in checks if c["present"]),
        "rule": ("every VFY claim is re-verified against the candidate copy in this lab. "
                 "The merged plan is a guide, not the measurement."),
    }


def finding_catalog() -> list[dict]:
    return [
        {"id": "A01", "severity": "P0", "title": "fee charged one half of the registered one-way rate",
         "phases": ["LAB-04", "LAB-05", "LAB-06", "LAB-07", "LAB-08", "LAB-09"],
         "arms": ["A", "B", "C", "D", "E"], "cells": list(ALL_CELLS),
         "claims": ["SELECTION", "TIMING", "all account-return magnitudes"],
         "evidence": ["probe P01", "SRC12", "SRC13", "configs/cost_binding_verification.json"],
         "reason": "every candidate was scored and every account charged under 0.0002 instead of 0.0004; "
                   "the fee probe changed 1/12 A-SC/BTC arm selections, so this is a design defect, not accounting only."},
        {"id": "A02", "severity": "P0", "title": "first future-selected version active from bar 0",
         "phases": ["LAB-07", "LAB-08", "LAB-09"], "arms": ["C", "D", "E"], "cells": list(RUN_CELLS),
         "claims": ["TIMING", "POLICY", "activation-delay attribution"],
         "evidence": ["probe P02", "probe P12", "SRC01", "SRC02"],
         "reason": "the schedule's first selection is installed at bar 0 without waiting for its requested/ready bar; "
                   "confirmation first dynamic cutoffs were 8..64 hours after account start."},
        {"id": "A03", "severity": "P0", "title": "non-converged / unmapped candidates still scored and confirmed",
         "phases": ["LAB-04", "LAB-08", "LAB-09"], "arms": ["A", "B", "C", "D", "E"],
         "cells": list(RUN_CELLS) + ["A-VWAP/BTCUSDT(C,D,E)", "A-VWAP/ETHUSDT(A)", "A-VWAP/SOLUSDT(C)"],
         "claims": ["SELECTION", "TIMING", "POLICY"],
         "evidence": ["probe P06", "probe P07", "SRC14", "SRC16"],
         "reason": "convergence compared exit bar sets only (price/qty/reason/sequence ignored) and "
                   "_evaluate returned EVALUATED on unmapped intents; 7 development and 5 confirmation arm-cells were non-converged."},
        {"id": "A04", "severity": "P0", "title": "adapter fed fabricated fills; corrective exits and amendments lost",
         "phases": ["LAB-04", "LAB-05", "LAB-06", "LAB-07", "LAB-08", "LAB-09"],
         "arms": ["A", "B", "C", "D", "E"], "cells": list(ALL_CELLS),
         "claims": ["SELECTION", "TIMING", "POLICY", "execution validity"],
         "evidence": ["probe P11", "SRC03", "SRC13", "SRC14", "SRC21", "SRC22"],
         "reason": "on_fill was called with raw next-open predictions before the engine confirmed; HMA corrective EXIT_ALL "
                   "follow-ups and VWAP AMEND_PROTECTION were dropped or recorded unmapped while still scored."},
        {"id": "A05", "severity": "P0", "title": "HMA stop-mode choices collapse to one effective mode",
         "phases": ["LAB-04", "LAB-08", "LAB-09"], "arms": ["A", "B", "C", "D", "E"],
         "cells": [f"A-HMA/{s}" for s in SYMBOLS],
         "claims": ["DESCRIPTIVE stop-mode family", "A-HMA SELECTION"],
         "evidence": ["probe P05", "SRC18", "SRC19", "SRC20"],
         "reason": "schema choices are Half Distance Zone / Zone Distance / ATR but the adapter accepts only "
                   "One Distance Zone / Half Distance Zone / Last High/Low / ATR Only and defaults unknown names to mode 1; "
                   "all three searched choices map to the same mode."},
        {"id": "A06", "severity": "P0", "title": "decision frame used as protection execution instead of 1m",
         "phases": ["LAB-04", "LAB-05", "LAB-06", "LAB-07", "LAB-08", "LAB-09"],
         "arms": ["A", "B", "C", "D", "E"], "cells": [f"A-HMA/{s}" for s in SYMBOLS] + [f"A-VWAP/{s}" for s in SYMBOLS],
         "claims": ["absolute protective-fill levels", "TIMING (intrabar bias may differ by parameter set)"],
         "evidence": ["OP-19", "SRC13", "SRC14", "configs/protective_order_fidelity.json"],
         "reason": "the protocol declares 1m execution; protective orders resolved on the 15m/1h decision bar. "
                   "Sharing the approximation across arms does not guarantee the comparative effect is unchanged."},
        {"id": "A07", "severity": "P0", "title": "block utility drops PnL at the first observation of a block",
         "phases": ["LAB-04", "LAB-06", "LAB-08", "LAB-09"], "arms": ["A", "B"], "cells": list(RUN_CELLS),
         "claims": ["SELECTION", "response utility", "decay magnitudes"],
         "evidence": ["probe P08", "SRC15"],
         "reason": "net_return=(segment[-1]-segment[0])/capital ignores the move from the observation before lo to lo; "
                   "a partition can lose money while every block reports zero."},
        {"id": "A08", "severity": "P0", "title": "arm A was not the public Mode 4 WFO baseline",
         "phases": ["LAB-04", "LAB-05", "LAB-06", "LAB-07", "LAB-08", "LAB-09"], "arms": ["A"], "cells": list(RUN_CELLS),
         "claims": ["SELECTION baseline", "TIMING"],
         "evidence": ["SRC17", "configs/lab04_selector_counterexamples.json"],
         "reason": "the custom calendar loop filled mean_is_sharpe with a non-Sharpe utility and used a default selector "
                   "instead of the public mode_4_is_only_robust / per_fold_causal path."},
        {"id": "A09", "severity": "P0", "title": "arm E was a copy of arm D's schedule",
         "phases": ["LAB-08", "LAB-09"], "arms": ["E"], "cells": list(RUN_CELLS),
         "claims": ["POLICY"],
         "evidence": ["SRC05", "configs/lab08_factorial_full.json", "configs/lab09_confirmation_results.json"],
         "reason": "the runner assigned E the same selections as D; E and D share a daily path in 15/15 development "
                   "and 15/15 confirmation cells. This is null by construction, not a measured conditional-policy null."},
        {"id": "A10", "severity": "P0", "title": "scheduler treated a model namespace change as a market change",
         "phases": ["LAB-08", "LAB-09"], "arms": ["C", "D", "E"], "cells": list(RUN_CELLS),
         "claims": ["TIMING", "POLICY"],
         "evidence": ["probe P03", "SRC04", "SRC25", "configs/trigger_eligibility_audit.json"],
         "reason": "state identity included the namespace, so refits triggered transitions even when the semantic state "
                   "did not change; decision_eligible/quality_status were not filtered."},
        {"id": "A11", "severity": "P0", "title": "response similarity used squared fit residual as market context",
         "phases": ["LAB-06", "LAB-08", "LAB-09"],
         "arms": ["policy"], "cells": ["A-SC/BTCUSDT"],
         "claims": ["PREDICTIVE", "POLICY"],
         "evidence": ["probe P04", "SRC06", "SRC07", "SRC10"],
         "reason": "0.5*w*(z-mu_selected)^2 preserves neither sign nor state; opposite trends at opposite centroids "
                   "have zero residual distance and are treated as the same context."},
        {"id": "A12", "severity": "P1", "title": "response study lacked support and was not wired to deployment",
         "phases": ["LAB-06", "LAB-08", "LAB-09"],
         "arms": ["policy"], "cells": ["A-SC/BTCUSDT"],
         "claims": ["PREDICTIVE", "POLICY"],
         "evidence": ["SRC08", "SRC09", "SRC10", "configs/lab09_policy_decision_ledger.json"],
         "reason": "one cell only; weekly reset-flat episodes without warmup; empty campaign book; contiguous-block "
                   "support counted weight fragments rather than time dependence; projected turnover=1 against a 0.1 allocation."},
        {"id": "A13", "severity": "P1", "title": "candidate bank had no conditional-specialist admission",
         "phases": ["LAB-06", "LAB-08", "LAB-09"],
         "arms": ["policy"], "cells": ["A-SC/BTCUSDT"],
         "claims": ["POLICY", "bank composition"],
         "evidence": ["SRC06", "SRC11", "configs/lab06_bank_registry.json"],
         "reason": "global robust-score ranking plus parameter-distance dedupe only; specialist_note() was a description, "
                   "not admission logic, and parameter diversity is not behavioral diversity."},
        {"id": "A14", "severity": "P1", "title": "model ladder/ablation did not prove decision value",
         "phases": ["LAB-03", "LAB-05", "LAB-08", "LAB-09"],
         "arms": ["C", "D", "E"], "cells": ["BTCUSDT regime model"],
         "claims": ["DESCRIPTIVE", "TIMING model input"],
         "evidence": ["probe P10", "SRC24", "SRC26"],
         "reason": "scaler fit over the whole calibration frame leaked into inner validation; ablation changed the scored "
                   "target across feature sets; K/cadence were frozen despite an inner criterion that picked K=2; "
                   "centroids from different scalers were compared in incompatible coordinates."},
        {"id": "A15", "severity": "P0", "title": "minimum economic effect omitted the allocation factor",
         "phases": ["LAB-04", "LAB-05", "LAB-06", "LAB-07", "LAB-08", "LAB-09"],
         "arms": ["A", "B", "C", "D", "E"], "cells": list(ALL_CELLS),
         "claims": ["every economic comparison that used the 0.64 bps/day hurdle"],
         "evidence": ["probe P09", "SRC23", "configs/minimum_economic_effect.json"],
         "reason": "the registered derivation multiplied a notional-based cost by turn-over/day but compared it to an "
                   "account-return endpoint; under the lab's own fixed notional the factor is 2000/20000=0.1."},
        {"id": "A16", "severity": "P0", "title": "claim hierarchy was not fail-closed",
         "phases": ["LAB-09"], "arms": ["A", "B", "C", "D", "E"], "cells": list(ALL_CELLS),
         "claims": ["SELECTION", "TIMING", "DESCRIPTIVE", "PREDICTIVE", "POLICY", "development outcome"],
         "evidence": ["SRC27", "configs/lab09_claim_report.json"],
         "reason": "with FAILED_VALIDITY final, subclaims remained RULED_OUT and confirms_the_development_outcome=true; "
                   "a policy that never acted cannot serve as a predictive-validation test."},
    ]


def historical_invalidation(catalog: list[dict], now: str) -> dict:
    claims = [
        {"id": "SELECTION", "historical_verdict": "RULED_OUT",
         "repaired_verdict": "NOT_EVALUABLE", "caused_by": ["A01", "A03", "A04", "A07", "A08", "A15"]},
        {"id": "TIMING", "historical_verdict": "RULED_OUT",
         "repaired_verdict": "NOT_EVALUABLE", "caused_by": ["A01", "A02", "A03", "A04", "A06", "A08", "A10", "A14", "A15"]},
        {"id": "DESCRIPTIVE", "historical_verdict": "NOT_SUPPORTED",
         "repaired_verdict": "NOT_EVALUABLE", "caused_by": ["A05", "A14"]},
        {"id": "PREDICTIVE", "historical_verdict": "NOT_SUPPORTED",
         "repaired_verdict": "NOT_EVALUABLE", "caused_by": ["A11", "A12", "A14"]},
        {"id": "POLICY", "historical_verdict": "NULL_BY_CONSTRUCTION",
         "repaired_verdict": "NOT_IMPLEMENTED_AS_SPECIFIED", "caused_by": ["A09", "A10", "A11", "A12", "A13"]},
    ]
    return {
        "schema": "regime_lab.historical_invalidation.v3",
        "generated_at_utc": now,
        "invalidated_study": "crypto_regime_timeedge_v2",
        "superseded_by_study": STUDY_ID,
        "historical_conclusion_level": "FAILED_VALIDITY",
        "historical_conclusion_preserved": True,
        "historical_artifacts_edited": False,
        "execution_validity": "FAIL",
        "implementation_fidelity": "DEVIATED",
        "statistical_status": "NOT_EVALUABLE",
        "rule": ("a P0 finding that touches a contrast makes that contrast's statistical claim NOT_EVALUABLE. "
                 "RULED_OUT is only allowed for a valid experiment with the correct threshold and enough evidence. "
                 "Raw curves, null metrics and negative results stay in place; no historical file is rewritten."),
        "findings": [
            {"id": f["id"], "severity": f["severity"], "title": f["title"],
             "affected_phases": f["phases"], "affected_arms": f["arms"],
             "scope_affected": f["cells"], "invalidated_claims": f["claims"],
             "evidence": f["evidence"], "retest_required": True,
             "invalidated_by": f["id"], "superseded_by": STUDY_ID, "reason": f["reason"]}
            for f in catalog
        ],
        "contrast_claims": claims,
        "historical_development_outcome": {
            "value": "NO_PROMISING_DESIGN",
            "repaired_status": "NOT_EVALUABLE",
            "reason": "the development comparison inherits A01-A15 and cannot be cited as a measured outcome.",
        },
        "e_arm": {
            "historical_status": "QUARANTINED",
            "repaired_claim_status": "NOT_IMPLEMENTED_AS_SPECIFIED",
            "reason": "E was D's schedule copied; no conditional-response deployment existed to evaluate.",
        },
        "appendix_evidence": {
            "recovered_bundle": "evidence/corrective_mode4_v3/audit_recovered_v1",
            "original_archive_sha256": AUDIT_ARCHIVE_SHA256,
            "original_self_manifest_defect": "N03 preserved, see finding_disposition.json",
        },
    }


def dispositions(catalog: list[dict], now: str) -> dict:
    def entry(fid, category, status, planned_phase, catching_tests, evidence, note=None):
        return {"id": fid, "category": category, "disposition": status,
                "planned_phase": planned_phase, "required_tests": catching_tests,
                "evidence": evidence, "note": note}

    records = []
    mapping = {
        "A01": ("fix", "RF-02", ["T01", "T59"], "probe P01; configs/cost_binding_verification.json"),
        "A02": ("fix", "RF-02", ["T03", "T04", "T05"], "probes P02/P12; SRC01-02"),
        "A03": ("fix", "RF-02", ["T11", "T12"], "probes P06/P07; SRC14/SRC16"),
        "A04": ("fix", "RF-02", ["T09", "T10", "T13", "T14", "T17", "T18"], "probe P11; SRC03/13/14/21/22"),
        "A05": ("fix", "RF-02", ["T15", "T16"], "probe P05; SRC18-20"),
        "A06": ("fix", "RF-02", ["T06", "T07", "T08"], "OP-19; configs/protective_order_fidelity.json"),
        "A07": ("fix", "RF-02", ["T51", "T52"], "probe P08; SRC15"),
        "A08": ("fix", "RF-02", ["T25", "T26", "T40"], "SRC17"),
        "A09": ("quarantine", "RF-03", ["T37", "T38"], "SRC05", "old E path disabled; repaired E only in RF-03"),
        "A10": ("fix", "RF-03", ["T29", "T30", "T31"], "probe P03; SRC04/SRC25"),
        "A11": ("fix", "RF-03", ["T41", "T42"], "probe P04; SRC06/07/10"),
        "A12": ("fix", "RF-03", ["T45", "T46", "T48", "T49"], "SRC08-10"),
        "A13": ("fix", "RF-03", ["T47"], "SRC06/SRC11"),
        "A14": ("fix", "RF-03", ["T43", "T44", "T50"], "probe P10; SRC24/SRC26"),
        "A15": ("fix", "RF-01", ["T59"], "probe P09; SRC23", "corrected derivation registered in corrective_study_spec.json; freeze before RF-04"),
        "A16": ("fix", "RF-01", ["T60", "T61", "T62"], "SRC27; configs/lab09_claim_report.json", "invalidation manifest written this phase; gate test added in RF-01.4"),
    }
    for finding in catalog:
        fid = finding["id"]
        kind, phase, tests, evidence, *rest = mapping[fid]
        status = "QUARANTINED_UNSUPPORTED_PATH" if kind == "quarantine" else (
            "FIXED_PENDING_TEST" if fid in {"A16"} else "OPEN_REPRODUCED")
        records.append(entry(fid, "P0" if finding["severity"] == "P0" else "P1",
                             status, phase, tests, evidence, rest[0] if rest else None))
    dmap = {
        "D01": ("REPRODUCIBILITY_PARTIAL", "RF-01", "audit ZIP contains no raw pilot market pack; server snapshot is read-only", "RF-05 reproduction_manifest"),
        "D02": ("OPEN_REPRODUCED", "RF-01", "tests hardcode a venv executable/paths", "RF-01.4"),
        "D03": ("OPEN_REPRODUCED", "RF-02", "trial lifecycle ledger lacks duplicate/pruned/failed states", "T63"),
        "D04": ("OPEN_REPRODUCED", "RF-03", "response sampling 4000/400 and missing supported rows", "T64"),
        "D05": ("OPEN_REPRODUCED", "RF-02", "tick/lot metadata is sample-derived, not venue historical authority", "T24"),
        "D06": ("OPEN_REPRODUCED", "RF-01", "no-funding label must travel with every economic artifact", "T24"),
        "D07": ("OPEN_REPRODUCED", "RF-02", "A-HASH five cells unrun and docs drifted", "T19"),
        "D08": ("OPEN_REPRODUCED", "RF-01", "test presence did not prove the runner used the helper", "RF-01.4 mutation checks"),
    }
    for fid, (status, phase, note, test) in dmap.items():
        records.append(entry(fid, "D", status, phase, [test], "recovered audit bundle", note))
    nmap = {
        "N01": ("OPEN_REPRODUCED", "RF-02", "PF definition must stay raw_quantbt vs trade PF", "T54"),
        "N02": ("OPEN_REPRODUCED", "RF-02", "same-close native clock is not next-open", "T06/T07"),
        "N03": ("OPEN_REPRODUCED", "RF-05", "audit_bundle_manifest self-hash defect preserved as history", "T70"),
        "N04": ("OPEN_REPRODUCED", "RF-02", "observer aliases (turnover/mean_return/volatility) must be mapped", "T53"),
        "N05": ("OPEN_REPRODUCED", "RF-02", "whole-window Sharpe used sqrt(len(steps))", "T53"),
    }
    for fid, (status, phase, note, test) in nmap.items():
        records.append(entry(fid, "N", status, phase, [test], "recovered audit bundle", note))
    return {
        "schema": "regime_lab.finding_disposition.v3",
        "generated_at_utc": now,
        "phase": PHASE,
        "vocabulary": ["OPEN_REPRODUCED", "FIXED_PENDING_TEST", "FIXED_AND_VERIFIED",
                       "ALREADY_FIXED_WITH_SOURCE_AND_TEST_EVIDENCE", "QUARANTINED_UNSUPPORTED_PATH",
                       "SECONDARY_REPAIRED_NOT_MARKET_EVALUATED", "BLOCKED_WITH_REASON"],
        "dispositions": records,
        "counts": {s: sum(1 for r in records if r["disposition"] == s)
                   for s in sorted({r["disposition"] for r in records})},
        "rule": ("NOT_BENEFICIAL is not a disposition for a fee/backdate/fabricated-fill defect. "
                 "A quarantined path blocks every arm that depends on it."),
    }


def corrective_spec(now: str, snapshot_manifest_sha: str) -> dict:
    return {
        "schema": "regime_lab.corrective_study_spec.v3",
        "registered_at_utc": now,
        "registered_by": "OpenCode under user approval (2026-09-11)",
        "study_id": STUDY_ID,
        "supersedes_study": "crypto_regime_timeedge_v2",
        "status": "RF01_REGISTERED__RF02_QUALIFICATION_PENDING",
        "source_of_truth": {
            "plan": {"path": PLAN.name, "sha256": PLAN_SHA256},
            "historical_study_registration": "configs/study_registration.json",
            "historical_conclusion": "FAILED_VALIDITY (preserved; never rewritten)",
            "precedence": ["this spec", "verified economic/availability contracts", "A01-A16 findings",
                           "recovered audit evidence", "Final V2 where not superseded"],
        },
        "primary_question": ("On the same four real alphas, the same economic contract and the same Mode 4 "
                             "train-only selector with the same training-memory rule, does a causal regime-triggered "
                             "refit schedule improve out-of-sample continuous-account net return and reduce decay "
                             "versus the calendar per_fold_causal WFO?"),
        "mode4_contract": {
            "optimization_mode": "mode_4_is_only_robust",
            "optimization_schedule": "per_fold_causal",
            "candidate_selection_metric": "is_only_robust",
            "scoring_backend": "endpoint",
            "calendar_contract": "exact_v2",
            "target_runtime_requested": "rust",
            "native_prepared_wfo": "off_until_qualified",
            "oos_used_for_selection": False,
            "forbidden": ["another optimization mode", "a non-Sharpe utility in a Sharpe field",
                          "private default-selector imitation", "future OOS decay as a primary ranker"],
        },
        "arms": {
            "primary": ["M4_CAL", "M4_REGIME"],
            "budget_control": "M4_CAL_MATCHED",
            "secondary_selector": ["M4_CAL_NEIGH", "M4_REGIME_NEIGH"],
            "secondary_policy": "E_RESPONSE_V2",
            "E_RESPONSE_V2_status": "DISABLED_UNTIL_REPAIRED_RF03",
            "naming_rule": "new names only; historical A/B/C/D/E are never reused",
        },
        "primary_contrast_family": [
            {"id": "TIMING", "contrast": "M4_REGIME - M4_CAL",
             "question": "does causal regime timing add account net return on the same continuous account?"},
            {"id": "BUDGET_AWARE", "contrast": "M4_REGIME - M4_CAL_MATCHED",
             "question": "is any timing gain separable from refit cadence and compute?"},
        ],
        "secondary_contrasts": [
            {"id": "SELECTOR", "contrast": "M4_CAL_NEIGH - M4_CAL", "family": "secondary"},
            {"id": "INTERACTION",
             "contrast": "(M4_REGIME_NEIGH - M4_CAL_NEIGH) - (M4_REGIME - M4_CAL)", "family": "secondary"},
            {"id": "POLICY_E", "contrast": "E_RESPONSE_V2 - M4_CAL", "family": "exploratory",
             "status": "DISABLED_UNTIL_REPAIRED_RF03"},
        ],
        "cohort": {
            "alphas": ["A-SC", "A-HMA", "A-VWAP", "A-HASH"],
            "symbols": list(SYMBOLS),
            "matrix_cells": 20,
            "primary_cells": "cells that pass RF-02 route qualification; A-HASH may stay blocked and keeps null metrics",
            "data_product": "crypto_binance_futures_1m",
            "snapshot_id": "server_core_v1",
            "snapshot_manifest_sha256": snapshot_manifest_sha,
            "funding": "MISSING_DECLARED",
        },
        "windows": {
            "development": "2021-01-01..2023-12-31",
            "outer": "2024-01-01..2026-08-31 (consumed by the invalidated LAB-09 confirmation)",
            "contamination_status": "NESTED_RETROSPECTIVE",
            "prospective_protocol": {"status": "SPECIFIED_NOT_EXECUTED", "artifact": "TBD_RF05"},
            "rule": "no interval is an untouched holdout; corrected results are retrospective/prequential evidence",
        },
        "cost_contract": {
            "one_way_taker_fee": 0.0004,
            "slippage_per_side": 0.0001,
            "binding_rule": "route-specific typed binding: explicit one-way fee_rate, or fee=2*one_way on legacy round-trip endpoints",
            "binding_status": "TO_BE_QUALIFIED_RF02",
            "stress_multipliers": [1.0, 1.5, 2.0],
            "sizing_contract": "percent-equity semantics per actual resolved factory; frozen by golden fixtures in RF-02",
        },
        "mde": {
            "historical_registered": {"value": 6.4e-05, "unit": "account daily net return",
                                      "status": "PRESERVED_AS_HISTORY",
                                      "artifact": "configs/minimum_economic_effect.json"},
            "corrected_derivation": {
                "formula": "one_way_cost_uncertainty_round_trip * actual_round_trips_per_day * actual_notional_over_equity",
                "a15_note": "the old derivation omitted allocation; under its own fixed notional the value would be 6.4e-06/day (0.064 bps)",
                "status": "PENDING_RF02_ACTUAL_ENGINE_UNITS",
                "freeze_before": "RF-04 design freeze and RF-05 confirmation",
            },
            "business_hurdle": {"status": "TO_BE_SET_BY_RESEARCH_OWNER", "value": None,
                                "rule": "may be chosen independently of the cost derivation but must be registered before results"},
        },
        "seeds": {
            "probe_design": 20260911,
            "model_multi_start": [11, 23, 37, 51],
            "placebo": 20260912,
            "repeated_seeds_measure": "search variability, not independent observations",
        },
        "budgets": {
            "search_trials_per_cutoff": {"pilot_min": 32, "pilot_max": 64,
                                         "freeze_after_dry_run_coverage": True,
                                         "note": "64 is not a guarantee; the final value is frozen before RF-04 discovery"},
            "tier_caps_seconds": {"T0": 60, "T1": 120, "T2": 600, "T3": 900, "T4": "approved_total"},
            "os_resource_budget_start": {"workers": 1, "cpu_limit": 2, "working_memory_gib": 4},
            "compute_matching": "total candidate-window-bars, route cost, probes, failed attempts, fits, wall/CPU; equal policy budget per arm",
            "profiler_fields": ["load/prepare/indicator/intent-pack", "QuantBT simulation/metrics/native",
                                "mode4 selection/model-fit/regime/scheduling", "audit encode/flush/report",
                                "unique evaluations/cache hits/visited bars", "cold compile/warm run/RSS",
                                "requested/resolved backend/native origin"],
        },
        "latency_policy": {
            "refit_latency": "measured conservative operational budget; zero seconds is refused",
            "activation_rule": "effective_at >= max(selection_cutoff, fit_ready_at, indicator_ready_at, execution boundary)",
            "no_backdating": True,
        },
        "claim_gates": {
            "execution_validity": ["PASS", "FAIL", "PARTIAL"],
            "implementation_fidelity": ["AS_SPECIFIED", "DEVIATED", "NOT_IMPLEMENTED"],
            "statistical_status": ["NOT_EVALUABLE", "INCONCLUSIVE", "NEGATIVE_WITHIN_SCOPE", "POSITIVE_WITHIN_SCOPE"],
            "rule": "a P0 touching a contrast sets its statistical status to NOT_EVALUABLE; RULED_OUT requires validity, the correct threshold and enough evidence",
        },
        "evidence_layout": {
            "root": "evidence/corrective_mode4_v3",
            "phase_dir": f"evidence/corrective_mode4_v3/{PHASE}",
            "historical_evidence": "evidence/crypto_regime_timeedge_v2 (append-only, never edited)",
            "report_pair": "report.md + report.json per phase",
            "rerun_rule": "a superseding run gets a new artifact name or a supersedes chain; committed results are not overwritten in place",
        },
        "acceptance_registry": {"path": "configs/rf_acceptance_registry.json", "ids": "T01..T70",
                                "note": "separate from the historical T01..T64 registry; the old registry is untouched"},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true",
                        help="overwrite existing RF-01 artifacts (refused by default)")
    args = parser.parse_args()

    if sha256_file(PLAN) != PLAN_SHA256:
        raise SystemExit("the merged plan changed after RF-01 registered its hash; review before regenerating")

    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    marker = json.loads((LAB_ROOT / ".lab_marker.json").read_text(encoding="utf-8"))
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID, lab_run_id=PHASE)
    now = utc_now_iso()

    def emit(relpath: str, payload: dict, schema: str) -> dict:
        target = writer.run_dir / relpath
        if target.exists() and not args.force:
            raise SystemExit(f"{target} exists; pass --force to supersede this run explicitly")
        return writer.write_json(relpath, payload, schema=schema)

    snapshot_manifest = LAB_ROOT / "snapshots" / "server_core_v1" / "manifest.json"
    snapshot_sha = sha256_file(snapshot_manifest) if snapshot_manifest.is_file() else None
    source = source_manifest()
    catalog = finding_catalog()

    identity = {
        "schema": "regime_lab.working_copy_identity.v3",
        "generated_at_utc": now,
        "phase": PHASE,
        "study_id": STUDY_ID,
        "lab_root": str(LAB_ROOT),
        "lab_marker_study_id": marker.get("study_id"),
        "lab_marker_note": ("the marker is LAB-01 bootstrap evidence and is not rewritten; the corrective study is a "
                            "successor study inside the same LAB_ROOT"),
        "branch": git("branch", "--show-current"),
        "head_commit": git("rev-parse", "HEAD"),
        "working_tree_porcelain": git("status", "--porcelain").splitlines(),
        "plan": {"path": PLAN.name, "sha256": PLAN_SHA256},
        "original_audit_archive": {"name": "regime-lab-main.zip", "sha256": AUDIT_ARCHIVE_SHA256,
                                   "present_in_lab": False,
                                   "note": "user-provided; its contents are preserved in the merged plan and the recovered bundle"},
        "recovered_bundle": {
            "path": "evidence/corrective_mode4_v3/audit_recovered_v1",
            "status": "RESTORED_VERIFIED", "members": 20, "bytes": 1462711,
            "executed_restored_code": False,
            "extractor": "scripts/extract_embedded_audit.py",
            "extractor_sha256": sha256_file(LAB_ROOT / "scripts" / "extract_embedded_audit.py"),
        },
        "environment": environment_fingerprint(),
        "quantbt_installed": InstalledQuantBT.load().identity(),
        "candidate_copy": {
            "root": str(CANDIDATE.relative_to(LAB_ROOT)),
            "endpoint_sha256": sha256_file(QC / "endpoint.py"),
            "walkforward_sha256": sha256_file(QC / "walkforward.py"),
            "matches_audited_vfy01": sha256_file(QC / "endpoint.py") ==
                                     "45ede55d0d66dd3a30089584b92199a455acca83e8f0418df3305874c28929a6",
        },
        "requirements_lock_sha256": sha256_file(LAB_ROOT / "configs" / "requirements.lock"),
        "protected_paths_write_refused": protected_write_probes(policy),
        "preflight": run_all(policy),
        "source_manifest_counts": {key: len(value) for key, value in source.items()},
    }

    manifest_payload = {
        "schema": "regime_lab.source_before_manifest.v3",
        "generated_at_utc": now,
        "purpose": "hash of every lab source/config/test file before RF-02 repairs",
        "counts": {key: len(value) for key, value in source.items()},
        "files": source,
    }
    binding = binding_report()
    invalidation = historical_invalidation(catalog, now)
    disposition = dispositions(catalog, now)
    spec = corrective_spec(now, snapshot_sha)

    written = [
        emit("working_copy_identity.json", identity, identity["schema"]),
        emit("source_before_manifest.json", manifest_payload, manifest_payload["schema"]),
        emit("quantbt_binding_report.json", binding, "regime_lab.quantbt_binding_report.v3"),
        emit("historical_invalidation.json", invalidation, invalidation["schema"]),
        emit("finding_disposition.json", disposition, disposition["schema"]),
        emit("corrective_study_spec.json", spec, spec["schema"]),
    ]

    print(json.dumps({
        "run_dir": str(writer.run_dir),
        "artifacts": [w["relpath"] for w in written],
        "vfy_present": f"{binding['checks_present']}/{binding['checks_total']}",
        "findings": len(catalog),
        "dispositions": disposition["counts"],
        "snapshot_manifest_sha256": snapshot_sha,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
