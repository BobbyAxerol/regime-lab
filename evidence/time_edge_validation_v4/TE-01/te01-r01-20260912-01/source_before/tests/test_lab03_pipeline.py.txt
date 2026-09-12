"""LAB-03 pipeline tests: inventory, snapshot read-lock, features, scaler,
cohorts and market qualification."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from crypto_regime_lab.data import features as F
from crypto_regime_lab.data import panel as P
from crypto_regime_lab.data.availability import resample_bars
from crypto_regime_lab.data.eligibility import cohort_report, symbol_eligibility
from crypto_regime_lab.data.inventory import PRODUCTS, TRADE_SYMBOLS, build_inventory
from crypto_regime_lab.data.snapshot import (
    DEFAULT_SCOPE,
    classify_source_drift,
    verify_snapshot,
)

STORAGE = "/root/bobby/pool_alpha/alphas_storage/_get_data/storage"


@pytest.fixture(scope="module")
def snapshot_root(lab_root):
    root = lab_root / "snapshots" / "server_core_v1"
    if not (root / "manifest.json").is_file():
        pytest.skip("run scripts/snapshot_data.py")
    return root


@pytest.fixture(scope="module")
def manifest(snapshot_root):
    return json.loads((snapshot_root / "manifest.json").read_text())


@pytest.fixture(scope="module")
def inventory(lab_root):
    path = lab_root / "configs" / "data_product_inventory.json"
    if not path.is_file():
        pytest.skip("run scripts/snapshot_data.py")
    return json.loads(path.read_text())


# --- L03.1 inventory -----------------------------------------------------

def test_inventory_records_what_is_actually_present(inventory):
    products = inventory["products"]
    assert set(products) == set(PRODUCTS)
    assert sorted(products["crypto_binance_futures_1m"]["coverage_by_symbol"]) == sorted(TRADE_SYMBOLS)
    assert products["crypto_binance_spot_1m"]["trade_symbols_absent"] == [
        "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT"]
    assert products["crypto_binance_futures_metrics_5m"]["trade_symbols_absent"] == [
        "SOLUSDT", "BNBUSDT", "DOGEUSDT"]


def test_inventory_does_not_infer_a_dataset_from_a_reader_name(inventory):
    assert "CryptoBinanceSpot1m" in inventory["loader_reader_classes"]
    spot = inventory["products"]["crypto_binance_spot_1m"]
    assert len(spot["coverage_by_symbol"]) == 1, (
        "the loader exposes a spot reader for every symbol; storage has spot for BTCUSDT only"
    )
    assert "never inferred present from the reader name" in " ".join(spot["notes"])


def test_absent_products_are_named_with_their_consequence(inventory):
    absent = inventory["expected_but_absent"]
    assert set(absent) == {"funding_rate_history", "basis_or_mark_price"}
    assert absent["funding_rate_history"]["found"] is False
    assert "never silently zero" in absent["funding_rate_history"]["consequence"]


def test_inventory_is_read_only_and_reproducible(inventory):
    fresh = build_inventory(STORAGE)
    for product_id in PRODUCTS:
        assert sorted(fresh["products"][product_id]["coverage_by_symbol"]) == \
            sorted(inventory["products"][product_id]["coverage_by_symbol"])
        assert fresh["products"][product_id]["read_only_verified"] is True


# --- L03.2 snapshot and the read-lock ------------------------------------

def test_snapshot_scope_matches_measured_coverage(manifest):
    assert manifest["scope"] == DEFAULT_SCOPE
    symbols = {(r["product_id"], r["symbol"]) for r in manifest["files"]}
    assert ("crypto_binance_spot_1m", "ETHUSDT") not in symbols, "absent data is never invented"
    assert len({s for p, s in symbols if p == "crypto_binance_futures_1m"}) == 5


def test_snapshot_is_a_byte_copy_and_originals_are_untouched(manifest):
    assert manifest["copy_mode"] == "byte_copy"
    assert manifest["originals_unmodified"] is True
    assert manifest["source_drift_detected"] == []


def test_read_lock_distinguishes_expected_drift_from_a_real_invalidation(manifest):
    """Three kinds of upstream change, and only one of them invalidates a run.

    Measured here: the trailing month grows (the collector appending) and the
    order-book product rewrites its own partitions (a documented rolling 30-day
    window). Neither is an invalidation.

    Since 2026-09-10 there is also a fourth, real one: the 5m futures-metrics
    product was rewritten upstream across 23 CLOSED partitions spanning 2020-09
    to 2025-08 for BTCUSDT and ETHUSDT. That is a genuine EXTERNAL_DATA_DRIFT and
    it invalidates the G3 cohort that reads that product. It does not touch the
    perpetual 1m bars, which are the only product the primary core reads, so the
    drift is scoped rather than either ignored or inflated into a global stop.
    """
    verification = verify_snapshot(manifest)
    assert verification["snapshot_files_changed"] == [], "the lab's own bytes never change"

    # whatever drifted, it must be attributed to a product and scoped
    for record in verification["closed_partition_drift"]:
        assert record["product_id"] in verification["products_invalidated"]
    for record in verification["rolling_window_drift"]:
        assert record["product_id"] in verification["rolling_window_products"]

    if verification["closed_partition_drift"]:
        assert verification["status"] == "EXTERNAL_DATA_DRIFT"
        assert verification["cohort_runs_invalidated"], (
            "closed-partition drift must name the cohorts it invalidates")
    else:
        assert verification["status"] in ("UNCHANGED", "EXPECTED_MUTABLE_DRIFT_ONLY")

    # the primary core reads the perpetual 1m bars only; it stays valid exactly
    # while none of THOSE closed partitions changed
    assert verification["primary_core_closed_drift"] == [], (
        "a closed partition of a product the primary core reads changed upstream: every primary "
        "run on this snapshot is invalidated and must be re-registered"
    )
    assert verification["primary_run_valid"] is True


def test_metrics_product_drift_is_recorded_and_scoped_to_its_cohort(manifest):
    """The measured 2026-09-10 upstream rewrite must stay visible, not be smoothed away."""
    verification = verify_snapshot(manifest)
    for product, info in verification["drift_by_product"].items():
        assert info["closed_partitions_changed"] > 0
        assert info["in_primary_core"] is False, (
            f"{product} is in the primary core and drifted: the snapshot must be re-registered")
        assert info["symbols"], "drift must name the symbols it touched"


def test_open_partitions_are_excluded_from_a_primary_read(manifest):
    open_parts = [r for r in manifest["files"] if not r["closed"]]
    assert open_parts, "the current month is still open"
    assert manifest["primary_eligibility"]["closed_partitions_only"] is True


def test_every_snapshot_file_carries_its_lock_fields(manifest):
    for record in manifest["files"]:
        assert record["sha256"] and record["rows"] > 0
        assert record["time_min"] and record["time_max"]
        assert isinstance(record["closed"], bool)


# --- L03.4 feature mathematics -------------------------------------------

def test_direction_descriptor_is_bounded_and_signed():
    r = pd.Series([0.01] * 10)
    assert F.direction_descriptor(r, 5).iloc[-1] == pytest.approx(np.sqrt(5), rel=1e-9)
    assert F.direction_descriptor(-r, 5).iloc[-1] == pytest.approx(-np.sqrt(5), rel=1e-9)


def test_path_efficiency_is_one_for_a_straight_move_and_zero_for_a_round_trip():
    straight = pd.Series([0.01] * 8)
    assert F.path_efficiency(straight, 4).iloc[-1] == pytest.approx(1.0, rel=1e-9)
    alternating = pd.Series([0.01, -0.01] * 6)
    assert F.path_efficiency(alternating, 4).iloc[-1] == pytest.approx(0.0, abs=1e-9)


def test_downside_ratio_is_a_share_not_a_probability():
    r = pd.Series([0.01, -0.01, 0.01, -0.01, 0.01, -0.01])
    assert F.downside_ratio(r, 6).iloc[-1] == pytest.approx(0.5, rel=1e-9)
    spec = P.FEATURE_SPECS["g1_downside_ratio_6"]
    assert "not a crash probability" in spec.caveat


def test_delta_log_oi_needs_positive_open_interest():
    oi = pd.Series([100.0, 110.0, 0.0, 120.0])
    out = F.delta_log_oi(oi)
    assert out.iloc[1] == pytest.approx(np.log(1.1), rel=1e-9)
    assert np.isnan(out.iloc[2]) and np.isnan(out.iloc[3])


def test_basis_is_undefined_without_a_spot_price():
    perp = pd.Series([100.0, 101.0])
    spot = pd.Series([100.0, 0.0])
    out = F.basis(perp, spot)
    assert out.iloc[0] == pytest.approx(0.0)
    assert np.isnan(out.iloc[1])


def test_rolling_beta_uses_only_past_observations():
    rng = np.random.default_rng(4)
    market = pd.Series(rng.normal(0, 0.01, 200))
    local = 1.5 * market + rng.normal(0, 0.001, 200)
    beta, residual = F.rolling_beta_and_residual(local, market, 50)
    assert beta.iloc[-1] == pytest.approx(1.5, rel=0.1)
    mutated_market = market.copy()
    mutated_market.iloc[150:] = rng.normal(0, 0.5, 50)
    beta_b, _ = F.rolling_beta_and_residual(local, mutated_market, 50)
    assert np.allclose(beta.iloc[:150].fillna(-9), beta_b.iloc[:150].fillna(-9))


# --- scaler --------------------------------------------------------------

def test_scaler_is_fitted_on_training_and_clips():
    rng = np.random.default_rng(1)
    frame = pd.DataFrame({"time": pd.date_range("2020-01-01", periods=500, freq="4h"),
                          "x": rng.normal(0, 1, 500)})
    scaler = F.RobustScaler(clip=3.0).fit(frame.iloc[:300], ["x"])
    z = scaler.transform(frame)
    assert z["x"].abs().max() <= 3.0
    assert scaler.n_train_ == 300
    assert scaler.as_record()["policy"].endswith("never on the full history")


def test_scaler_drops_a_degenerate_feature_instead_of_amplifying_it():
    frame = pd.DataFrame({"time": pd.date_range("2020-01-01", periods=100, freq="4h"),
                          "flat": np.full(100, 7.0), "live": np.arange(100.0)})
    scaler = F.RobustScaler().fit(frame, ["flat", "live"])
    assert "flat" in scaler.dropped_ and "live" in scaler.active_features
    assert "degenerate" in scaler.dropped_["flat"]


def test_group_weights_neutralise_block_size():
    specs = P.FEATURE_SPECS
    active = ["g1_rv_6", "g1_direction_6", "g1_efficiency_6", "g2_taker_imbalance"]
    weights = F.group_weights(active, specs)
    g1 = sum(w for f, w in weights.items() if specs[f].group == "G1")
    g2 = sum(w for f, w in weights.items() if specs[f].group == "G2")
    assert g1 == pytest.approx(g2), "three G1 features must not outweigh one G2 feature"
    assert sum(weights.values()) == pytest.approx(1.0)


# --- L03.6 cohorts and eligibility ---------------------------------------

def test_cohorts_are_reported_separately_not_intersected(manifest):
    report = cohort_report(manifest, list(TRADE_SYMBOLS), warmup_bars=30)
    cohorts = report["cohorts"]
    assert cohorts["SERVER_CORE_LONG"]["member_count"] == 5
    assert cohorts["SERVER_CORE_SPOT"]["member_count"] == 1
    assert cohorts["SERVER_DERIVATIVES"]["member_count"] == 2
    assert cohorts["SERVER_LIQUIDITY"]["member_count"] == 1
    assert cohorts["FREE_ENRICHED"]["status"] == "EMPTY"
    assert "would shrink the core cohort" in report["no_intersection_collapse"]


def test_common_period_and_per_symbol_history_are_both_reported(manifest):
    report = cohort_report(manifest, list(TRADE_SYMBOLS), warmup_bars=30)
    common = report["five_symbol_common_period"]
    assert common[0].startswith("2020-09-14"), "the common period starts at SOL's listing"
    longest = report["per_symbol_longest_history"]
    assert longest["BTCUSDT"][0].startswith("2020-01-01")
    assert longest["BTCUSDT"][0] < common[0], "BTC has more history than the common period"


def test_first_decision_bar_respects_warmup(manifest):
    eligibility = symbol_eligibility("SOLUSDT", manifest, warmup_bars=30)
    start = pd.Timestamp(eligibility.data_start)
    first = pd.Timestamp(eligibility.first_decision_bar)
    assert first - start == pd.Timedelta("4h") * 30


def test_missing_products_appear_as_symbol_blockers(manifest):
    eligibility = symbol_eligibility("DOGEUSDT", manifest, warmup_bars=30)
    joined = " ".join(eligibility.blockers)
    assert "SERVER_CORE_SPOT" in joined and "SERVER_DERIVATIVES" in joined


# --- L03.4 outputs -------------------------------------------------------

@pytest.fixture(scope="module")
def feature_schema(lab_root):
    path = lab_root / "configs" / "feature_schema.json"
    if not path.is_file():
        pytest.skip("run scripts/build_feature_panels.py")
    return json.loads(path.read_text())


def test_primary_core_respects_the_complexity_budget(feature_schema):
    assert feature_schema["budget_respected"] is True
    assert 8 <= feature_schema["primary_core_count"] <= 12


def test_primary_core_only_contains_features_covering_all_five_symbols(feature_schema):
    coverage = feature_schema["coverage_by_feature"]
    for name in feature_schema["primary_core_features"]:
        assert coverage[name]["covers_all_five"] is True, name
        assert coverage[name]["tier"] == "primary_core"


def test_partial_coverage_features_are_extensions_not_core(feature_schema):
    coverage = feature_schema["coverage_by_feature"]
    assert coverage["g3_dlog_oi"]["symbols_with_any_data"] == ["BTCUSDT", "ETHUSDT"]
    assert coverage["g3_dlog_oi"]["tier"] == "derivatives_extension"
    assert coverage["g3_basis"]["symbols_with_any_data"] == ["BTCUSDT"]


def test_raw_aggregates_are_retained_beside_the_z_scores(lab_root, feature_schema):
    panels = json.loads((lab_root / "configs" / "feature_schema.json").read_text())
    assert panels["intermediate_aggregates_retained"] is True
    path = lab_root / "snapshots" / "server_core_v1" / "panels" / "BTCUSDT.parquet"
    if not path.is_file():
        pytest.skip("panels not built")
    frame = pd.read_parquet(path)
    raw = [c for c in frame.columns if not c.startswith("z_")]
    standardised = [c for c in frame.columns if c.startswith("z_")]
    assert raw and standardised
    for name in feature_schema["primary_core_features"]:
        assert name in raw and f"z_{name}" in standardised


def test_availability_rules_declare_the_derived_bar_close(lab_root):
    path = lab_root / "configs" / "availability_rules.json"
    if not path.is_file():
        pytest.skip("run scripts/build_feature_panels.py")
    doc = json.loads(path.read_text())
    for product in doc["products"].values():
        assert "derived" in product["bar_close_rule"]
        assert product["available_at_rule"] == "bar_close + publication_delay"
    assert doc["resampling"]["level_columns"].startswith("open interest and ratios take the LAST")
    assert doc["funding"]["status"] == "MISSING"


# --- L03.7 qualification --------------------------------------------------

@pytest.fixture(scope="module")
def qualification(lab_root):
    path = lab_root / "configs" / "market_qualification.json"
    if not path.is_file():
        pytest.skip("run scripts/qualify_market_adapters.py")
    return json.loads(path.read_text())


def test_qualification_runs_every_cell_including_the_blocked_alpha(qualification):
    assert qualification["cells_attempted"] == 20
    alphas = {r["alpha_id"] for r in qualification["results"]}
    assert alphas == {"A-SC", "A-HMA", "A-VWAP", "A-HASH"}
    assert qualification["not_ready_alphas"] == ["A-HASH"]


def test_qualification_is_development_role_only(qualification):
    assert qualification["data_role"] == "development"
    for record in qualification["results"]:
        assert record["data_role"] == "development"
        assert record["not_model_selection"] is True


def test_qualified_cells_produce_a_finite_account_trace(qualification):
    qualified = [r for r in qualification["results"] if r["status"] == "QUALIFIED"]
    assert qualified, "at least one cell must qualify"
    for record in qualified:
        assert record["checks"]["account_trace_finite"] is True
        assert record["checks"]["no_intent_during_warmup"] is True
        assert record["checks"]["account_trace_bars"] == record["bars"]


def test_ratio_features_are_undefined_on_a_flat_window():
    """Guide 6.4: zero dispersion is missing, never silently strong evidence."""
    flat = pd.Series(np.zeros(10))
    assert np.isnan(F.direction_descriptor(flat, 5).iloc[-1])
    assert np.isnan(F.path_efficiency(flat, 5).iloc[-1])
    assert np.isnan(F.downside_ratio(flat, 5).iloc[-1])
    assert np.isnan(F.jump_concentration(flat, 5).iloc[-1])
    assert F.realized_vol(flat, 5).iloc[-1] == 0.0, "realized vol of a flat window IS zero"


# --- instrument registry and the minimum economic effect ------------------

@pytest.fixture(scope="module")
def instrument_registry(lab_root):
    path = lab_root / "configs" / "instrument_registry.json"
    if not path.is_file():
        pytest.skip("run scripts/close_lab01_blockers.py")
    return json.loads(path.read_text())


def test_instrument_registry_is_inferred_from_measured_granularity(instrument_registry):
    instruments = instrument_registry["instruments"]
    assert set(instruments) == set(TRADE_SYMBOLS)
    assert instruments["BTCUSDT"]["qty_steps_observed"] == [0.001]
    assert instruments["DOGEUSDT"]["qty_steps_observed"] == [1.0]
    assert instrument_registry["registry_digest"]


def test_registry_records_the_symbol_whose_step_changed(instrument_registry):
    assert instrument_registry["quantity_step_unstable_symbols"] == ["SOLUSDT"]
    sol = instrument_registry["instruments"]["SOLUSDT"]
    assert sol["qty_step_stable"] is False
    assert len(sol["qty_steps_observed"]) > 1
    assert "would be wrong for a symbol whose step changed" in instrument_registry["policy"]


def test_registry_uses_the_conservative_step(instrument_registry):
    for symbol, rec in instrument_registry["instruments"].items():
        if rec["qty_steps_observed"]:
            assert rec["conservative_qty_step"] == max(rec["qty_steps_observed"]), symbol


@pytest.fixture(scope="module")
def minimum_effect(lab_root):
    path = lab_root / "configs" / "minimum_economic_effect.json"
    if not path.is_file():
        pytest.skip("run scripts/close_lab01_blockers.py")
    return json.loads(path.read_text())


def test_minimum_effect_is_derived_from_cost_uncertainty_not_from_a_result(minimum_effect):
    derivation = minimum_effect["derivation"]
    assert derivation["round_trip_cost"] == pytest.approx(2 * (0.0004 + 0.0001))
    assert derivation["cost_uncertainty_per_round_trip"] == pytest.approx(
        derivation["round_trip_cost"] * (2.0 - 1.0))
    expected = (derivation["cost_uncertainty_per_round_trip"]
                * derivation["busiest_alpha_round_trips_per_day"])
    assert minimum_effect["minimum_daily_net_return_difference"] == pytest.approx(expected)
    assert minimum_effect["registered_before_any_arm_comparison"] is True
    assert "can never be chosen to fit an observed delta" in minimum_effect["rule"]


def test_study_registration_has_no_remaining_blockers(lab_root):
    study = json.loads((lab_root / "configs" / "study_registration.json").read_text())
    assert study["status"] == "REGISTERED_DATA_PINNED"
    assert study["data_roles"] is not None
    assert study["execution"]["instrument_registry_digest"]
    assert study["minimum_economic_effect"] is not None
    leftovers = [k for k in study if k.endswith("_blocker")]
    leftovers += [k for k in study["execution"] if k.endswith("_blocker")]
    assert leftovers == [], leftovers


def test_registration_records_funding_as_missing_not_zero(lab_root):
    study = json.loads((lab_root / "configs" / "study_registration.json").read_text())
    assert study["execution"]["fee_funding_slippage_config"]["funding"] == "MISSING_NOT_ZERO"
    assert "no funding product exists" in \
        study["execution"]["fee_funding_slippage_config"]["funding_evidence"]


def test_data_eligibility_markdown_is_generated_from_artifacts(lab_root):
    path = lab_root / "reports" / "data_eligibility.md"
    if not path.is_file():
        pytest.skip("run scripts/write_data_eligibility_md.py")
    text = path.read_text()
    assert "# Data eligibility — LAB-03" in text
    assert "funding_rate_history" in text
    assert "SERVER_CORE_LONG" in text
    assert "What this does not establish" in text
    assert "no backtest has been run" in text.lower()


# --- L03.1 provenance: docs, configuration and revisions ------------------

@pytest.fixture(scope="module")
def provenance(lab_root):
    path = lab_root / "configs" / "data_provenance.json"
    if not path.is_file():
        pytest.skip("run scripts/build_feature_panels.py")
    return json.loads(path.read_text())


def test_product_docs_were_actually_read(provenance):
    docs = provenance["documents_read"]["product_docs"]
    assert all(rec["found"] for rec in docs.values())
    for rec in docs.values():
        assert rec["sha256"] and rec["lines"] > 0
    assert all(rec["found"] for rec in provenance["documents_read"]["revision_docs"])


def test_absences_are_configuration_not_loss(provenance):
    docs = provenance["documents_read"]["product_docs"]
    spot = docs["crypto_binance_spot_1m"]["documented_config"]
    assert spot["configured_symbols"] == ["BTCUSDT"]
    assert "never configured" in spot["consequence"]
    metrics = docs["crypto_binance_futures_metrics_5m"]["documented_config"]
    assert "SOLUSDT" not in metrics["configured_symbols"]


def test_orderbook_is_a_rolling_window_and_cannot_hold_history(provenance):
    book = provenance["documents_read"]["product_docs"][
        "crypto_binance_orderbook_snapshot_1h"]["documented_config"]
    assert book["lookback_days"] == 30
    assert "ROLLING 30-DAY WINDOW" in book["consequence"]
    assert "can never support a historical study" in book["consequence"]


def test_documentation_matches_the_storage(provenance):
    assert provenance["documentation_matches_storage"] is True
    assert provenance["documentation_mismatches"] == []


def test_the_documented_repair_is_visible_in_the_data(provenance):
    repairs = {(r["symbol"], r["partition"]) for r in provenance["repaired_partitions"]}
    assert ("BTCUSDT", "2026-05") in repairs and ("ETHUSDT", "2026-05") in repairs
    for record in provenance["repaired_partitions"]:
        if record["partition"] == "2026-05":
            assert "2026-06-12" in record["ingest_days"], "the repair ingest day is in the data"
            assert record["rows_from_the_later_ingest"] > 40000


def test_repair_window_is_masked_in_the_panels(lab_root):
    path = lab_root / "snapshots" / "server_core_v1" / "panels" / "BTCUSDT.parquet"
    if not path.is_file():
        pytest.skip("panels not built")
    frame = pd.read_parquet(path)
    assert "in_documented_repair_window" in frame.columns
    masked = frame[frame["in_documented_repair_window"]]
    assert len(masked) > 0
    assert pd.Timestamp(masked["time"].min()) >= pd.Timestamp("2026-05-01")
    assert pd.Timestamp(masked["time"].max()) < pd.Timestamp("2026-06-06")


# --- L03.3 all three resample targets -------------------------------------

def test_all_three_resample_targets_are_produced_and_checked(lab_root):
    path = lab_root / "configs" / "availability_rules.json"
    if not path.is_file():
        pytest.skip("run scripts/build_feature_panels.py")
    doc = json.loads(path.read_text())["resample_verification"]
    assert set(doc["targets"]) == {"15min", "1h", "4h"}
    for target, checks in doc["targets"].items():
        assert checks["volume_sum_matches"], target
        assert checks["open_is_first"] and checks["close_is_last"], target
        assert checks["high_is_max"] and checks["low_is_min"], target
    assert doc["targets"]["15min"]["expected_bars_per_bucket"] == 15
    assert doc["targets"]["1h"]["expected_bars_per_bucket"] == 60
    assert doc["targets"]["4h"]["expected_bars_per_bucket"] == 240


def test_level_columns_are_never_summed_by_the_resampler():
    idx = pd.date_range("2024-01-01", periods=120, freq="5min")
    frame = pd.DataFrame({"time": idx, "symbol": "BTCUSDT",
                          "sum_open_interest": np.arange(120, dtype=float) + 100.0,
                          "source": "test", "ingested_at": idx})
    out = resample_bars(frame, "5min", "1h")
    assert out["sum_open_interest"].iloc[0] == 111.0, "the LAST value of the bucket, never a sum"


# --- exit gate: loader-level future mutation ------------------------------

def test_loader_ignores_a_future_partition(lab_root, manifest, tmp_path):
    """Adding a later partition must not change what an earlier read returned."""
    import shutil

    source = lab_root / "snapshots" / "server_core_v1" / "crypto_binance_futures_1m" / "BTCUSDT"
    partitions = sorted(p for p in source.glob("*.parquet"))[:4]
    staging = tmp_path / "crypto_binance_futures_1m" / "BTCUSDT"
    staging.mkdir(parents=True)
    for path in partitions[:3]:
        shutil.copyfile(path, staging / path.name)

    before = P.load_resampled(tmp_path, "crypto_binance_futures_1m", "BTCUSDT", "4h")
    shutil.copyfile(partitions[3], staging / partitions[3].name)
    after = P.load_resampled(tmp_path, "crypto_binance_futures_1m", "BTCUSDT", "4h")

    assert len(after) > len(before), "the later partition really did add bars"
    pd.testing.assert_frame_equal(before, after.iloc[:len(before)].reset_index(drop=True))


def test_spot_before_the_clean_convention_is_excluded(manifest):
    from crypto_regime_lab.data.eligibility import SPOT_CLEAN_FROM, symbol_eligibility

    eligibility = symbol_eligibility("BTCUSDT", manifest, warmup_bars=30)
    spot = eligibility.products["crypto_binance_spot_1m"]
    assert spot["storage_time_min"].startswith("2018-01-01"), "storage really does go back to 2018"
    assert spot["eligible_time_min"] == SPOT_CLEAN_FROM
    assert spot["pre_convention_data_excluded"] is True


def test_market_universe_cannot_be_widened_on_this_storage(inventory):
    """Guide 6.2 allows a wider market-context universe; this storage has no wider one."""
    universe = inventory.get("market_universe")
    if universe is None:
        pytest.skip("re-run scripts/snapshot_data.py")
    assert sorted(universe["perpetual_symbols"]) == sorted(TRADE_SYMBOLS)
    assert universe["wider_universe_available"] == []
    assert universe["can_widen_market_context"] is False
    assert universe["quarterly_contract_count"] > 40
    assert "expiries of the same underlyings" in universe["consequence"]


# --- L03.2 deep read-lock: what a digest cannot tell you ------------------


def _write_pair(tmp_path, lab_rows, upstream_rows):
    """Two parquet files standing in for the lab copy and the upstream original."""
    lab = tmp_path / "lab.parquet"
    upstream = tmp_path / "upstream.parquet"
    pd.DataFrame(lab_rows).to_parquet(lab)
    pd.DataFrame(upstream_rows).to_parquet(upstream)
    return {"snapshot_path": str(lab), "source_path": str(upstream),
            "product_id": "crypto_binance_futures_metrics_5m", "symbol": "BTCUSDT",
            "partition": "2021-01"}


_BASE = {"time": pd.to_datetime(["2021-01-01 00:00", "2021-01-01 00:05"]),
         "sum_open_interest": [10.0, 11.0], "source": ["s", "s"],
         "ingested_at": pd.to_datetime(["2026-01-01", "2026-01-01"])}


def test_deep_read_lock_calls_a_pure_ingest_restamp_what_it_is(tmp_path):
    """Only ``ingested_at`` moved. The numbers this study read are still the numbers upstream holds."""
    later = {**_BASE, "ingested_at": pd.to_datetime(["2026-09-10", "2026-09-10"])}
    verdict = classify_source_drift(_write_pair(tmp_path, _BASE, later))
    assert verdict["classification"] == "VINTAGE_RESTAMP_ONLY"
    assert verdict["vintage_columns_that_moved"] == ["ingested_at"]
    assert verdict["rows_compared"] == 2


def test_deep_read_lock_still_calls_a_changed_measurement_a_revision(tmp_path):
    """A moved value is a revision even when the vintage moved too — the read decides, not the stamp."""
    revised = {**_BASE, "sum_open_interest": [10.0, 11.5],
               "ingested_at": pd.to_datetime(["2026-09-10", "2026-09-10"])}
    verdict = classify_source_drift(_write_pair(tmp_path, _BASE, revised))
    assert verdict["classification"] == "CONTENT_REVISION"
    assert "sum_open_interest" in verdict["changed_columns"]
    assert verdict["changed_columns"]["sum_open_interest"]["rows_differing"] == 1


@pytest.mark.parametrize("upstream, expected_reason", [
    ({"time": pd.to_datetime(["2021-01-01 00:00"]), "sum_open_interest": [10.0],
      "source": ["s"], "ingested_at": pd.to_datetime(["2026-01-01"])}, "row count"),
    ({"time": pd.to_datetime(["2021-01-01 00:00", "2021-01-01 00:05"]),
      "sum_open_interest": [10.0, 11.0], "ingested_at": pd.to_datetime(["2026-01-01", "2026-01-01"])},
     "column set"),
])
def test_deep_read_lock_refuses_to_clear_anything_it_cannot_prove(tmp_path, upstream, expected_reason):
    """A dropped row or a dropped column is not a re-stamp. The benign verdict carries the burden of proof."""
    verdict = classify_source_drift(_write_pair(tmp_path, _BASE, upstream))
    assert verdict["classification"] == "CONTENT_REVISION"
    assert expected_reason in verdict["reason"]


def test_deep_read_lock_treats_an_unreadable_upstream_file_as_a_revision(tmp_path):
    record = _write_pair(tmp_path, _BASE, _BASE)
    Path(record["source_path"]).write_bytes(b"not a parquet file")
    verdict = classify_source_drift(record)
    assert verdict["classification"] == "CONTENT_REVISION"
    assert "could not be read" in verdict["reason"]


def test_measured_metrics_drift_is_a_restamp_and_the_shallow_check_still_fails_closed(manifest):
    """The real 23-partition rewrite, classified by reading both files rather than by digest.

    Measured 2026-09-10: every one of the 23 CLOSED ``binance_futures_metrics_5m``
    partitions that drifted has identical measurements; only ``ingested_at``
    moved, because the collector re-ingests closed months. The shallow verdict
    must stay ``EXTERNAL_DATA_DRIFT`` so the read-lock is never weakened by
    default, and the deep verdict must name what the drift actually was.
    """
    shallow = verify_snapshot(manifest)
    deep = verify_snapshot(manifest, deep=True)
    assert deep["closed_partition_drift_classified"] is True
    assert shallow["closed_partition_drift_classified"] is False

    if not shallow["closed_partition_drift"]:
        pytest.skip("no closed-partition drift upstream right now")

    assert shallow["status"] == "EXTERNAL_DATA_DRIFT", "shallow must stay fail-closed"
    revisions = deep["closed_partition_content_revisions"]
    restamps = deep["closed_partition_vintage_restamps"]
    assert len(revisions) + len(restamps) == len(shallow["closed_partition_drift"])
    for verdict in restamps:
        assert verdict["vintage_columns_that_moved"] == ["ingested_at"]
        assert verdict["rows_compared"] > 0
    # a cohort is cleared only when every one of its drifted partitions was proven benign
    for product in deep["cohort_runs_invalidated"]:
        assert any(v["product_id"] == product for v in revisions), (
            f"{product} is invalidated but no partition of it was proven to be a content revision")
    if not revisions:
        assert deep["status"] == "EXTERNAL_VINTAGE_RESTAMP_ONLY"
        assert deep["cohort_runs_invalidated"] == []


def test_data_eligibility_reproduces_from_the_pinned_manifest(lab_root, manifest):
    """The eligibility document must be derivable from the snapshot it names.

    server_core_v1 was read three times while the collector was appending to the
    open 2026-09 partitions, and the first version of this artifact was written
    from the 20:03:51 pass while the study pins 20:15:47 -- naming a snapshot it
    did not come from and under-counting every symbol by 7-9 rows. No closed
    partition differed and no result moved, but "the artifact reports its own
    inputs correctly" is the property, not "the difference was small".
    """
    path = lab_root / "configs" / "data_eligibility.json"
    if not path.is_file():
        pytest.skip("run scripts/build_feature_panels.py")
    stored = json.loads(path.read_text())

    assert stored["snapshot_id"] == manifest["snapshot_id"]
    assert stored["manifest_ingest_finished_utc"] == manifest["ingest_finished_utc"], (
        "the eligibility report was built from a different read of this snapshot; "
        "run scripts/refresh_data_eligibility.py")
    assert stored["manifest_total_rows"] == manifest["total_rows"]

    rebuilt = cohort_report(manifest, list(stored["per_symbol"]), stored["warmup_bars"])
    for symbol, record in stored["per_symbol"].items():
        for product, entry in record["products"].items():
            fresh = rebuilt["per_symbol"][symbol]["products"][product]
            assert entry["rows"] == fresh["rows"], f"{symbol}/{product} row count is stale"
            assert entry["partitions"] == fresh["partitions"]
            assert entry["closed_partitions"] == fresh["closed_partitions"]
            assert entry["time_min"] == fresh["time_min"]
            assert entry["time_max"] == fresh["time_max"]


def test_eligibility_row_counts_match_the_parquet_files_themselves(lab_root, manifest):
    """Not just manifest-consistent: consistent with the bytes on disk.

    The manifest could itself be wrong. This reads ``num_rows`` out of the
    parquet footers of the lab's own copies and checks the published totals
    against them, so the reported data length is anchored to files rather than
    to a chain of JSON documents.
    """
    import pyarrow.parquet as pq

    path = lab_root / "configs" / "data_eligibility.json"
    if not path.is_file():
        pytest.skip("run scripts/build_feature_panels.py")
    stored = json.loads(path.read_text())

    by_key: dict[tuple[str, str], int] = {}
    for record in manifest["files"]:
        key = (record["symbol"], record["product_id"])
        by_key[key] = by_key.get(key, 0) + pq.ParquetFile(record["snapshot_path"]).metadata.num_rows

    for symbol, record in stored["per_symbol"].items():
        for product, entry in record["products"].items():
            assert entry["rows"] == by_key[(symbol, product)], (
                f"{symbol}/{product}: the published row count does not match the parquet footers")


# --- L03.1 the loader is READ, never CALLED -------------------------------


@pytest.fixture(scope="module")
def loader_parity(lab_root):
    path = lab_root / "configs" / "loader_endpoint_parity.json"
    if not path.is_file():
        pytest.skip("run scripts/verify_loader_parity.py")
    return json.loads(path.read_text())


def test_the_pinned_loader_is_never_imported_by_the_lab_runtime(lab_root):
    """No module under src/ may import or execute the vendored loader.

    The loader tells the lab WHERE each product lives. If a runtime module ever
    called it, the volume truncation measured below would enter the features
    through the back door, so the boundary is asserted rather than assumed.
    """
    offenders = []
    for path in (lab_root / "src").rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "loader_snapshot" in text and "sha256" not in text and "map_loader" not in text:
            offenders.append(str(path.relative_to(lab_root)))
        if "import data_loader" in text or "from data_loader" in text:
            offenders.append(str(path.relative_to(lab_root)))
    assert offenders == [], f"the lab runtime reaches for the loader in {offenders}"


def test_loader_parity_artifact_covers_every_traded_symbol(loader_parity):
    covered = {r["symbol"] for r in loader_parity["per_symbol"]}
    assert covered == set(TRADE_SYMBOLS), (
        "a fixed calendar month would have skipped the late-listing symbols, which are exactly "
        f"the ones whose stored dtype differs; covered={sorted(covered)}")
    assert all(r["status"] == "COMPARED" for r in loader_parity["per_symbol"])


def test_loader_endpoint_parity_artifact_matches_a_live_call(loader_parity, lab_root):
    """Re-run one recorded comparison against the loader and the parquet right now.

    The report cites this artifact for a claim about a third-party endpoint, so
    the artifact has to be reproducible rather than a remembered measurement.
    """
    import importlib.util
    import sys
    import types

    sys.dont_write_bytecode = True                    # never leave bytecode in a protected tree
    source = lab_root / "vendor_readonly" / "loader_snapshot" / "data_loader.py"
    from crypto_regime_lab.safety.paths import sha256_file
    assert sha256_file(source) == loader_parity["loader_snapshot_sha256"], (
        "the pinned loader changed; the parity artifact describes a different file")

    stub = types.ModuleType("loaders.deribit_options")
    for name in ("DeribitOptionOverlayLoader", "DeribitOptionSnapshots5mLoader",
                 "DeribitOptionTradesLoader"):
        setattr(stub, name, type(name, (), {}))
    package = types.ModuleType("loaders")
    package.__path__ = []
    sys.modules.setdefault("loaders", package)
    sys.modules.setdefault("loaders.deribit_options", stub)

    spec = importlib.util.spec_from_file_location("pinned_data_loader_test", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.STORAGE_DIR = Path(loader_parity["storage_root"])

    record = next(r for r in loader_parity["per_symbol"] if r["columns_differing"])
    stored = (lab_root / "snapshots" / "server_core_v1" / "crypto_binance_futures_1m"
              / record["symbol"] / f"{record['partition']}.parquet")
    raw = pd.read_parquet(stored).sort_values("time").reset_index(drop=True)
    served = module.CryptoBinance1m().load(
        symbols=record["symbol"], start_date=str(raw["time"].min()),
        end_date=str(raw["time"].max()), columns="full", check_val=False
    ).sort_values("time").reset_index(drop=True)

    assert len(served) == len(raw) == record["rows"]
    assert str(raw["volume"].dtype) == record["stored_volume_dtype"]
    assert str(served["volume"].dtype) == "int64", (
        "the endpoint no longer casts volume; the artifact's finding is out of date")
    differing = int((raw["volume"].astype("float64") != served["volume"].astype("float64")).sum())
    assert differing == record["columns_differing"]["volume"]["rows_differing"]
    assert int(((raw["volume"].astype("float64") > 0) & (served["volume"] == 0)).sum()) == \
        record["bars_a_cast_would_zero"]
    for column in ("open", "high", "low", "close", "quote_volume", "number_of_trades"):
        assert raw[column].equals(served[column]), (
            f"{column} now differs too; the parity artifact understates the gap")


def test_the_data_sources_report_exists_and_matches_the_pinned_snapshot(lab_root, manifest):
    """The audit view of the raw data must be present and current.

    The user's question -- "which historical data, how long, and can I trust the
    raw bars" -- has one answer document. A stale one is worse than none, so the
    headline figures are checked against the manifest they claim to describe.
    """
    path = lab_root / "reports" / "data_sources_used.md"
    if not path.is_file():
        pytest.skip("run scripts/write_data_sources_report.py")
    text = path.read_text()
    assert f"{manifest['file_count']} files" in text
    assert f"{manifest['total_rows']:,} rows" in text
    assert manifest["storage_root"] in text
    for phrase in ("no network, no collector, no repair job",
                   "Which phase consumed which slice",
                   "Re-derive every number on this page"):
        assert phrase in text, f"the report no longer states: {phrase}"
