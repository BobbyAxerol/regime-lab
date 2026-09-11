"""Suite-level LAB-02 tests: probes, catalog, reference parity, fixtures, engine parity."""

from __future__ import annotations

import json

import numpy as np
import pytest

from crypto_regime_lab.alphas import catalog as catalog_mod
from crypto_regime_lab.alphas.findings import FINDINGS, SEMANTIC_DELTAS
from crypto_regime_lab.safety.archive import ALLOWED_ALPHA_FILES


@pytest.fixture(scope="module")
def raw_dir(lab_root):
    return lab_root / "vendor_readonly" / "alphas_raw"


@pytest.fixture(scope="module")
def inventories(raw_dir):
    out = {}
    for filename, digest in ALLOWED_ALPHA_FILES.items():
        inv = catalog_mod.inventory_file(raw_dir / filename, digest)
        out[inv.alpha_id] = inv
    return out


# --- L02.1 catalog ------------------------------------------------------

def test_every_guide_section_3_finding_is_registered():
    counts = {}
    for f in FINDINGS:
        counts[f.alpha_id] = counts.get(f.alpha_id, 0) + 1
    assert counts["A-HASH"] == 7 and counts["A-VWAP"] == 7
    assert counts["A-HMA"] == 9
    assert counts["A-SC"] == 7, "6 from the guide plus SC-07 found by the lab"
    ids = {f.id for f in FINDINGS}
    assert {f"AH-0{i}" for i in range(1, 8)} <= ids
    assert {f"AV-0{i}" for i in range(1, 8)} <= ids
    assert {f"HM-0{i}" for i in range(1, 10)} <= ids
    assert {f"SC-0{i}" for i in range(1, 8)} <= ids


def test_every_finding_has_a_reproducer_and_source_lines():
    for f in FINDINGS:
        assert f.source_lines and f.reproducer and f.handling


def test_semantic_deltas_reference_real_findings():
    finding_ids = {f.id for f in FINDINGS}
    for d in SEMANTIC_DELTAS:
        assert d.change_kind in ("packaging_fix", "execution_repair", "indicator_repair",
                                 "thesis_change")
        assert set(d.finding_refs) <= finding_ids, d.delta_id
        assert d.before_semantics and d.after_semantics and d.reproducer


def test_thesis_changes_are_excluded_from_every_arm():
    for d in SEMANTIC_DELTAS:
        if d.change_kind == "thesis_change":
            assert d.applies_to_experiment_arms == [], (
                f"{d.delta_id} changes the alpha thesis and may not run inside a canonical arm"
            )


def test_preset_classification_matches_the_guide_appendix_a1(inventories):
    catalog, unmapped = catalog_mod.classify_presets(inventories)
    per_alpha = {}
    for rec in catalog:
        per_alpha[rec["declared_in_alpha"]] = per_alpha.get(rec["declared_in_alpha"], 0) + 1
    unmapped_per = {}
    for rec in unmapped:
        unmapped_per[rec["declared_in_alpha"]] = unmapped_per.get(rec["declared_in_alpha"], 0) + 1
    assert per_alpha["A-HASH"] == 6 and unmapped_per.get("A-HASH", 0) == 0
    assert per_alpha["A-HMA"] == 13 and unmapped_per["A-HMA"] == 1      # sl_mode_map
    assert per_alpha["A-SC"] == 1
    assert per_alpha["A-VWAP"] == 5 and unmapped_per["A-VWAP"] == 10    # 4 VWAP + base, 10 others


def test_unmapped_presets_are_not_eligible_for_anything(inventories):
    _catalog, unmapped = catalog_mod.classify_presets(inventories)
    for rec in unmapped:
        assert rec["classification"] == "UNMAPPED"
        assert rec["eligible_for_retrospective_reference"] is False
        assert rec["eligible_for_primary_candidate_bank"] is False


def test_every_preset_is_quarantined(inventories):
    catalog, _unmapped = catalog_mod.classify_presets(inventories)
    for rec in catalog:
        assert rec["provenance"] == "user_full_sample_tpe"
        assert rec["eligible_for_early_fold_warm_start"] is False
        assert rec["eligible_for_independent_oos_claim"] is False


def test_parameter_schema_is_derived_from_actual_reads(inventories):
    assert "sl_mult" not in inventories["A-HMA"].parameter_schema
    assert {"min_length", "max_length", "flat", "take_profit"} <= inventories["A-HMA"].parameter_schema
    assert {"coeff", "AP", "novolumedata", "regime_threshold"} <= inventories["A-SC"].parameter_schema
    assert {"rsi_len", "htf_tf", "exit_at_vwap"} <= inventories["A-VWAP"].parameter_schema


def test_unused_knobs_are_detected(raw_dir, inventories):
    source = (raw_dir / "adaptive_hma_cpp.py").read_text()
    knobs = catalog_mod.unused_knobs(inventories["A-HMA"], source)
    dead = knobs["unused_function_arguments"].get("core_adaptive_hma_signals", [])
    assert {"time_ms", "volume", "double_up"} <= set(dead)
    assert "sl_mult" in knobs["preset_keys_never_read_by_the_alpha"]


