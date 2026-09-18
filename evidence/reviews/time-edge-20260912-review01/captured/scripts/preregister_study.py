#!/usr/bin/env python
"""LAB-01 L01.5: preregister the study before any performance is observed.

Writes configs/study_registration.json + configs/hypothesis_registry.json.
Fields that genuinely cannot be resolved yet stay null with a named blocker;
a null is visible missing information, never a placeholder that counts as PASS.
"""

from __future__ import annotations

import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter, utc_now_iso  # noqa: E402
from crypto_regime_lab.quantbt_bridge.capabilities import InstalledQuantBT  # noqa: E402
from crypto_regime_lab.safety.archive import ALLOWED_ALPHA_FILES, ALPHA_IDS  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy, sha256_file  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT"]

# Guide 10.4 pilot protocol, registered BEFORE any result is seen.
ALPHA_TIMEFRAMES = {
    "A-SC":   {"decision_bars": "15m", "execution_bars": "1m", "secondary_registered": "1h"},
    "A-VWAP": {"decision_bars": "15m", "execution_bars": "1m", "secondary_registered": "5m"},
    "A-HMA":  {"decision_bars": "1h",  "execution_bars": "1m", "secondary_registered": "15m"},
    "A-HASH": {"decision_bars": "15m", "execution_bars": "1m", "secondary_registered": "1h"},
}
PILOT_ORDER = ["A-SC", "A-HMA", "A-VWAP", "A-HASH"]

ARMS = {
    "A": {"selector": "installed_wfo_selector", "refit": "frozen_calendar", "purpose": "primary baseline"},
    "B": {"selector": "independent_neighborhood", "refit": "frozen_calendar", "purpose": "robustness contribution"},
    "C": {"selector": "installed_wfo_selector", "refit": "regime_triggered_full_refresh", "purpose": "timing contribution"},
    "D": {"selector": "independent_neighborhood", "refit": "regime_triggered_full_refresh", "purpose": "selector x timing interaction"},
    "E": {"selector": "independent_neighborhood + bank + response policy", "refit": "slow model fit; bank refresh as B",
          "purpose": "extension: intelligent switching separated from frequent refit"},
}
CONTROLS = ["RISK_ONLY", "CALENDAR_MATCHED", "BANK_CALENDAR", "STATE_PLACEBO",
            "DELAYED_STATE", "EXPOST_DIAGNOSTIC", "USER_PRESET_REFERENCE"]

PRIMARY_CONTRASTS = [
    {"id": "H1", "contrast": "B-A", "question": "does independent-neighborhood selection beat the installed selector on the same calendar?"},
    {"id": "H2", "contrast": "C-A", "question": "does regime-triggered refresh timing beat the frozen calendar with the same selector?"},
    {"id": "H3", "contrast": "D-B", "question": "does regime timing add anything on top of the new selector?"},
    {"id": "H4", "contrast": "D-C", "question": "does the new selector add anything on top of regime timing?"},
    {"id": "H5", "contrast": "(D-C)-(B-A)", "question": "is there a selector x timing interaction?"},
]
EXTENSION_CONTRASTS = [
    {"id": "H6", "contrast": "E-B", "question": "does bank + response switching beat the same selector without switching?"},
    {"id": "H7", "contrast": "E-BANK_CALENDAR", "question": "is the gain from regime information or merely from having a bank?"},
]


