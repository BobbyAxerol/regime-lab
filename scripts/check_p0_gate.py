#!/usr/bin/env python3
"""P0 gate check for TE-03.7 structural controls (read-only).

Validates the four P0 conditions from handoff/TE_PHASE_PLAN_V1.md against
committed artifacts. Never runs the engine, never writes evidence (unless
--out is given for the verdict record). Exits 0 on PASS, 1 on FAIL.
A missing input is a FAIL with a named reason, never an assumption.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
FUNNEL_STEPS = ("valid_observations", "triggers", "searches",
                "different_params", "activated", "different_orders")


def load(path_arg: str | None, name: str, checks: list) -> dict | None:
    if not path_arg:
        checks.append({"check": name, "pass": False,
                       "reason": f"input missing: --{name} not given"})
        return None
    path = Path(path_arg)
    if not path.is_file():
        checks.append({"check": name, "pass": False,
                       "reason": f"input missing: {path} not found"})
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        checks.append({"check": name, "pass": False,
                       "reason": f"input unreadable: {path}: {exc}"})
        return None


def check_funnel(doc: dict | None, checks: list) -> None:
    if doc is None:
        return
    funnel = doc.get("funnel")
    if not isinstance(funnel, dict):
        checks.append({"check": "funnel.present", "pass": False,
                       "reason": "funnel object missing"})
        return
    for step in FUNNEL_STEPS:
        node = funnel.get(step)
        if not isinstance(node, dict):
            checks.append({"check": f"funnel.{step}", "pass": False,
                           "reason": "step missing"})
            continue
        value, denom, reason = node.get("value"), node.get("denominator"), node.get("reason")
        if not isinstance(denom, int) or denom <= 0:
            checks.append({"check": f"funnel.{step}", "pass": False,
                           "reason": f"no denominator (value={value!r})"})
        elif not isinstance(value, int) or value <= 0:
            checks.append({"check": f"funnel.{step}", "pass": False,
                           "reason": f"zero without measured flow (denominator={denom}, reason={reason!r})"})
        else:
            checks.append({"check": f"funnel.{step}", "pass": True,
                           "reason": f"value={value} denominator={denom}"})


def check_selection(doc: dict | None, trials_expected: int, checks: list) -> None:
    if doc is None:
        return
    trials = doc.get("trials")
    if not isinstance(trials, list) or len(trials) != trials_expected:
        got = len(trials) if isinstance(trials, list) else type(trials).__name__
        checks.append({"check": "selection.trials", "pass": False,
                       "reason": f"expected {trials_expected} trials, got {got}"})
        return
    checks.append({"check": "selection.trials", "pass": True,
                   "reason": f"{len(trials)} trials present"})
    bad = [i for i, t in enumerate(trials)
           if not isinstance(t, dict) or not t.get("params")
           or not isinstance(t.get("objective"), (int, float))
           or not math.isfinite(t["objective"])]
    if bad:
        checks.append({"check": "selection.trials_valid", "pass": False,
                       "reason": f"trials without params/finite objective at indices {bad[:5]}"})
    else:
        checks.append({"check": "selection.trials_valid", "pass": True,
                       "reason": "all trials carry params and finite objective"})
    fills = doc.get("fills")
    if not isinstance(fills, list) or not fills:
        checks.append({"check": "selection.fills", "pass": False,
                       "reason": "no fill ledger"})
        return
    need = ("bar_index", "side", "qty", "price", "fee")
    bad_fills = [i for i, f in enumerate(fills)
                 if not isinstance(f, dict) or any(k not in f for k in need)]
    if bad_fills:
        checks.append({"check": "selection.fills", "pass": False,
                       "reason": f"fills missing keys at indices {bad_fills[:5]}"})
    else:
        checks.append({"check": "selection.fills", "pass": True,
                       "reason": f"{len(fills)} fills with {need}"})


def check_power(doc: dict | None, checks: list) -> None:
    if doc is None:
        return
    pos = doc.get("positive_control", {})
    powers = pos.get("per_hypothesis_power", [])
    if pos.get("recovered") is True and powers and min(powers) >= 0.90:
        checks.append({"check": "power.positive", "pass": True,
                       "reason": f"recovered, min power {min(powers)}"})
    else:
        checks.append({"check": "power.positive", "pass": False,
                       "reason": f"recovered={pos.get('recovered')}, powers={powers}"})
    null = doc.get("null_control", {})
    upper, tol = null.get("maximum_family_wilson_upper"), null.get("tolerance")
    if null.get("false_positive") is False and isinstance(upper, (int, float)) \
            and isinstance(tol, (int, float)) and upper <= tol:
        checks.append({"check": "power.null", "pass": True,
                       "reason": f"no false positive, upper {upper} <= tolerance {tol}"})
    else:
        checks.append({"check": "power.null", "pass": False,
                       "reason": f"false_positive={null.get('false_positive')}, upper={upper}, tol={tol}"})


def check_no_fabrication(funnel_doc: dict | None, selection_doc: dict | None,
                         checks: list) -> None:
    flags = []
    for doc in (funnel_doc, selection_doc):
        if isinstance(doc, dict) and "fabricated_fills" in doc:
            flags.append(doc["fabricated_fills"])
    if flags and all(flag is False for flag in flags):
        checks.append({"check": "no_fabrication", "pass": True,
                       "reason": "fabricated_fills=false declared"})
    else:
        checks.append({"check": "no_fabrication", "pass": False,
                       "reason": "no explicit fabricated_fills=false declaration found"})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--funnel", default=None)
    parser.add_argument("--selection", default=None)
    parser.add_argument("--power", default=None)
    parser.add_argument("--trials", type=int, default=32)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)
    checks: list = []
    funnel_doc = load(args.funnel, "funnel", checks)
    selection_doc = load(args.selection, "selection", checks)
    power_doc = load(args.power, "power", checks)
    if funnel_doc is not None:
        check_funnel(funnel_doc, checks)
    if selection_doc is not None:
        check_selection(selection_doc, args.trials, checks)
    if power_doc is not None:
        check_power(power_doc, checks)
    check_no_fabrication(funnel_doc, selection_doc, checks)
    verdict = {"schema": "regime_lab.te_p0_gate.v1",
               "pass": all(c["pass"] for c in checks),
               "checks": checks}
    text = json.dumps(verdict, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n")
    else:
        print(text)
    return 0 if verdict["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
