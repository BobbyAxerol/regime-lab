"""Probe the *installed* QuantBT and build ``api_binding_map.json`` (guide L01.6).

Nothing here asserts that an API exists. Every lab operation is mapped to a real
symbol found by introspection, or recorded as ``UNKNOWN`` / ``BLOCKED_CAPABILITY``
with the reason. Unknown is never filled in with an imagined API.
"""

from __future__ import annotations

import importlib
import importlib.metadata as md
import inspect
from dataclasses import dataclass
from typing import Any

from ..safety.paths import sha256_file

# Lab operation -> candidate installed symbols (guide 4.4 facade).
LAB_OPERATION_CANDIDATES: dict[str, tuple[str, ...]] = {
    "inspect_installed_contracts": ("EXECUTION_CONTRACT_REGISTRY", "get_execution_contract", "EVENT_CLOCK_CONTRACTS", "get_event_clock_contract", "walkforward_support_matrix"),
    "prepare_market": ("prepare_market_handle_v2", "PreparedMarketHandleV2", "prepare_market_tape", "prepare_instrument_registry_v2", "compile_instrument_table"),
    "evaluate_candidate": ("QuantBTEndpoint", "EndpointConfig", "BacktestResult", "GenericEndpointEvaluator"),
    "run_continuous": ("WalkForwardEngine", "WalkForwardConfig", "WalkForwardResult", "ReactivePreparedWfoRuntimeV1", "prepare_reactive_wfo_strategy"),
    "replay_fixed_intents": ("FillReplayTapeV2", "run_fill_replay_kernel", "TraceReplayer", "IntrabarIntentTape"),
    "export_required_artifacts": ("ResearchAuditWriterV1", "ResearchRetentionPlanV1", "build_canonical_execution_trace", "metrics_from_result"),
}

# Symbols the lab must understand before LAB-04/05 because they already implement
# a regime notion inside QuantBT (the thing this lab is asked to test around).
INCUMBENT_REGIME_SYMBOLS: tuple[str, ...] = (
    "volatility_regime_labels",
    "WalkForwardConfig",
    "RobustSelectionConfig",
    "CandidateSelector",
    "select_flat_minima_record",
    "select_full_sample_robust_record",
    "select_is_only_robust_record",
    "select_is_plateau_robust_record",
    "stationary_bootstrap_sharpes",
    "resolve_causality_schedule_v2",
)


def _describe(obj: Any) -> dict:
    record: dict[str, Any] = {"kind": type(obj).__name__}
    try:
        record["signature"] = str(inspect.signature(obj))
    except (TypeError, ValueError):
        record["signature"] = None
    doc = inspect.getdoc(obj)
    record["doc_first_line"] = doc.splitlines()[0] if doc else None
    module = getattr(obj, "__module__", None)
    record["module"] = module
    try:
        record["defined_in"] = inspect.getsourcefile(obj)
        _src, lineno = inspect.getsourcelines(obj)
        record["source_line"] = lineno
    except (TypeError, OSError):
        record["defined_in"] = None
        record["source_line"] = None
    if isinstance(obj, dict):
        record["dict_keys"] = sorted(str(k) for k in obj)
    if isinstance(obj, (str, int, float, bool)):
        record["value"] = obj
    if hasattr(obj, "__dataclass_fields__"):
        record["dataclass_fields"] = sorted(obj.__dataclass_fields__)
    return record


@dataclass
class InstalledQuantBT:
    module: Any
    distributions: dict[str, str | None]

    @classmethod
    def load(cls) -> "InstalledQuantBT":
        module = importlib.import_module("quantbt")
        dists: dict[str, str | None] = {}
        for name in ("quantbt-engine", "quantbt-native"):
            try:
                dists[name] = md.version(name)
            except Exception:
                dists[name] = None
        return cls(module=module, distributions=dists)

    def identity(self) -> dict:
        module_file = getattr(self.module, "__file__", None)
        record = {
            "import_origin": module_file,
            "module_version_attr": getattr(self.module, "__version__", None),
            "distributions": self.distributions,
            "public_symbol_count": len([n for n in dir(self.module) if not n.startswith("_")]),
        }
        if module_file:
            record["init_sha256"] = sha256_file(module_file)
        try:
            native = importlib.import_module("quantbt_native")
            record["native_import_origin"] = getattr(native, "__file__", None)
        except Exception as exc:
            record["native_import_origin"] = None
            record["native_import_error"] = f"{type(exc).__name__}: {exc}"
        return record