# --- Appendix B probes ---------------------------------------------------

def test_all_21_appendix_b_probes_confirm(lab_root):
    from crypto_regime_lab.alphas.probes import run_all_probes

    report = run_all_probes(lab_root)
    assert report["probe_count"] == 21
    failed = [r["id"] for r in report["results"] if r["status"] != "CONFIRMED"]
    assert failed == [], failed


def test_probe_observations_match_the_guide_appendix_e(lab_root):
    from crypto_regime_lab.alphas.probes import run_all_probes

    by_id = {r["id"]: r["observed"] for r in run_all_probes(lab_root)["results"]}
    assert by_id["PARSE_vwap.py"] == 249
    assert by_id["PARSE_hash_momentum.py"] == 166
    assert by_id["PARSE_adaptive_hma_cpp.py"] == 349
    assert by_id["PARSE_signal_combine.py"] == 145
    assert by_id["HASH_ATR_CLOSE_ONLY"] == 0.0
    assert by_id["HASH_EQUITY_NO_MTM"]["terminal_wallet_plus_unrealized"] == 10100.0
    assert by_id["HASH_ONE_TP_BRANCH_PER_BAR"]["units"] == [0.0, 10.0, 5.0]
    assert by_id["HASH_UNORDERED_TP_PRESETS"] == ["huhu", "bubu", "haft", "kuku"]
    assert by_id["HMA_FLAT_RSI"] == {"at_seed": 50.0, "next": 100.0}
    assert by_id["HMA_INVERTED_LENGTH_PRESETS"] == ["hfhf", "hjhj", "hoho", "hbhb"]
    assert by_id["HMA_IGNORED_SL_MULT"] == 13
    assert by_id["VWAP_OPEN_IGNORED"]["same_output_after_open_change"] is True
    assert by_id["SIGCOMBINE_LONG_FLAT_ONLY"] == [0, 2, 0, 0, 2]
    assert by_id["SIGCOMBINE_CROSSOVER_DIFF"]["actual"] == [False, False, False, False]
    assert by_id["SIGCOMBINE_CROSSOVER_DIFF"]["standard_shifted_operand"] == [False, False, False, True]
    assert by_id["JM_FORWARD_DP_ORACLE"]["max_abs_error"] < 1e-12


# --- L02.2 reference parity ---------------------------------------------

def test_reference_oracle_reproduces_every_source_kernel(raw_dir):
    from crypto_regime_lab.alphas.reference.parity import parity_report

    report = parity_report(raw_dir)
    assert report["status"] == "PASS", report["failures"]
    exact = [r for r in report["source_vs_oracle"] if r["tolerance_class"] == "exact"]
    assert len(exact) >= 12
    for r in exact:
        assert r["max_abs_error"] == 0.0, r["pair_id"]


def test_library_divergences_are_documented_and_decay(raw_dir):
    from crypto_regime_lab.alphas.reference.parity import parity_report

    report = parity_report(raw_dir)
    divergences = [r for r in report["oracle_vs_library"]
                   if r["tolerance_class"] == "documented_divergence"]
    assert {r["pair_id"] for r in divergences} == {"ta.RSIIndicator", "ta.AverageTrueRange"}
    for r in divergences:
        assert r["passed"], r
        assert "decay_ok=True" in r["note"]


def test_parity_report_is_strict_json_serialisable(raw_dir):
    from crypto_regime_lab.evidence.manifest import dumps_strict
    from crypto_regime_lab.alphas.reference.parity import parity_report

    dumps_strict(parity_report(raw_dir))


# --- L02.7 fixtures and L02.8 engine parity ------------------------------

def test_all_execution_fixtures_pass():
    from crypto_regime_lab.alphas.fixtures import run_all_fixtures

    report = run_all_fixtures()
    failed = [r["fixture_id"] for r in report["results"] if not r["passed"]]
    assert failed == [], failed
    assert report["fixture_count"] >= 13


def test_engine_contract_is_the_guides_primary_clock():
    from crypto_regime_lab.quantbt_bridge.intent_tape import contract_snapshot

    contract = contract_snapshot()
    assert contract["signal_phase"] == "bar_close"
    assert contract["entry_fill_phase"] == "next_open"
    assert contract["market_fill_policy"] == "next_open"
    assert contract["same_bar_policy"] == "conservative"
    assert contract["strict_data"] is True


def test_python_and_rust_account_traces_are_identical():
    from crypto_regime_lab.quantbt_bridge.parity import parity_report

    report = parity_report()
    assert report["status"] == "PASS", report["account_trace_failures"]
    assert report["case_count"] >= 7
    for case in report["cases"]:
        for field, diff in case["trace_diffs"].items():
            assert diff.get("exact"), f"{case['case_id']}/{field}: {diff}"


