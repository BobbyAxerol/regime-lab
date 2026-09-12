"""L01.6 tests: the API map must describe the installed engine, not an imagined one."""

from __future__ import annotations

import json

import pytest

quantbt = pytest.importorskip("quantbt")

from crypto_regime_lab.quantbt_bridge import capabilities  # noqa: E402
from crypto_regime_lab.quantbt_bridge.capabilities import (  # noqa: E402
    map_loader_statically, probe_native_capability, probe_wfo_modes,
)


def test_the_v2_binding_map_builder_exists_and_is_callable():
    """This was an unused import doing an existence check silently; say it out loud."""
    assert callable(capabilities.build_api_binding_map_v2)


@pytest.fixture(scope="module")
def api_map(lab_root):
    path = lab_root / "configs" / "api_binding_map.json"
    if not path.is_file():
        pytest.skip("api_binding_map.json not built; run scripts/bootstrap_lab.py")
    return json.loads(path.read_text())


def test_map_is_v2_and_has_no_unresolved_operations(api_map):
    assert api_map["schema"] == "crypto_regime_lab.api_binding_map.v2"
    assert api_map["unresolved"] == []


def test_every_operation_names_a_real_symbol_and_a_test(api_map):
    for operation, record in api_map["operations"].items():
        assert record["status"] == "BOUND", operation
        assert record["bound_symbols"], operation
        assert record["test_coverage"] == "COVERED", f"{operation} has no test reference"


def test_execution_contracts_are_enumerated(api_map):
    assert "event_lifecycle_v3_next_open" in api_map["execution_contracts"]
    assert api_map["guide_target_contract_available"] is True


def test_prepare_market_is_bound(api_map):
    assert "prepare_market_handle_v2" in api_map["operations"]["prepare_market"]["bound_symbols"]


def test_endpoint_surface_is_bound(api_map):
    bound = api_map["operations"]["evaluate_candidate"]["bound_symbols"]
    assert "QuantBTEndpoint" in bound and "EndpointConfig" in bound
    assert bound["QuantBTEndpoint"]["signature"]


def test_replay_surface_is_bound(api_map):
    assert api_map["operations"]["replay_fixed_intents"]["bound_symbols"]


def test_result_export_surface_is_bound(api_map):
    assert api_map["surfaces"]["result_exports"]["bound_count"] >= 15
    assert api_map["surfaces"]["result_exports"]["absent"] == []


def test_all_five_wfo_modes_are_enumerated():
    modes = probe_wfo_modes(quantbt)["optimization_modes_found_in_source"]
    assert modes == [
        "mode_1_decay", "mode_2_sbb", "mode_3_flat_minima",
        "mode_4_is_only_robust", "mode_5_full_robust",
    ], modes


def test_causality_is_resolved_by_the_installed_resolver_not_by_naming():
    """LAB-04 must not guess causality from a mode name (guide 10.1 / T54)."""
    resolution = probe_wfo_modes(quantbt)["causality_resolution"]
    assert resolution, "no (mode, schedule) pair was resolved"
    statuses = {rec["status"] for rec in resolution.values()}
    assert statuses <= {"RESOLVED", "REJECTED"}, statuses
    assert "RESOLVED" in statuses


def test_command_lifecycle_and_callback_surfaces_are_complete(api_map):
    for name in ("command", "lifecycle_and_oco", "callbacks", "wfo", "account_and_instrument"):
        assert api_map["surfaces"][name]["absent"] == [], f"{name}: {api_map['surfaces'][name]['absent']}"


def test_native_capability_matrix_covers_the_required_fixtures():
    """Guide 4.4 fixtures need OCO, amend/cancel, partial reduce, funding, liquidation."""
    native = probe_native_capability(quantbt)
    assert native["missing_required_capabilities"] == []
    assert native["native_event_capability_matrix_version"]
    assert native["native_event_contract_fingerprint"]


def test_loader_is_mapped_statically_without_importing_it(lab_root):
    snapshot = lab_root / "vendor_readonly" / "loader_snapshot" / "data_loader.py"
    if not snapshot.is_file():
        pytest.skip("loader snapshot missing")
    mapped = map_loader_statically(snapshot)
    assert mapped["status"] == "MAPPED_STATICALLY"
    assert "CryptoBinance1m" in mapped["classes"]
    assert tuple(mapped["classes"]["CryptoBinance1m"]["constants"]["NEW_PATH_PARTS"]) == (
        "crypto", "binance_futures", "1m",
    )
    assert "CryptoBinanceSpot1m" in mapped["crypto_readers"]
    import sys

    assert "data_loader" not in sys.modules, "the loader must never be imported"


def test_unknowns_are_listed_rather_than_invented(api_map):
    unknowns = api_map["unknowns"]
    assert unknowns["api"] == [] or all("handling" in u for u in unknowns["api"])
    assert len(unknowns["data"]) >= 5
    assert {u["name"] for u in unknowns["data"]} >= {
        "instrument_registry_digest", "funding_history_coverage", "data_roles",
    }