def build_registration(installed: InstalledQuantBT, policy: SandboxPolicy) -> dict:
    cells = [
        {
            "cell_id": f"{alpha}|{symbol}",
            "alpha_id": alpha,
            "symbol": symbol,
            "decision_bars": ALPHA_TIMEFRAMES[alpha]["decision_bars"],
            "execution_bars": ALPHA_TIMEFRAMES[alpha]["execution_bars"],
            "status": "REGISTERED_NOT_RUN",
        }
        for alpha in PILOT_ORDER
        for symbol in SYMBOLS
    ]
    return {
        "schema": "crypto_regime_lab.study.v2",
        "study_id": STUDY_ID,
        "status": "DRAFT_REQUIRES_LAB03_DATA_PIN",
        "status_reason": (
            "Baseline, alpha allowlist, arms, cells, costs and budgets are frozen here. "
            "instrument_registry_digest, data_roles and the funding cohort cannot be pinned until "
            "LAB-03 inventories the actual storage, so they stay null with named blockers."
        ),
        "registered_at_utc": utc_now_iso(),
        "guide_sha256": sha256_file(LAB_ROOT / "QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md"),
        "baseline": {
            "core_version": installed.distributions.get("quantbt-engine"),
            "native_expected": "0.4.2",
            "native_installed": installed.distributions.get("quantbt-native"),
            "source_sha": None,
            "source_sha_blocker": "lab consumes the PyPI wheel; upstream git SHA not required and not claimed",
            "wheel_digests": "recorded in evidence/environment_baseline.json wheelhouse map",
            "installed_origins": installed.identity()["import_origin"],
            "matches_guide_baseline": (
                installed.distributions.get("quantbt-engine") == "1.1.1"
                and installed.distributions.get("quantbt-native") == "0.4.2"
            ),
        },
        "allowed_alpha_files": sorted(ALLOWED_ALPHA_FILES),
        "alpha_ids": ALPHA_IDS,
        "trade_symbols": SYMBOLS,
        "spot_clean_from": "2020-01-01T00:00:00Z",
        "source_preset_role": "retrospective_reference_only",
        "primary_arms": ["A", "B", "C", "D"],
        "extension_arms": ["E"],
        "arm_definitions": ARMS,
        "controls": CONTROLS,
        "primary_matrix": {"alphas": len(PILOT_ORDER), "symbols": len(SYMBOLS), "cells": len(cells),
                           "pilot_order": PILOT_ORDER, "cell_list": cells},
        "timeframes": ALPHA_TIMEFRAMES,
        "model": {
            "primary": "discrete_jump_model",
            "initial_states": 3,
            "observation_interval": "4h",
            "fit_cadence_days": 28,
            "train_memory_days": 365,
            "values_are_starting_hypotheses": True,
            "incumbent_comparator": "quantbt.volatility_regime_labels (M0/legacy; see incumbent_regime_probe.json)",
        },
        "execution": {
            "contract": "event_lifecycle_v3_next_open",
            "contract_available_in_install": True,
            "account_contract": {
                "initial_capital_usdt": 20000.0,
                "entry_notional_usdt": 2000.0,
                "leverage_cap": 1.0,
                "margin_mode": "cross",
                "frozen_for_all_arms": True,
                "provenance": "guide 4.1 proposal sizing, frozen here; never a tuned parameter",
            },
            "instrument_registry_digest": None,
            "instrument_registry_blocker": "LAB-03 must pin tick/lot/min-notional from actual instrument metadata",
            "fee_funding_slippage_config": {
                "taker_fee_rate": 0.0004,
                "fee_provenance": "Binance USD-M standard taker rate; re-pin against actual contract data in LAB-03",
                "slippage": 0.0001,
                "slippage_provenance": "engine default, applied identically to every arm",
                "funding": "PENDING_COVERAGE_CHECK",
                "funding_policy": "missing funding history is never treated as zero on a realistic-net-carry claim",
                "frozen_for_all_arms": True,
            },
            "cost_stress_levels": [1.0, 1.5, 2.0],
        },
        "data_roles": None,
        "data_roles_blocker": "LAB-03 must produce data_product_inventory.json before roles/cutoffs can be assigned",
        "primary_endpoint": {
            "statistic": "mean daily net-return difference between arms on the same risk budget",
            "aggregation": "daily UTC paired differences on a common evaluation interval",
            "guardrails": ["max_drawdown", "expected_shortfall", "exposure", "turnover", "costs", "trade_count"],
            "registered_before_results": True,
        },
        "minimum_economic_effect": None,
        "minimum_economic_effect_blocker": (
            "must be derived from measured execution-cost uncertainty in LAB-03/LAB-04, "
            "never chosen after seeing an observed delta"
        ),
        "hypothesis_family_and_adjustment": {
            "primary_family": [h["id"] for h in PRIMARY_CONTRASTS],
            "adjustment": "Holm-type across the primary contrast family; block bootstrap for paired uncertainty",
            "block_length_selection": "development only, with a registered sensitivity range",
            "exploratory_contrasts_disclosed": True,
        },
        "contamination": {
            "claim_level": "RETROSPECTIVE_NESTED_CAUSAL_RESEARCH",
            "reason": (
                "supplied presets were TPE-tuned on the full sample and the tuning cutoff is unknown, "
                "so no interval of this dataset can be called an untouched holdout"
            ),
            "prospective_protocol_required_for_strong_claim": True,
        },
        "resource_budget": {"workers": 1, "cpu_limit": 2, "working_memory_gib": 4},
        "market_experiments_allowed": False,
        "market_experiments_unlock_gate": "LAB-02 adapter certification AND LAB-03 data qualification",
        "production_mutations_allowed": False,
        "live_execution_allowed": False,
        "protected_roots": [str(p) for p in policy.protected_roots],
    }