def build_api_binding_map(installed: InstalledQuantBT | None = None) -> dict:
    """Map each lab operation onto symbols that actually exist in this install."""
    installed = installed or InstalledQuantBT.load()
    module = installed.module
    operations: dict[str, dict] = {}
    for operation, candidates in LAB_OPERATION_CANDIDATES.items():
        bound, missing = {}, []
        for name in candidates:
            if hasattr(module, name):
                bound[name] = _describe(getattr(module, name))
            else:
                missing.append(name)
        operations[operation] = {
            "status": "BOUND" if bound else "UNKNOWN",
            "bound_symbols": bound,
            "absent_candidates": missing,
            "note": None if bound else "no installed symbol found; do not invent one",
        }
    incumbent = {
        name: _describe(getattr(module, name))
        for name in INCUMBENT_REGIME_SYMBOLS
        if hasattr(module, name)
    }
    absent_incumbent = [n for n in INCUMBENT_REGIME_SYMBOLS if not hasattr(module, n)]
    return {
        "schema": "crypto_regime_lab.api_binding_map.v1",
        "installed": installed.identity(),
        "execution_contracts": sorted(getattr(module, "EXECUTION_CONTRACT_REGISTRY", {})),
        "event_clock_contracts": sorted(getattr(module, "EVENT_CLOCK_CONTRACTS", {})),
        "guide_target_contract": getattr(module, "EVENT_LIFECYCLE_V3_NEXT_OPEN", None),
        "guide_target_contract_available": hasattr(module, "EVENT_LIFECYCLE_V3_NEXT_OPEN"),
        "operations": operations,
        "incumbent_regime_surface": incumbent,
        "incumbent_regime_absent": absent_incumbent,
        "unresolved": [op for op, rec in operations.items() if rec["status"] != "BOUND"],
    }


# =====================================================================
# L01.6 completion: WFO modes, command/callback/OCO surface, result
# exports, native capability, loader static map, unknowns register.
# =====================================================================

WFO_SURFACE_SYMBOLS: tuple[str, ...] = (
    "WalkForwardConfig", "WalkForwardEngine", "WalkForwardResult", "WalkForwardFold",
    "WalkForwardTrialRecord", "WalkForwardCompatibilityEntry", "walkforward_support_matrix",
    "WfoCausalityScheduleV2", "resolve_causality_schedule_v2", "WfoIntentContractV1",
    "WfoIntentKindV1", "WFO_CONTRACT_SCHEMA_V1", "FoldAccountPolicyV1", "FoldWarmupPolicyV1",
)
COMMAND_SURFACE_SYMBOLS: tuple[str, ...] = (
    "OrderCommand", "OrderIntent", "OrderAction", "OrderSide", "OrderType", "TimeInForce",
    "CommandWriter", "CommandBatchView", "CommandOutcome", "CommandValidationError",
    "BracketOrderSpec", "build_bracket_order_plan", "StructuredOrderPlan",
    "order_intents_to_lifecycle_commands", "OrderActivationPolicy",
)
LIFECYCLE_SURFACE_SYMBOLS: tuple[str, ...] = (
    "LifecycleEventKind", "LifecycleModel", "LifecycleModelKind", "LifecycleOrderStatus",
    "LifecycleTransition", "lifecycle_transitions", "validate_lifecycle_transition",
    "StrategyLifecycleV1", "ProtectiveExitReentryPolicy", "StopGapPolicy", "TakeProfitGapPolicy",
    "TrailingUpdatePhase", "FillPhase", "FillDecision", "Fill", "IntrabarFill",
)
CALLBACK_SURFACE_SYMBOLS: tuple[str, ...] = (
    "CallbackSchedule", "StrategyCallbackError", "StrategyContextView", "StrategyContextRequirements",
    "MaterializedStrategyContext", "NativeStrategyContext", "StaleStrategyContextError",
    "WakePlanV1", "WakeReasonV1", "wake_reason_names", "CandidateWakePlansV1",
    "EarlyStoppingCallback", "SingleObjectiveEarlyStopping", "logging_callback",
)
RESULT_EXPORT_SYMBOLS: tuple[str, ...] = (
    "BacktestResult", "BacktestResultV2", "metrics_from_result", "metric_from_result",
    "result_full_report", "full_report", "format_metrics_report", "strategy_return_series",
    "build_canonical_execution_trace", "CanonicalTraceArtifact", "canonical_trace_fingerprint",
    "compare_canonical_traces", "TraceReplayer", "TraceReplayResult", "TRACE_FIELDS",
    "TRACE_SCHEMA_VERSION", "ResearchAuditWriterV1", "ResearchAuditArtifactV1",
    "ResearchRetentionPlanV1", "certify_result_metadata",
)
ACCOUNT_SURFACE_SYMBOLS: tuple[str, ...] = (
    "AccountConfig", "ExecutionConfig", "EndpointConfig", "MarginMode", "MarginModel",
    "FeeModel", "CostModel", "CarryModel", "SizingPolicy", "InstrumentSpec",
    "InstrumentRegistryV2", "compile_instrument_table", "QuantityConstraints",
    "build_quantity_constraints", "quantize_order_value",
)
NATIVE_CAPABILITY_SYMBOLS: tuple[str, ...] = (
    "NATIVE_EVENT_CAPABILITY_MATRIX", "NATIVE_EVENT_CAPABILITY_MATRIX_VERSION",
    "NATIVE_EVENT_CONTRACT_FINGERPRINT", "NATIVE_EVENT_CORE_PROTOCOL_VERSION",
    "NATIVE_EVENT_COMMAND_ABI_VERSION", "NATIVE_EVENT_SEMANTIC_DESCRIPTOR_VERSION",
    "native_event_capability_matrix", "native_event_semantic_descriptor",
    "capability_matrix_fingerprint", "semantic_descriptor_fingerprint",
    "validate_native_event_capability_matrix", "assert_native_event_full_parity",
)

