"""OUT.2 — integration_binding_map.json: lab hook -> VERIFIED installed symbol.

The rule this file exists to enforce is the LAB-07 exit gate: an unsupported
hook is a BLOCKER or a documented lab patch, and never a silent reroute to a
different contract. A reroute is the dangerous one because it succeeds — the run
completes, the numbers look ordinary, and the economics underneath are not the
ones the study registered.

So every integration point is probed against the INSTALLED package. A point that
resolves is bound with the symbol it resolved to; a point that does not is
recorded as BLOCKED_CAPABILITY with what a lab-side patch would have to add.
"""

from __future__ import annotations

import importlib
from typing import Any

#: lab integration point -> (dotted path on the installed package, why the lab needs it)
INTEGRATION_POINTS: dict[str, dict[str, str]] = {
    "execution_contract": {
        "symbol": "quantbt.QuantBTEndpoint.intrabar_bracket_reference",
        "why": "the one route with next-open entry plus intrabar protective handling",
    },
    "execution_contract_native": {
        "symbol": "quantbt.QuantBTEndpoint.intrabar_bracket_rust",
        "why": "the same contract on the native backend, for L07.1 fixed-intent parity",
    },
    "walkforward": {
        # probed, not assumed: `walkforward` is exported at the package root, not
        # under `quantbt.optimization` where the guide's prose implies it lives
        "symbol": "quantbt.walkforward",
        "why": "the installed calendar WFO that arm A reproduces",
    },
    "walkforward_config": {
        "symbol": "quantbt.WalkForwardConfig",
        "why": "the config object whose modes LAB-04 traced; arm A must pin one of them",
    },
    "walkforward_support_matrix": {
        "symbol": "quantbt.walkforward_support_matrix",
        "why": "declares which modes the install actually supports, instead of assuming five",
    },
    "candidate_selection": {
        "symbol": "quantbt.optimization.candidate_selection",
        "why": "the installed selection rule arm A is labelled against",
    },
    "volatility_regime_labels": {
        "symbol": "quantbt.volatility_regime_labels",
        "why": "the registered M0 comparator (in-sample by construction, never an estimator)",
    },
}

#: Hooks LAB-07 would want and the installed package does not expose. Recorded
#: as blockers with their consequence, never worked around by rerouting.
KNOWN_BLOCKERS: dict[str, dict[str, str]] = {
    "engine_fill_trace_native": {
        "consequence": ("the rust backend exposes no per-fill trace, so Python/Rust parity is "
                        "established on account path and orders, and full event-trace parity is "
                        "never claimed"),
        "lab_patch": "handoff/lab_only_patch.diff would expose the fill vector; NOT applied",
    },
    "scheduler_callback": {
        "consequence": ("the installed engine has no refit-scheduler callback, so the lab drives "
                        "the schedule from OUTSIDE the engine and feeds it fixed intents. The "
                        "engine's economics are untouched, which is the point"),
        "lab_patch": "none needed: driving from outside is the contract-preserving option",
    },
}


def _resolve(dotted: str) -> tuple[Any, str | None]:
    parts = dotted.split(".")
    for split in range(len(parts), 0, -1):
        module_name = ".".join(parts[:split])
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        target: Any = module
        for attribute in parts[split:]:
            if not hasattr(target, attribute):
                return None, f"{module_name} has no attribute {attribute!r}"
            target = getattr(target, attribute)
        return target, None
    return None, f"no importable module prefix in {dotted!r}"


def build_binding_map() -> dict:
    """Probe every integration point against the installed package."""
    import quantbt

    bindings = {}
    for name, spec in INTEGRATION_POINTS.items():
        target, error = _resolve(spec["symbol"])
        bindings[name] = {
            "lab_operation": name,
            "installed_symbol": spec["symbol"],
            "why": spec["why"],
            "status": "BOUND" if target is not None else "BLOCKED_CAPABILITY",
            "resolved_kind": type(target).__name__ if target is not None else None,
            "error": error,
        }
    return {
        "schema": "crypto_regime_lab.integration_binding_map.v1",
        "installed_version": getattr(quantbt, "__version__", None),
        "installed_origin": getattr(quantbt, "__file__", None),
        "bindings": bindings,
        "bound": sorted(n for n, b in bindings.items() if b["status"] == "BOUND"),
        "blocked": sorted(n for n, b in bindings.items() if b["status"] != "BOUND"),
        "known_blockers": KNOWN_BLOCKERS,
        "reroute_policy": (
            "an integration point that does not resolve is BLOCKED_CAPABILITY. It is never "
            "rerouted to a similar-looking symbol: a reroute succeeds, and a run that completes "
            "on economics the study did not register is worse than one that stops"),
        "engine_owns": "matching and accounting",
        "lab_owns": "when a parameter version becomes effective",
    }