def build_hypothesis_registry() -> dict:
    return {
        "schema": "crypto_regime_lab.hypothesis_registry.v1",
        "study_id": STUDY_ID,
        "registered_at_utc": utc_now_iso(),
        "primary_contrasts": PRIMARY_CONTRASTS,
        "extension_contrasts": EXTENSION_CONTRASTS,
        "conclusion_levels": [
            "DESCRIPTIVE_VALUE", "CONDITIONAL_RESPONSE_EVIDENCE", "NET_PARAMETER_SELECTION_EDGE",
            "NET_TIMING_EDGE", "NET_POLICY_EDGE", "NO_INCREMENTAL_VALUE",
            "INCONCLUSIVE_SAMPLE", "FAILED_VALIDITY",
        ],
        "falsification_commitments": [
            "a negative or inconclusive result is a valid outcome and is published, not rerun until it wins",
            "risk-only improvement is never recorded as a parameter-selection edge",
            "zero switches because no challenger qualified is a valid technical pass",
            "an alpha that cannot be certified is reported NOT_READY with null metrics, never PnL=0",
        ],
        "forbidden_claims": [
            "regime work from full-sample-fit state correlation",
            "no leakage from a .shift(1)",
            "out-of-sample for full-set presets or a holdout used to tune policy",
            "better on every dimension from one improved metric",
            "Rust parity from close final equity",
            "all four alphas certified from a successful AST parse",
            "absolute production safety from path naming without OS-level isolation",
        ],
    }


def build_freeze_holdout_policy() -> dict:
    """L01.5 freeze/holdout policy, registered before any performance is seen."""
    return {
        "schema": "crypto_regime_lab.freeze_holdout_policy.v1",
        "study_id": STUDY_ID,
        "registered_at_utc": utc_now_iso(),
        "two_stage_information": {
            "discovery": {
                "permits": [
                    "adapter repair and versioning",
                    "feature/model/K/penalty/cadence hypotheses",
                    "selector and probe-design tuning on development splits",
                    "inner chronological validation",
                ],
                "requires": "the full search history is retained, including negative and pruned runs",
            },
            "confirmation": {
                "permits": ["executing the frozen protocol exactly as registered"],
                "forbids": [
                    "any code, config, cost, cadence or data-role change",
                    "re-running after seeing the outcome",
                    "human adjustment mid-run",
                    "choosing the confirmatory design from outer results",
                ],
            },
        },
        "freeze_procedure": {
            "trigger": "LAB-08 exit with a selected confirmatory design",
            "frozen_objects": [
                "alpha adapter versions and digests",
                "selector and probe design + radii",
                "regime model K, lambda, features, scaler, cadence",
                "response estimator bandwidth, shrinkage, gates",
                "economic contract: capital, notional, leverage, fees, slippage, funding cohort",
                "evaluation interval, seeds, compute budget",
            ],
            "freeze_artifact": "configs/confirmation_spec.json (written at LAB-08 exit, absent until then)",
            "validator_rule": "a study may not move to FROZEN while any required field is null",
        },
        "holdout_status": {
            "claim_level": "RETROSPECTIVE_NESTED_CAUSAL_RESEARCH",
            "untouched_holdout_exists": False,
            "reason": (
                "the supplied presets were TPE-tuned on the full sample and the tuning cutoff is "
                "unknown, so no interval of this dataset can be declared untouched"
            ),
            "forbidden": [
                "labelling the final year 'untouched' without an exposure audit",
                "calling the provided full-set presets out-of-sample",
                "re-tuning after a holdout has been unlocked",
            ],
            "path_to_a_strong_claim": (
                "a prospective observation protocol registered after the freeze, evaluated on data "
                "that did not exist at freeze time; the lab writes the protocol artifact but does "
                "not execute live"
            ),
        },
        "access_logging": {
            "rule": "every read of a confirmation-role data range is logged with run id and purpose",
            "artifact": "evidence/{study_id}/{run_id}/data_access_log.jsonl (from LAB-03 onward)",
        },
        "unlock_gates": {
            "market_execution": "LAB-02 certification AND LAB-03 data qualification",
            "confirmation_run": "LAB-08 design freeze committed",
        },
    }


def main() -> int:
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)
    installed = InstalledQuantBT.load()
    with writer.attempt("L01.5.preregister") as att:
        registration = build_registration(installed, policy)
        registry = build_hypothesis_registry()
        freeze_policy = build_freeze_holdout_policy()
        writer.write_config("study_registration.json", registration)
        writer.write_config("hypothesis_registry.json", registry)
        writer.write_config("freeze_holdout_policy.json", freeze_policy)
        writer.write_json("freeze_holdout_policy.json", freeze_policy, schema=freeze_policy["schema"])
        writer.write_json("study_registration.json", registration, schema=registration["schema"])
        writer.write_json("hypothesis_registry.json", registry, schema=registry["schema"])
        att.detail = {"cells": len(registration["primary_matrix"]["cell_list"]),
                      "status": registration["status"]}
    print(f"status                = {registration['status']}")
    print(f"cells registered      = {len(registration['primary_matrix']['cell_list'])}")
    print(f"baseline matches guide= {registration['baseline']['matches_guide_baseline']}")
    print(f"primary contrasts     = {[h['contrast'] for h in PRIMARY_CONTRASTS]}")
    print(f"freeze/holdout policy = registered (claim level {freeze_policy['holdout_status']['claim_level']})")
    print("open blockers         = data_roles, instrument_registry_digest, minimum_economic_effect")
    print(f"evidence -> {writer.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