# Which lab test currently exercises each mapped operation. "None" is honest:
# it means the binding is recorded but not yet covered by a test.
OPERATION_TEST_REFS: dict[str, list[str]] = {
    "inspect_installed_contracts": [
        "tests/test_incumbent_regime_surface.py::test_target_execution_contract_exists_in_this_install",
        "tests/test_lab01_api_map.py::test_execution_contracts_are_enumerated",
    ],
    "prepare_market": ["tests/test_lab01_api_map.py::test_prepare_market_is_bound"],
    "evaluate_candidate": ["tests/test_lab01_api_map.py::test_endpoint_surface_is_bound"],
    "run_continuous": ["tests/test_lab01_api_map.py::test_all_five_wfo_modes_are_enumerated"],
    "replay_fixed_intents": ["tests/test_lab01_api_map.py::test_replay_surface_is_bound"],
    "export_required_artifacts": ["tests/test_lab01_api_map.py::test_result_export_surface_is_bound"],
}


def _surface(module: Any, names: tuple[str, ...]) -> dict:
    bound = {n: _describe(getattr(module, n)) for n in names if hasattr(module, n)}
    absent = [n for n in names if not hasattr(module, n)]
    return {"bound": bound, "absent": absent, "bound_count": len(bound)}


def probe_wfo_modes(module: Any) -> dict:
    """Enumerate the real optimization modes and how each resolves causally.

    ``resolve_causality_schedule_v2`` is the installed authority on whether a
    (mode, schedule) pair is causal; guessing that from names is exactly the
    LAB-04 mistake the guide warns about.
    """
    import re

    try:
        import quantbt.walkforward as wf_mod

        source = inspect.getsource(wf_mod)
        modes = sorted(set(re.findall(r'"(mode_\d[a-z_0-9]*)"', source)))
    except (ImportError, OSError):
        modes = []
    schedules = ("global", "per_fold", "per_fold_decay")
    resolution: dict[str, dict] = {}
    resolver = getattr(module, "resolve_causality_schedule_v2", None)
    for mode in modes + ["none"]:
        for schedule in schedules:
            key = f"{mode}|{schedule}"
            if resolver is None:
                resolution[key] = {"status": "UNKNOWN", "reason": "resolver symbol absent"}
                continue
            try:
                resolved = resolver(optimization_schedule=schedule, optimization_mode=mode)
                resolution[key] = {
                    "status": "RESOLVED",
                    "repr": repr(resolved)[:300],
                    "fields": {
                        f: getattr(resolved, f) for f in getattr(resolved, "__dataclass_fields__", {})
                        if isinstance(getattr(resolved, f), (str, int, float, bool, type(None)))
                    },
                }
            except Exception as exc:
                resolution[key] = {"status": "REJECTED", "error": f"{type(exc).__name__}: {exc}"[:250]}
    support = None
    try:
        support = module.walkforward_support_matrix(as_dataframe=False)
    except Exception as exc:
        support = {"error": f"{type(exc).__name__}: {exc}"}
    return {
        "optimization_modes_found_in_source": modes,
        "optimization_schedules_probed": list(schedules),
        "causality_resolution": resolution,
        "walkforward_support_matrix": support,
        "note": "modes are read from the installed module source; causality comes from the installed resolver, not from naming",
    }