def test_fill_trace_parity_is_disclosed_as_blocked():
    from crypto_regime_lab.quantbt_bridge.parity import parity_report

    report = parity_report()
    assert report["fill_trace_parity"]["status"] == "BLOCKED_CAPABILITY"
    assert "rust backend returns an empty fill sequence" in report["fill_trace_parity"]["detail"]


def test_capability_matrix_records_the_hash_ladder_blocker():
    from crypto_regime_lab.quantbt_bridge.capability_probe import capability_matrix

    matrix = capability_matrix()
    assert matrix["a_hash_ladder_route"]["status"] == "BLOCKED_CAPABILITY"
    assert matrix["a_hash_ladder_route"]["routes_supporting_all"] == []
    intrabar = next(r for r in matrix["routes"] if r["route"].startswith("intrabar"))
    assert intrabar["next_open_entry_fill"]["supported"] is True
    assert intrabar["partial_reduce_only_ladder"]["supported"] is False
    orders = next(r for r in matrix["routes"] if r["route"].startswith("orders"))
    assert orders["partial_reduce_only_ladder"]["supported"] is True
    assert orders["next_open_entry_fill"]["supported"] is False


# --- golden traces -------------------------------------------------------

@pytest.mark.parametrize("alpha_id", ["A-SC", "A-HMA", "A-VWAP", "A-HASH"])
def test_golden_trace_is_reproducible(alpha_id):
    from crypto_regime_lab.alphas.golden import golden_trace

    first = golden_trace(alpha_id)
    second = golden_trace(alpha_id)
    assert first["golden_digest"] == second["golden_digest"]
    assert first["entries"] >= 1
    assert len(first["engine_fills"]) >= 1


@pytest.mark.parametrize("alpha_id", ["A-SC", "A-HMA", "A-VWAP", "A-HASH"])
def test_golden_trace_entry_fills_at_the_next_open(alpha_id):
    from crypto_regime_lab.alphas.golden import GOLDEN_FIXTURES, golden_trace

    trace = golden_trace(alpha_id)
    fixture = GOLDEN_FIXTURES[alpha_id]()
    entries = [f for f in trace["engine_fills"] if f["reason"] == "entry"]
    assert entries
    for fill in entries:
        expected = float(fixture.market.open[fill["bar_index"]])
        # the fill is the bar's open, adjusted only by the configured slippage
        assert abs(fill["price"] - expected) <= abs(expected) * 2e-4 + 1e-9


def test_certification_summary_is_present_and_honest(lab_root):
    path = lab_root / "configs" / "lab02_certification_summary.json"
    if not path.is_file():
        pytest.skip("run scripts/certify_alphas.py")
    doc = json.loads(path.read_text())
    assert set(doc["certifications"]) == {"A-SC", "A-HMA", "A-VWAP", "A-HASH"}
    assert doc["certifications"]["A-HASH"]["status"] == "NOT_READY_SPECIFIC_BLOCKER"
    assert doc["certifications"]["A-HASH"]["blockers"], "a blocker must be specific, never empty"
    assert "never removed from the denominator" in doc["matrix_rule"]
    assert doc["market_optimization_allowed_for"] == doc["ready_for_research"]


def test_not_ready_alpha_keeps_its_cells(lab_root):
    """Guide LAB-02 exit: a blocked alpha is not swapped out or dropped."""
    cert = lab_root / "configs" / "alpha_certification" / "A-HASH.json"
    if not cert.is_file():
        pytest.skip("run scripts/certify_alphas.py")
    doc = json.loads(cert.read_text())
    assert doc["status"] == "NOT_READY_SPECIFIC_BLOCKER"
    assert doc["adapter_version"] == "canonical_v1", "the adapter still exists"
    assert doc["golden_trace_refs"], "and it still has a synthetic suite"
    variant = doc["declared_reduced_fidelity_variant"]
    assert variant["status"] == "AVAILABLE_BUT_NOT_THE_CANONICAL_ALPHA"


def test_legacy_equity_is_diagnostic_only(lab_root):
    from crypto_regime_lab.alphas.a_hash import HashMomentumEventAdapterV1
    from crypto_regime_lab.alphas.base import MarketSlice

    n = 60
    close = np.full(n, 100.0)
    market = MarketSlice(close.copy(), close + 1, close - 1, close, np.full(n, 1000.0))
    adapter = HashMomentumEventAdapterV1(
        dict(mom_len=3, ema_len=5, cooldown_bars=1, stop_loss_perc=2.0, rr_ratio=3.0,
             tp1_ratio=1.0, tp1_qty_perc=50, tp2_ratio=2.0, tp2_qty_perc=50,
             mom_threshold_mult=0.0), market)
    assert "DIAGNOSTIC ONLY" in adapter.legacy_realized_equity.__doc__
    assert "never be used" in adapter.legacy_realized_equity.__doc__