def probe_native_capability(module: Any) -> dict:
    """Probe what the native backend actually supports (L01.3 'native capability được probe')."""
    record: dict[str, Any] = {"symbols": _surface(module, NATIVE_CAPABILITY_SYMBOLS)}
    matrix_fn = getattr(module, "native_event_capability_matrix", None)
    if matrix_fn is not None:
        try:
            matrix = matrix_fn()
            record["capability_matrix"] = {str(k): matrix[k] for k in sorted(matrix)} if hasattr(matrix, "keys") else repr(matrix)[:1000]
        except Exception as exc:
            record["capability_matrix"] = {"error": f"{type(exc).__name__}: {exc}"}
    for const in ("NATIVE_EVENT_CAPABILITY_MATRIX_VERSION", "NATIVE_EVENT_CONTRACT_FINGERPRINT",
                  "NATIVE_EVENT_CORE_PROTOCOL_VERSION", "NATIVE_EVENT_COMMAND_ABI_VERSION",
                  "NATIVE_EVENT_SEMANTIC_DESCRIPTOR_VERSION"):
        record[const.lower()] = getattr(module, const, None)
    # Capabilities the guide's required fixtures depend on (guide 4.4).
    required = ("oco", "amend", "cancel", "limit", "market", "funding", "liquidation",
                "multi_symbol", "ioc", "fok", "gtc", "gtd")
    matrix = record.get("capability_matrix")
    if isinstance(matrix, dict) and "error" not in matrix:
        record["required_fixture_capabilities"] = {
            name: matrix.get(name, "ABSENT_FROM_MATRIX") for name in required
        }
        record["missing_required_capabilities"] = [
            name for name in required if name not in matrix
        ]
    else:
        record["required_fixture_capabilities"] = "UNKNOWN"
        record["missing_required_capabilities"] = "UNKNOWN"
    return record


def map_loader_statically(loader_path) -> dict:
    """Static AST map of the historical data loader snapshot.

    Deliberately does NOT import the module: importing production loader code
    could trigger caching side effects (guide L01.6).
    """
    import ast
    from pathlib import Path as _Path

    path = _Path(loader_path)
    if not path.is_file():
        return {"status": "ABSENT", "path": str(path)}
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    classes: dict[str, dict] = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        attrs: dict[str, Any] = {}
        for stmt in node.body:
            targets = []
            if isinstance(stmt, ast.Assign):
                targets = [t.id for t in stmt.targets if isinstance(t, ast.Name)]
                value = stmt.value
            elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                targets = [stmt.target.id]
                value = stmt.value
            else:
                continue
            for name in targets:
                if name.isupper() and value is not None:
                    try:
                        attrs[name] = ast.literal_eval(value)
                    except (ValueError, SyntaxError):
                        attrs[name] = f"<non-literal: {ast.dump(value)[:80]}>"
        classes[node.name] = {
            "bases": [ast.unparse(b) for b in node.bases],
            "constants": attrs,
            "methods": sorted(s.name for s in node.body if isinstance(s, ast.FunctionDef)),
            "lineno": node.lineno,
        }
    crypto = {n: c for n, c in classes.items()
              if any(k in n for k in ("Crypto", "Binance", "Deribit"))}
    return {
        "status": "MAPPED_STATICALLY",
        "path": str(path),
        "method": "ast.parse of the read-only snapshot; the module was never imported",
        "class_count": len(classes),
        "classes": classes,
        "crypto_readers": sorted(crypto),
        "module_level_constants": {
            n.targets[0].id: ast.literal_eval(n.value)
            for n in tree.body
            if isinstance(n, ast.Assign) and len(n.targets) == 1
            and isinstance(n.targets[0], ast.Name) and n.targets[0].id.isupper()
            and isinstance(n.value, (ast.Constant, ast.Tuple, ast.List))
            and _safe_literal(n.value)
        },
    }


def _safe_literal(node) -> bool:
    import ast

    try:
        ast.literal_eval(node)
        return True
    except (ValueError, SyntaxError):
        return False


def build_api_binding_map_v2(installed: InstalledQuantBT | None = None, loader_path=None) -> dict:
    """Full L01.6 map: operations + surfaces + modes + native + loader + unknowns."""
    installed = installed or InstalledQuantBT.load()
    module = installed.module
    base = build_api_binding_map(installed)

    for operation, record in base["operations"].items():
        record["tests"] = OPERATION_TEST_REFS.get(operation, [])
        record["test_coverage"] = "COVERED" if record["tests"] else "NO_TEST_YET"
        record["version"] = installed.distributions.get("quantbt-engine")

    surfaces = {
        "wfo": _surface(module, WFO_SURFACE_SYMBOLS),
        "command": _surface(module, COMMAND_SURFACE_SYMBOLS),
        "lifecycle_and_oco": _surface(module, LIFECYCLE_SURFACE_SYMBOLS),
        "callbacks": _surface(module, CALLBACK_SURFACE_SYMBOLS),
        "result_exports": _surface(module, RESULT_EXPORT_SYMBOLS),
        "account_and_instrument": _surface(module, ACCOUNT_SURFACE_SYMBOLS),
    }
    native = probe_native_capability(module)
    modes = probe_wfo_modes(module)
    loader = map_loader_statically(loader_path) if loader_path else {"status": "NOT_REQUESTED"}

    unknowns: list[dict] = []
    for surface_name, surface in surfaces.items():
        for absent in surface["absent"]:
            unknowns.append({"kind": "ABSENT_SYMBOL", "surface": surface_name, "name": absent,
                             "handling": "not substituted; any lab need for it becomes BLOCKED_CAPABILITY"})
    for operation, record in base["operations"].items():
        for absent in record["absent_candidates"]:
            unknowns.append({"kind": "ABSENT_CANDIDATE", "operation": operation, "name": absent,
                             "handling": "operation is bound via another symbol; this candidate simply does not exist"})
        if not record["tests"]:
            unknowns.append({"kind": "UNTESTED_BINDING", "operation": operation,
                             "handling": "binding recorded but no lab test exercises it yet"})
    if native.get("missing_required_capabilities") not in ([], "UNKNOWN"):
        unknowns.append({"kind": "MISSING_NATIVE_CAPABILITY",
                         "names": native.get("missing_required_capabilities"),
                         "handling": "guide 4.4 required fixture capability absent -> BLOCKED_CAPABILITY"})

    data_unknowns = [
        {"kind": "DATA_UNKNOWN", "name": "instrument_registry_digest",
         "handling": "tick/lot/min-notional not pinned until LAB-03 reads actual instrument metadata"},
        {"kind": "DATA_UNKNOWN", "name": "funding_history_coverage",
         "handling": "unknown per symbol; missing funding is never treated as zero on a net-carry claim"},
        {"kind": "DATA_UNKNOWN", "name": "perp_listing_dates",
         "handling": "per-symbol evaluation start cannot be fixed until LAB-03 coverage report"},
        {"kind": "DATA_UNKNOWN", "name": "orderbook_snapshot_coverage",
         "handling": "SERVER_LIQUIDITY cohort eligibility unresolved until LAB-03"},
        {"kind": "DATA_UNKNOWN", "name": "data_roles",
         "handling": "discovery/confirmation role assignment blocked on LAB-03 inventory"},
    ]

    base.update({
        "schema": "crypto_regime_lab.api_binding_map.v2",
        "surfaces": surfaces,
        "wfo_modes": modes,
        "native_capability": native,
        "loader_static_map": loader,
        "unknowns": {
            "api": unknowns,
            "data": data_unknowns,
            "policy": "an unknown is listed, never filled with an imagined API or a fabricated default",
        },
        "unknown_counts": {"api": len(unknowns), "data": len(data_unknowns)},
    })
    return base
