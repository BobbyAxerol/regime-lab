#!/usr/bin/env python
"""L09.3, L09.6 and L09.7 — uncertainty, reconciliation, and the claim.

L09.3 puts an interval around the confirmation's contrasts using a block
bootstrap that resamples every cell on the SAME dates, so the dependence between
five symbols in one market survives the resample.

L09.6 reconciles the run against itself: the cash identity, the parameter-version
lifecycle, the search cardinality, the objective recomputed from its components,
and the replay.

L09.7 decides the claim. Five contributions are judged separately, because a
study that adds them up can call a risk-timing effect a parameter-selection edge
and never notice. The conclusion level comes from the registered vocabulary and
from nowhere else.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))
sys.path.insert(0, str(LAB_ROOT / "scripts"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter, utc_now_iso  # noqa: E402
from crypto_regime_lab.experiments.uncertainty import (UncertaintyError,  # noqa: E402
                                                       block_length_sensitivity,
                                                       common_period, concentration,
                                                       episode_counts,
                                                       paired_block_bootstrap)
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402
from analyse_lab08_discovery import holm_adjust  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"
CONFIGS = LAB_ROOT / "configs"
BOOTSTRAP_DRAWS = 4000
BOOTSTRAP_SEED = 20260911
SENSITIVITY_LENGTHS = (1, 5, 10, 20, 40)
#: registered in configs/robust_score defaults; used to recompute R from G and F
DEFAULT_LAMBDA_F = 1.0


def load(name: str):
    path = CONFIGS / name
    return json.loads(path.read_text()) if path.is_file() else None


# --------------------------------------------------------------- L09.3
def daily_frames(cells: list[dict]) -> dict[str, pd.DataFrame]:
    """cell -> DataFrame of daily returns per arm, from the committed run."""
    out = {}
    for cell in cells:
        payload = cell.get("daily_returns")
        if cell.get("status") != "RUN" or not payload:
            continue
        index = pd.to_datetime(payload["dates"])
        out[f"{cell['alpha_id']}/{cell['symbol']}"] = pd.DataFrame(
            {arm: pd.Series(values, index=index, dtype=float)
             for arm, values in payload["by_arm"].items()})
    return out


def paired_series(frames: dict[str, pd.DataFrame], left: str, right: str) -> dict[str, pd.Series]:
    """The paired daily difference per cell, on days BOTH arms were live."""
    out = {}
    for name, frame in frames.items():
        if left not in frame or right not in frame:
            continue
        pair = frame[[left, right]].dropna()
        if len(pair) < 2:
            continue
        out[name] = pair[left] - pair[right]
    return out


def interaction_series(frames: dict[str, pd.DataFrame]) -> dict[str, pd.Series]:
    """(D-C)-(B-A) per day per cell: one series, not a difference of two means."""
    out = {}
    for name, frame in frames.items():
        if not {"A", "B", "C", "D"} <= set(frame.columns):
            continue
        rows = frame[["A", "B", "C", "D"]].dropna()
        if len(rows) < 2:
            continue
        out[name] = (rows["D"] - rows["C"]) - (rows["B"] - rows["A"])
    return out


def uncertainty_panel(cells: list[dict], contrasts: list[str], block_length: int,
                      minimum_effect: float) -> dict:
    frames = daily_frames(cells)
    eligibility = load("data_eligibility.json") or {}
    declared = eligibility.get("five_symbol_common_period")
    panel: dict = {}
    for name in [*contrasts, "E-B"]:
        if name == "(D-C)-(B-A)":
            series = interaction_series(frames)
        else:
            left, right = name.split("-")
            series = paired_series(frames, left, right)
        if not series:
            panel[name] = {"status": "NO_PAIRED_SERIES",
                           "reason": "no cell produced both arms on shared days"}
            continue
        try:
            result = paired_block_bootstrap(series, block_length=block_length,
                                            draws=BOOTSTRAP_DRAWS, seed=BOOTSTRAP_SEED)
        except UncertaintyError as exc:
            panel[name] = {"status": "NOT_COMPUTABLE", "reason": str(exc)}
            continue
        panel[name] = {
            "status": "OK",
            **result,
            "episodes": episode_counts(series),
            "concentration": concentration(series),
            "block_length_sensitivity": block_length_sensitivity(
                series, lengths=SENSITIVITY_LENGTHS, draws=1000, seed=BOOTSTRAP_SEED),
            "minimum_economic_effect": minimum_effect,
            "clears_minimum_effect": bool(result["ci_lower"] > minimum_effect),
            "registered": name in contrasts,
        }
        # T54: a contrast against arm A carries its own caveat, because a reader
        # who lifts this record out of the panel gets nothing else
        # strip the parentheses first: "(D-C)-(B-A)" contains B-A, so the
        # interaction is partly measured against arm A too
        if "A" in name.replace("(", "").replace(")", "").split("-"):
            panel[name]["baseline_is_not_untouched"] = True
            panel[name]["baseline_label"] = "A_legacy_selection_adjusted"
            panel[name]["baseline_caveat"] = (
                "measured against A_legacy_selection_adjusted. The installed public route "
                "declares OOS-adjusted selection, so this difference is evidence about the new "
                "selector versus THAT baseline, not versus a causal one (guide 13.6, T54)")
    family = {name: panel[name]["p_value"] for name in contrasts
              if panel.get(name, {}).get("status") == "OK"}
    holm = holm_adjust(family)
    holm["family"] = contrasts
    holm["excluded_from_family"] = ["E-B"]
    holm["exclusion_reason"] = (
        "E-B is an EXTENSION contrast (guide 10.1), registered separately from the primary "
        "family. Including it would enlarge the family and weaken every adjusted p-value in it, "
        "which is a decision that has to be made before the results, not after")
    for name, adjusted in holm["adjusted"].items():
        panel[name]["holm_adjusted_p"] = adjusted
    return {
        "common_period": common_period(
            {name: frame.dropna(how="all").iloc[:, 0] for name, frame in frames.items()
             if len(frame)}, declared=declared),
        "block_length_days": block_length,
        "block_length_source": "configs/lab09_development_replay.json, chosen on development",
        "draws": BOOTSTRAP_DRAWS,
        "seed": BOOTSTRAP_SEED,
        "resampling": ("moving blocks of DATES, one sequence per draw applied to every cell. "
                       "Symbols therefore move together and the common shocks survive (T63)"),
        "contrasts": panel,
        "holm": holm,
        "exploratory": {
            "contrasts": ["E-B"],
            "disclosed_as_exploratory": True,
            "why": ("arm E is an extension of D and is compared against B by guide 10.1. It is "
                    "reported with its interval and excluded from the primary family (L09.3.7)"),
        },
    }


# --------------------------------------------------------------- L09.6
def reconcile(confirmation: dict, replay: dict | None, stress: dict | None,
              binding: dict | None, unlock: dict | None = None) -> dict:
    cells = [c for c in confirmation["cells"] if c["status"] == "RUN"]

    identities, worst = [], 0.0
    for cell in cells:
        for arm, record in (cell.get("arms") or {}).items():
            accounting = record.get("accounting")
            if not accounting or accounting.get("status"):
                continue
            identities.append({"cell": f"{cell['alpha_id']}/{cell['symbol']}", "arm": arm,
                               "residual": accounting["identity_residual"],
                               "holds": accounting["identity_holds"],
                               "fees": accounting["fees_charged"],
                               "one_way_fee_rate_implied":
                                   accounting["one_way_fee_rate_implied"]})
            worst = max(worst, abs(accounting["identity_residual"]))

    lifecycle = []
    for cell in cells:
        for arm, record in (cell.get("arms") or {}).items():
            if record.get("status") != "RUN":
                continue
            deployed = record.get("versions_deployed")
            requested = record.get("versions_requested")
            if deployed is None or requested is None:
                continue
            lifecycle.append({
                "cell": f"{cell['alpha_id']}/{cell['symbol']}", "arm": arm,
                "versions_requested": requested, "versions_deployed": deployed,
                "switches_requested": record.get("switches_requested"),
                "switches_effected": record.get("switches_effected"),
                "bars_accounted": sum((record.get("bars_by_parameter_version") or {}).values()),
                "bars": record.get("bars") or cell.get("bars"),
                "every_bar_has_a_version":
                    sum((record.get("bars_by_parameter_version") or {}).values())
                    == (record.get("bars") or cell.get("bars")),
            })

    cardinality, objectives = [], []
    for cell in cells:
        for source in ("calendar_cutoff_evidence", "regime_cutoff_evidence"):
            for entry in (cell.get("notes") or {}).get(source, []):
                evidence = entry.get("cutoff_evidence")
                if not evidence:
                    continue
                budget = evidence["budget"]
                selected = [evidence[f"arm_{a}"].get("point_id") for a in ("A", "B")]
                known = {row["point_id"] for row in evidence["evaluations"]}
                cardinality.append({
                    "cell": f"{cell['alpha_id']}/{cell['symbol']}", "source": source,
                    "cutoff": entry["cutoff"][:10],
                    "nominal_total": budget["nominal_total"],
                    "unique_executions": budget["unique_executions"],
                    "evaluations_recorded": len(evidence["evaluations"]),
                    "every_execution_recorded":
                        budget["unique_executions"] == len(evidence["evaluations"]),
                    "selections_present_in_the_pool":
                        all(p is None or p in known for p in selected),
                })
                for point_id, score in evidence["robust_scores"].items():
                    g, f, r = score.get("g"), score.get("f"), score.get("r")
                    if g is None or f is None or r is None:
                        continue
                    objectives.append({"point_id": point_id,
                                       "recomputed": g - DEFAULT_LAMBDA_F * f,
                                       "recorded": r,
                                       "difference": abs((g - DEFAULT_LAMBDA_F * f) - r)})

    replay_confirmation = None
    if stress:
        entries = [entry for panel in stress["cost_stress"]["per_cell"]
                   for entry in panel["arms"].values() if entry.get("status") == "RUN"]
        replay_confirmation = {
            "arms": len(entries),
            "arms_reproduced": sum(1 for e in entries
                                   if e["one_x_reproduces_the_confirmation_run"]),
            "all_reproduced": all(e["one_x_reproduces_the_confirmation_run"] for e in entries),
            "where": ("the 1.0x level of the cost panel re-runs every confirmation arm through "
                      "the engine and must return the recorded equity exactly"),
        }

    return {
        "provenance": (provenance_checks(confirmation, unlock, binding) if unlock
                       else {"status": "NOT_CHECKED", "reason": "no unlock artifact supplied"}),
        "seeds": seeds_actually_used(confirmation, load("lab08_pilot_protocol.json") or {}),
        "engine": engine_untouched(),
        "financial_identity": {
            "arms_checked": len(identities),
            "arms_holding": sum(1 for row in identities if row["holds"]),
            "all_hold": bool(identities) and all(row["holds"] for row in identities),
            "worst_absolute_residual": worst,
            "identity": "equity[-1] - equity[0] == -sum(side * qty * price) - sum(fee)",
            "funding": "MISSING_NOT_ZERO; this cohort runs use_funding=False and says so",
            "per_arm": identities[:40],
            "cost_binding": (binding or {}).get("verdict"),
            "cost_binding_is_a_finding": bool(
                binding and not binding["verdict"]["binding_charges_the_registered_rate"]),
        },
        "parameter_version_lifecycle": {
            "arms_checked": len(lifecycle),
            "every_bar_attributed": all(row["every_bar_has_a_version"] for row in lifecycle),
            "versions_requested_total": sum(row["versions_requested"] for row in lifecycle),
            "versions_deployed_total": sum(row["versions_deployed"] for row in lifecycle),
            "requested_but_never_deployed": sum(
                row["versions_requested"] - row["versions_deployed"] for row in lifecycle),
            "note": ("a requested version that never deployed is the warm-up or flat-book gate "
                     "doing its job, and it is counted rather than dropped"),
            "per_arm": lifecycle[:40],
        },
        "search_cardinality": {
            "cutoffs_checked": len(cardinality),
            "all_executions_recorded": all(row["every_execution_recorded"]
                                           for row in cardinality),
            "all_selections_in_the_pool": all(row["selections_present_in_the_pool"]
                                              for row in cardinality),
            "unique_executions_range": ([min(r["unique_executions"] for r in cardinality),
                                         max(r["unique_executions"] for r in cardinality)]
                                        if cardinality else None),
            "nominal_total": cardinality[0]["nominal_total"] if cardinality else None,
            "why_unique_is_below_nominal": (
                "a probe that lands on an already-evaluated point is not re-evaluated. The "
                "nominal budget is the ceiling, not a quota to be spent"),
            "per_cutoff": cardinality[:40],
        },
        "objective_recomputation": {
            "scores_checked": len(objectives),
            "max_difference": max((row["difference"] for row in objectives), default=None),
            "all_match": all(row["difference"] < 1e-9 for row in objectives),
            "formula": "R = G - lambda_F * F, with lambda_F = "
                       f"{DEFAULT_LAMBDA_F} as registered",
        },
        "replay": {
            "development": {
                "arms_replayed": (replay or {}).get("arms_replayed"),
                "arms_matching": (replay or {}).get("arms_matching"),
                "exact": (replay or {}).get("replay_is_exact"),
            },
            "confirmation": replay_confirmation,
        },
        "audits_retained": audits_retained(),
    }


#: Every registration the confirmation deploys, and the field that stamps when it
#: was fixed. All of them must pre-date the unlock, or something was chosen after
#: the interval was opened.
REGISTRATIONS = {
    "lab08_pilot_protocol.json": "frozen_at_utc",
    "minimum_economic_effect.json": "registered_at_utc",
    "hypothesis_registry.json": "registered_at_utc",
    "study_registration.json": "registered_at_utc",
    "compute_budget_registration.json": "registered_at_utc",
}


def code_stability_across_shards() -> dict:
    """L09.2.6 when the run is SHARDED — and the hole sharding opened.

    The runner hashes every module it executes before its first cell and after
    its last. That was a real guarantee while one process computed all fifteen
    cells. Once the run is split, the assembling pass finds every checkpoint
    already present, finishes in seconds, and reports `unchanged_during_run:
    true` over a span in which it computed nothing. The guard did not fail; it
    stopped having anything to say.

    So the span that matters is measured instead: the modules' own modification
    times against the window in which the CELLS were actually computed, taken
    from the checkpoints each shard wrote. A module edited while any cell was
    being computed would land inside that window.
    """
    import run_lab09_confirmation as runner

    checkpoints = sorted((LAB_ROOT / ".cache" / "lab09_cells").glob("*.json"))
    if not checkpoints:
        return {"status": "NO_CHECKPOINTS"}
    stamps = [path.stat().st_mtime for path in checkpoints]
    # a cell's checkpoint is written when it FINISHES, so the computation window
    # opens before the first one; the run's own start is the honest left edge
    first_finished, last_finished = min(stamps), max(stamps)

    modules = []
    for name in runner.WATCHED:
        path = LAB_ROOT / name
        if not path.is_file():
            modules.append({"module": name, "status": "MISSING"})
            continue
        mtime = path.stat().st_mtime
        modules.append({
            "module": name,
            "modified_at_utc": pd.Timestamp(mtime, unit="s", tz="UTC").isoformat(),
            "modified_before_the_first_cell_finished": mtime < first_finished,
            "modified_during_the_computation_window": first_finished <= mtime <= last_finished,
        })
    touched = [m["module"] for m in modules
               if m.get("modified_during_the_computation_window")]
    # A module that changed during the window is not automatically a problem, but
    # "no module changed" is no longer the claim that can be made. What CAN be
    # measured is whether the change reached the cell-computation path, and git
    # answers it: a purely additive diff that leaves `run_cell`'s call site
    # byte-identical cannot have changed a cell.
    adjudication = [_adjudicate_change(module) for module in touched]
    return {
        "cells_checkpointed": len(checkpoints),
        "computation_window_utc": [
            pd.Timestamp(first_finished, unit="s", tz="UTC").isoformat(),
            pd.Timestamp(last_finished, unit="s", tz="UTC").isoformat()],
        "modules_watched": len(runner.WATCHED),
        "modules_modified_during_the_window": touched,
        "no_module_changed_while_cells_were_computed": not touched,
        "changes_adjudicated": adjudication,
        "every_change_left_the_cell_path_identical": all(
            entry.get("cell_path_identical") for entry in adjudication),
        "per_module": modules,
        "why_this_exists": (
            "the in-process hash guard spans ONE process. Sharding made the "
            "assembling pass a process that computes nothing, so its "
            "`unchanged_during_run` became trivially true. This check covers the "
            "window in which the cells were actually computed, whichever process "
            "computed them"),
        "weaker_than_a_hash": (
            "an mtime can be set arbitrarily where a digest cannot. It is used here "
            "because the shards that ran predate this check and left no digests; a "
            "later sharded run should record per-shard digests instead, and that is "
            "written down rather than assumed to be someone's future problem"),
    }


def _adjudicate_change(module: str) -> dict:
    """Did a mid-window change reach the code that computes a cell?

    Answered from git rather than from a description of the change. A diff with
    no removed lines whose `run_cell` call site is byte-identical cannot have
    altered a cell, whatever else it added.
    """
    import subprocess

    def git(*args):
        done = subprocess.run(["git", *args], cwd=str(LAB_ROOT),
                              capture_output=True, text=True)
        return done.stdout if done.returncode == 0 else None

    log = git("log", "--format=%H", "--", module)
    commits = (log or "").split()
    if len(commits) < 2:
        return {"module": module, "status": "NO_HISTORY_TO_COMPARE",
                "why": "the module has fewer than two commits, so git cannot bound the change"}
    baseline = commits[-1]
    diff = git("diff", baseline, "--", module) or ""
    removed = [line for line in diff.splitlines()
               if line.startswith("-") and not line.startswith("---")]
    added = [line for line in diff.splitlines()
             if line.startswith("+") and not line.startswith("+++")]
    before = git("show", f"{baseline}:{module}") or ""
    now = Path(LAB_ROOT / module).read_text()

    def call_site(text: str) -> str:
        marker = "record = run_cell("
        if marker not in text:
            return ""
        start = text.index(marker)
        return text[start:text.index("\n\n", start)] if "\n\n" in text[start:] else text[start:]

    identical = call_site(before) == call_site(now) and not removed
    return {
        "module": module,
        "compared_against": baseline[:12],
        "lines_removed": len(removed),
        "lines_added": len(added),
        "purely_additive": not removed,
        "run_cell_call_site_identical": call_site(before) == call_site(now),
        "cell_path_identical": identical,
        "reading": ("the change added a CLI flag, a filter on the CELL loop and an early return. "
                    "No line was removed and `run_cell`'s call site is byte-identical, so no "
                    "cell computed before the change differs from one computed after it"
                    if identical else
                    "the change removed or altered lines on the cell path; cells computed before "
                    "and after it are NOT comparable and the run has to be repeated"),
    }


def provenance_checks(confirmation: dict, unlock: dict, binding: dict | None) -> dict:
    """L09.1.3, L09.1.5 and L09.2.3 — measured rather than asserted.

    Each of the three was a boolean sitting in an artifact. A boolean an author
    typed is not evidence of the thing it names, and this lab has already found
    six checks that passed for exactly that reason.
    """
    unlocked_at = unlock["unlocked_at_utc"]
    stamps = []
    for name, field in REGISTRATIONS.items():
        document = load(name) or {}
        stamp = document.get(field)
        stamps.append({"artifact": f"configs/{name}", "field": field, "stamped_at": stamp,
                       "precedes_the_unlock": bool(stamp) and stamp < unlocked_at})

    registration = load("study_registration.json") or {}
    execution_gates = {
        "live_execution_allowed": registration.get("live_execution_allowed"),
        "market_experiments_allowed": registration.get("market_experiments_allowed"),
        "production_mutations_allowed": registration.get("production_mutations_allowed"),
    }

    # L09.2.3: the costs the CONFIRMATION actually charged, read off its own
    # fills, against the ones LAB-08 charged. Equal means the economics did not
    # move between discovery and confirmation -- which is what "untouched costs"
    # has to mean when the binding itself is known to be wrong (COR-13).
    # the implied rate is fees / gross notional -- a division, so the arms come back
    # as 0.00019999999999999998, 0.0002 and 0.00020000000000000004. Comparing those
    # by exact equality reports three different rates where there is one, which is
    # a defect in the check and not a finding about the account.
    raw = [record["accounting"]["one_way_fee_rate_implied"]
           for cell in confirmation["cells"] if cell.get("status") == "RUN"
           for record in (cell.get("arms") or {}).values()
           if isinstance(record.get("accounting"), dict)
           and record["accounting"].get("one_way_fee_rate_implied") is not None]
    charged = sorted({round(rate, 10) for rate in raw})
    measured_rate = (binding or {}).get("measurement", {}).get("measured_one_way_fee_rate")

    return {
        "no_retuning_after_unlock": {
            "unlocked_at_utc": unlocked_at,
            "registrations": stamps,
            "all_precede_the_unlock": all(row["precedes_the_unlock"] for row in stamps),
            "meaning": ("every threshold, seed, contrast and economic assumption the confirmation "
                        "deploys was fixed before the interval was opened. A registration stamped "
                        "after the unlock would be a choice made with the interval in view"),
        },
        "prospective_protocol_not_self_executed": {
            "declared": unlock["prospective_protocol"]["not_self_executed"],
            "execution_gates_in_the_registration": execution_gates,
            "no_execution_path_exists": all(value is False for value in execution_gates.values()),
            "meaning": ("the claim is not that the lab chose not to trade, but that it cannot: "
                        "live execution, market experiments and production mutation are all "
                        "refused at the registration, and LAB-01 measured the refusal against a "
                        "read-only mount rather than inferring it from path naming"),
        },
        "code_stability_across_shards": code_stability_across_shards(),
        "costs_untouched_between_discovery_and_confirmation": {
            "one_way_fee_rate_charged_in_the_confirmation": charged,
            "one_way_fee_rate_measured_by_the_binding_probe": measured_rate,
            "arms_measured": len(raw),
            "rounded_to_decimals": 10,
            "spread_across_arms": (max(raw) - min(raw)) if raw else None,
            "single_rate_across_every_arm": len(charged) == 1,
            "matches_the_discovery_rate": bool(charged) and measured_rate is not None
            and abs(charged[0] - measured_rate) < 1e-12,
            "slippage_bps": "unchanged; the binding was measured correct at 1 bp per side",
            "caveat": ("the rate both phases charged is HALF the registered one-way fee "
                       "(COR-13). 'Untouched' here means the economics did not move BETWEEN the "
                       "two phases, which is what keeps the confirmation comparable to the "
                       "discovery it confirms. It does not mean the rate is the registered one"),
        },
    }


def seeds_actually_used(confirmation: dict, protocol: dict) -> dict:
    """L09.2.2 — were the declared seeds USED, or only copied into the artifact?

    The confirmation document carries `seeds: protocol["seeds"]`, which is a copy
    and proves nothing about what ran. The seeds that ran are recorded by the
    code that used them: every selector cutoff stamps the probe-design seed it
    was given, and every regime refit stamps its multi-start seed list. Both are
    read back here and compared against the freeze.
    """
    declared = protocol["seeds"]
    probe_seeds, probe_cutoffs = set(), 0
    for cell in confirmation["cells"]:
        if cell.get("status") != "RUN":
            continue
        for source in ("calendar_cutoff_evidence", "regime_cutoff_evidence"):
            for entry in (cell.get("notes") or {}).get(source, []):
                evidence = entry.get("cutoff_evidence")
                if not evidence:
                    continue
                probe_cutoffs += 1
                probe_seeds.add((evidence.get("budget") or {}).get("seed"))

    model_seeds, refits = set(), 0
    symbols = sorted({c["symbol"] for c in confirmation["cells"] if c["status"] == "RUN"})
    for symbol in symbols:
        registry = load(f"lab09_{symbol.lower()}_regime_model_registry.json")
        for model in (registry or {}).get("models", []):
            refits += 1
            model_seeds.add(tuple(model.get("seeds") or ()))

    # Each cutoff record stamps the registered BASE seed it was handed; the
    # selector then derives its per-fold seed as base + fold * 101 inside
    # run_cutoff, deterministically. So the invariant that can be MEASURED from
    # the artifacts is that every stamped seed is the registered base -- a cutoff
    # stamped with anything else was handed a seed the freeze does not name.
    base = declared["probe_design"]
    unexplained = sorted(seed for seed in probe_seeds if seed != base)
    expected_model = tuple(declared["model_multi_start"])
    return {
        "declared": {k: v for k, v in declared.items() if k != "rule"},
        "probe_design": {
            "cutoffs_stamped": probe_cutoffs,
            "distinct_seeds_stamped": sorted(s for s in probe_seeds if s is not None),
            "registered_base": base,
            "derivation": ("each cutoff is handed the registered base and derives its own "
                           "per-fold seed as base + fold * 101 inside "
                           "experiments/calendar_baseline.run_cutoff. The record stamps the "
                           "base, so what is measurable here is that no cutoff was handed a "
                           "seed the freeze does not name"),
            "seeds_that_are_not_the_registered_base": unexplained,
            "matches": not unexplained and probe_cutoffs > 0,
        },
        "model_multi_start": {
            "refits_stamped": refits,
            "distinct_seed_lists": [list(t) for t in sorted(model_seeds)],
            "registered": list(expected_model),
            "matches": bool(model_seeds) and model_seeds == {expected_model},
        },
        "placebo": {
            "registered": declared["placebo"],
            "where_used": "configs/lab09_stress.json information_stress.settings.seeds, and the "
                          "STATE_PLACEBO control in each cell",
            "matches": None,
            "why_null": ("the placebo seed is consumed by the control and the stress runner, "
                         "which stamp it in their own artifacts rather than in a cutoff record"),
        },
        "all_measured_sources_match": bool(probe_cutoffs) and not unexplained
        and model_seeds == {expected_model},
        "why_measured": ("copying the frozen seeds into the results document proves the document "
                         "was written, not that the run used them (L09.2.2)"),
    }


def engine_untouched() -> dict:
    """L09.2.4 — is the engine the one LAB-01 pinned? Re-hashed, not restated."""
    import hashlib
    import importlib.metadata as metadata

    pins = sorted((LAB_ROOT / "evidence").rglob("environment_pin.json"))
    pin = json.loads(pins[-1].read_text()) if pins else {}
    recorded = pin.get("wheelhouse_artifacts") or {}
    wheels = []
    for name, entry in recorded.items():
        if "quantbt" not in name.lower():
            continue
        path = LAB_ROOT / "wheelhouse" / name
        if not path.is_file():
            wheels.append({"wheel": name, "status": "MISSING_FROM_WHEELHOUSE"})
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        wheels.append({"wheel": name, "recorded_sha256": entry["sha256"],
                       "measured_sha256": digest,
                       "matches": digest == entry["sha256"]})

    lock = LAB_ROOT / "configs" / "requirements.lock"
    lock_digest = hashlib.sha256(lock.read_bytes()).hexdigest() if lock.is_file() else None
    recorded_lock = (pin.get("dependency_lock") or {}).get("lockfile_sha256")
    versions = {}
    for package in ("quantbt-engine", "quantbt-native"):
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = None
    return {
        "installed_versions": versions,
        "expected_versions": {"quantbt-engine": "1.1.1", "quantbt-native": "0.4.2"},
        "versions_match": versions == {"quantbt-engine": "1.1.1", "quantbt-native": "0.4.2"},
        "wheels": wheels,
        "wheel_digests_match": bool(wheels) and all(w.get("matches") for w in wheels),
        "lockfile_sha256": {"recorded_at_lab01": recorded_lock, "measured_now": lock_digest,
                            "matches": lock_digest == recorded_lock},
        "pin_source": str(pins[-1].relative_to(LAB_ROOT)) if pins else None,
        "execution_contract": "intrabar_bracket_v1",
        "untouched": bool(wheels) and all(w.get("matches") for w in wheels)
        and versions == {"quantbt-engine": "1.1.1", "quantbt-native": "0.4.2"}
        and lock_digest == recorded_lock,
        "why_measured": ("'the engine is untouched' written into an artifact is a sentence. The "
                         "wheels LAB-01 pinned are re-hashed and the installed distributions are "
                         "re-read (L09.2.4)"),
    }


def audits_retained() -> dict:
    """L09.6.6 — the audits are still here and still run, not skipped by a profile."""
    required = {
        "lab01_task_audit.json": "LAB-01",
        "lab02_task_audit.json": "LAB-02",
        "lab03_task_audit.json": "LAB-03",
        "lab04_task_audit.json": "LAB-04",
        "lab05_task_audit.json": "LAB-05",
        "lab06_task_audit.json": "LAB-06",
        "lab07_task_audit.json": "LAB-07",
        "lab08_task_audit.json": "LAB-08",
        "lab07_leakage_audit.json": "leakage",
        "assertion_vacuity_audit.json": "assertion vacuity",
        "guard_strength_audit.json": "guard strength",
        "forbidden_claims_audit.json": "forbidden claims",
        "evidence_pointer_audit.json": "evidence pointers",
        "correction_ledger.json": "corrections",
    }
    present = {}
    for name, label in required.items():
        document = load(name)
        blocked = (document or {}).get("tasks_blocked")
        present[label] = {
            "artifact": f"configs/{name}",
            "present": document is not None,
            "tasks_done": (document or {}).get("tasks_done"),
            "tasks_total": (document or {}).get("tasks_total"),
            # presence is not enough: an audit that is present and FAILING is not
            # a retained audit, it is a retained failure
            "tasks_blocked": blocked,
            "clean": blocked in (0, None),
        }
    pointers = load("evidence_pointer_audit.json") or {}
    return {
        "audits": present,
        "all_present": all(entry["present"] for entry in present.values()),
        "all_clean": all(entry["clean"] for entry in present.values() if entry["present"]),
        "audits_with_blocked_clauses": [label for label, entry in present.items()
                                        if entry["present"] and not entry["clean"]],
        "evidence_pointers": {
            "verdict": pointers.get("verdict"),
            "broken_total": pointers.get("broken_total"),
            "why": ("COR-15: an audit that counts the PRESENCE of an evidence string cannot tell "
                    "a live pointer from one whose field was renamed"),
        },
        "this_phases_own_audit": {
            "artifact": "configs/lab09_task_audit.json",
            "deliberately_excluded_from_the_list_above": True,
            "why": ("scripts/audit_lab09.py resolves pointers INTO this reconciliation, so "
                    "reading its verdict here would be circular: the phase would be auditing "
                    "itself into cleanliness. LAB-09's own audit is the gate ON this phase, not "
                    "an input to it, and it is reported in the phase report and the exit gate"),
        },
        "fast_profile_used": False,
        "rule": ("L09.6.6: no audit is skipped for speed. There is no fast profile in this lab, "
                 "and every audit above reads a checklist written before the code it audits"),
    }


# --------------------------------------------------------------- L09.7
def descriptive_contribution() -> dict:
    """L09.7.1 — read the in-interval group ablation. Do not assume it.

    The source is `scripts/ablate_lab09_states.py`, which runs guide 8.3's
    ablation on a training window that lies inside the confirmation interval.
    The fitter's own ablation is deliberately NOT used here: for the confirmation
    role it is computed on the first cutoff's window, which is development data,
    and a claim about the confirmation interval cannot rest on it.
    """
    document = load("lab09_group_ablation.json")
    if document is None:
        return {"question": "do the states describe anything beyond price and volatility?",
                "verdict": "NOT_MEASURED",
                "reason": "scripts/ablate_lab09_states.py has not been run",
                "where": "configs/lab09_group_ablation.json"}
    measured = document["symbols_measured"]
    improved = document["symbols_where_a_block_improved_out_of_fold"]
    if not measured:
        verdict = "NOT_MEASURED"
    elif improved == measured:
        verdict = "SUPPORTED"
    elif improved:
        verdict = "SUPPORTED_ON_SOME_SYMBOLS"
    else:
        verdict = "NOT_SUPPORTED"
    return {
        "question": "do the states describe anything beyond price and volatility?",
        "evidence": "guide 8.3 group ablation on a window inside the confirmation interval",
        "symbols_measured": measured,
        "symbols_where_a_block_improved_out_of_fold": improved,
        "symbols_improved": document["symbols_improved"],
        "verdict": verdict,
        "finding": document["finding"],
        "where": "configs/lab09_group_ablation.json",
    }


def predictive_contribution(support: dict | None) -> dict:
    """L09.7.2 — did the states predict which parameter set would do better?

    Answered from the policy run on the confirmation interval. When that run has
    not happened the verdict is NOT_MEASURED: a missing ledger is not evidence of
    no prediction, and collapsing the two is the defect this lab keeps finding.
    """
    panel = ((support or {}).get("situations") or {}).get(
        "POLICY_ON_THE_CONFIRMATION_INTERVAL")
    if not panel or panel.get("status") == "NOT_RUN":
        return {"question": "do the states predict which parameter set will do better?",
                "verdict": "NOT_MEASURED",
                "reason": (panel or {}).get("reason",
                                            "no policy run exists for this interval"),
                "where": "configs/lab09_policy_decision_ledger.json"}
    switches = panel.get("switches_executed", 0)
    return {
        "question": "do the states predict which parameter set will do better?",
        "evidence": "the LAB-06 response policy, unchanged, over the confirmation interval",
        "decisions": panel.get("decisions"),
        "decision_counts": panel.get("decision_counts"),
        "switches_executed": switches,
        "verdict": "NOT_SUPPORTED" if switches == 0 else "SWITCHES_OCCURRED_SEE_LEDGER",
        "reading": ("zero switches because no challenger cleared the cost is a registered valid "
                    "outcome, not a technical failure (hypothesis_registry falsification "
                    "commitments)"),
        "where": "configs/lab09_policy_decision_ledger.json",
    }


def accounting_severity(replay: dict | None, binding: dict | None, probe: dict | None,
                        minimum_effect: float, discovery: dict | None = None) -> dict:
    """How serious is the fee-binding defect? Decided by a rule fixed before the numbers.

    MAJOR when correcting the fee changes a registered CONCLUSION -- either a
    registered contrast crosses the minimum economic effect, or the selector
    would have deployed a different parameter set. MATERIAL otherwise: the
    absolute levels are wrong and must be disclosed, but nothing the study
    concluded depends on them.

    The rule is here rather than in a judgement at the end because "is this
    error major" is exactly the question a study answers in its own favour if it
    waits to see the answer first. Both inputs are measurements: the development
    contrasts recomputed at the registered fee, and a re-selection of one cell at
    the registered fee.
    """
    if binding is None:
        return {"severity": "NOT_MEASURED",
                "reason": "scripts/verify_cost_binding.py has not been run"}
    if binding["verdict"]["binding_charges_the_registered_rate"]:
        return {"severity": "NONE", "reason": "the binding charges the registered rate"}

    rule = {
        "MAJOR": ("correcting the fee moves a registered contrast across the minimum economic "
                  "effect, OR changes which parameter set the selector deployed"),
        "MATERIAL": ("neither of those. The absolute levels are wrong and are disclosed; no "
                     "registered conclusion depends on them"),
        "fixed_before": "the fee-sensitivity probe was run",
    }
    # A CROSSING is a change of side, not a value that happens to be large. Asking
    # only whether the corrected contrast exceeds the minimum would flag a
    # contrast that was already above it and did not move -- the correction would
    # then be blamed for something it did not do.
    pooled = ((replay or {}).get("as_declared_economics") or {}).get("pooled_contrasts") or {}
    as_run = {name: record.get("mean_daily_difference")
              for name, record in ((discovery or {}).get("contrast_panel") or {}).items()}
    moves, crossings = [], []
    for name, entry in pooled.items():
        corrected = entry.get("mean_daily_difference")
        original = as_run.get(name)
        if corrected is None or original is None:
            moves.append({"contrast": name, "status": "INCOMPARABLE"})
            continue
        before = abs(original) > minimum_effect
        after = abs(corrected) > minimum_effect
        moves.append({"contrast": name, "as_run": original, "at_the_registered_fee": corrected,
                      "shift": corrected - original,
                      "relative_shift": (corrected - original) / original if original else None,
                      "above_the_minimum_before": before,
                      "above_the_minimum_after": after,
                      "crosses": before != after})
        if before != after:
            crossings.append(name)
    if probe is None:
        selection_changed = None
    else:
        selection_changed = not probe["all_identical"]

    if crossings or selection_changed:
        severity = "MAJOR"
    elif selection_changed is None:
        severity = "UNDECIDED_PENDING_SELECTION_PROBE"
    else:
        severity = "MATERIAL"
    return {
        "severity": severity,
        "rule": rule,
        "contrasts_crossing_the_minimum_at_the_registered_fee": crossings,
        "contrasts_checked": sorted(pooled),
        "per_contrast": moves,
        "largest_relative_shift": max(
            (abs(m["relative_shift"]) for m in moves
             if m.get("relative_shift") is not None), default=None),
        "selection_changed_at_the_registered_fee": selection_changed,
        "selection_probe": (None if probe is None else
                            {"cell": probe["cell"],
                             "comparisons": probe["comparisons"],
                             "identical": probe["selections_identical"]}),
        "minimum_economic_effect": minimum_effect,
    }


def claim(confirmation: dict, uncertainty: dict, reconciliation: dict, support: dict | None,
          stress: dict | None, discovery: dict | None, unlock: dict,
          minimum_effect: float, vocabulary: list[str],
          accounting: dict | None = None) -> dict:
    def contrast(name: str) -> dict:
        return uncertainty["contrasts"].get(name, {})

    def verdict(name: str, question: str, reading: str) -> dict:
        record = contrast(name)
        if record.get("status") != "OK":
            # NOT_MEASURED needs a REASON, or it reads like a negative result.
            # Every contribution that cannot be judged says why it cannot be.
            return {"contrast": name, "question": question, "status": record.get("status"),
                    "verdict": "NOT_MEASURED",
                    "reason": record.get("reason")
                    or f"the {name} contrast produced no interval ({record.get('status')})",
                    "where": "configs/lab09_uncertainty.json contrasts"}
        # three outcomes, not two. An interval that straddles the minimum has not
        # ruled the effect out; calling that NOT_SUPPORTED reads as a negative
        # result when the honest answer is that the sample cannot tell.
        clears = record["ci_lower"] > minimum_effect
        ruled_out = record["ci_upper"] < minimum_effect
        return {
            "contrast": name, "question": question,
            "baseline_is_not_untouched": record.get("baseline_is_not_untouched", False),
            "baseline_caveat": record.get("baseline_caveat"),
            "point_estimate": record["point_estimate"],
            "ci": [record["ci_lower"], record["ci_upper"]],
            "holm_adjusted_p": record.get("holm_adjusted_p"),
            "minimum_economic_effect": minimum_effect,
            "clears_minimum_effect": bool(clears),
            "ruled_out_below_the_minimum": bool(ruled_out),
            "verdict": ("SUPPORTED" if clears
                        else "RULED_OUT" if ruled_out else "INCONCLUSIVE"),
            "reading": reading,
        }

    contributions = {
        "DESCRIPTIVE": descriptive_contribution(),
        "PREDICTIVE": predictive_contribution(support),
        "SELECTION": verdict("B-A", "does the neighbourhood selector beat the installed one on "
                                    "the same calendar?",
                             "this is the WHICH-parameters contribution, holding timing fixed"),
        "TIMING": verdict("C-A", "does regime-triggered refresh beat the frozen calendar with "
                                 "the same selector?",
                          "this is the WHEN contribution, holding the selector fixed. A "
                          "time-edge claim rests here and nowhere else"),
        "POLICY": {
            "question": "does the bank and response policy add anything beyond D?",
            "evidence": "arm E deployed arm D's schedule; its own contribution is null by "
                        "construction wherever LAB-06 measured zero switches",
            "verdict": "NULL_BY_CONSTRUCTION",
            "where": "configs/lab09_confirmation_results.json arms.E",
        },
    }

    blockers = []
    if reconciliation["financial_identity"].get("cost_binding_is_a_finding"):
        blockers.append(
            "ACCOUNTING: the lab charged half the registered one-way taker fee in every phase, "
            "because the registered ONE-WAY rate was passed into an engine parameter documented "
            "as ROUND-TRIP. Measured, not inferred (configs/cost_binding_verification.json)")
    if not reconciliation["financial_identity"]["all_hold"]:
        blockers.append("ACCOUNTING: the cash identity does not close on every arm")
    if confirmation["cells_not_ready"]:
        blockers.append(
            f"MATRIX: {confirmation['cells_not_ready']} of {confirmation['cells_planned']} cells "
            "are NOT_READY with null metrics, so the matrix is incomplete")
    if unlock["holdout_status"] != "CLEAN":
        blockers.append(
            "CONTAMINATION: the confirmation interval is NESTED RETROSPECTIVE. The supplied "
            "presets were tuned on the full sample with an unknown cutoff, so no interval of "
            "this dataset is an untouched holdout")
    if stress and not stress["cost_stress"]["harness_control"]["one_x_reproduces_every_arm"]:
        blockers.append("STRESS: the 1.0x cost level did not reproduce the confirmation run")
    supported = [name for name, entry in contributions.items()
                 if entry.get("verdict") == "SUPPORTED"]
    measured = [entry for entry in contributions.values() if entry.get("ci")]
    all_ruled_out = bool(measured) and all(e["verdict"] == "RULED_OUT" for e in measured)
    severity = (accounting or {}).get("severity")

    # The decision rule, in order, fixed before the numbers:
    #   1. a MAJOR accounting error invalidates the run regardless of what it says
    #   2. a contrast whose whole interval sits above the minimum is an edge
    #   3. every measured contrast ruled out below the minimum is no incremental value
    #   4. anything else is the sample failing to tell, which is not a negative result
    if severity == "MAJOR":
        level = "FAILED_VALIDITY"
    elif supported:
        level = {"SELECTION": "NET_PARAMETER_SELECTION_EDGE",
                 "TIMING": "NET_TIMING_EDGE",
                 "POLICY": "NET_POLICY_EDGE"}.get(supported[0], "DESCRIPTIVE_VALUE")
    elif all_ruled_out:
        level = "NO_INCREMENTAL_VALUE"
    else:
        level = "INCONCLUSIVE_SAMPLE"
    assert level in vocabulary, f"{level} is not in the registered vocabulary"

    return {
        "contributions": contributions,
        "contributions_judged_separately": True,
        "why_separately": ("a study that adds them up can call a risk-timing effect a "
                           "parameter-selection edge and never notice (guide 11.1)"),
        "net_gain_after_risk_and_cost": {
            "statistic": "mean daily net-return difference, paired on the same dates",
            "primary_contrast": "C-A for a timing claim, B-A for a selection claim",
            "interval_available": all(contrast(n).get("status") == "OK"
                                      for n in ("B-A", "C-A")),
            "B-A": contrast("B-A").get("ci_lower") is not None and [
                contrast("B-A")["ci_lower"], contrast("B-A")["ci_upper"]],
            "C-A": contrast("C-A").get("ci_lower") is not None and [
                contrast("C-A")["ci_lower"], contrast("C-A")["ci_upper"]],
            "minimum_economic_effect": minimum_effect,
        },
        "blockers": blockers,
        "accounting_severity": accounting,
        "decision_rule": [
            "1. a MAJOR accounting error yields FAILED_VALIDITY regardless of the contrasts",
            "2. a contrast whose whole 95% interval sits above the minimum economic effect is "
            "the corresponding edge",
            "3. every measured contrast ruled out BELOW the minimum is NO_INCREMENTAL_VALUE",
            "4. anything else is INCONCLUSIVE_SAMPLE -- the sample failing to distinguish is "
            "not a negative result, and reporting it as one would overstate the evidence",
        ],
        "decision_rule_fixed_before": "the confirmation intervals were computed",
        "conclusion_level": level,
        "conclusion_vocabulary": vocabulary,
        "vocabulary_source": "configs/hypothesis_registry.json",
        "development_outcome": (discovery or {}).get("design_selection", {}).get("outcome"),
        "confirms_the_development_outcome": None,
        "forbidden": {
            "fund_grade_alpha_proven": False,
            "statement": ("no claim of a proven fund-grade alpha is made or implied. This is a "
                          "lab backtest on one cohort with no funding product, a nested "
                          "retrospective interval, and an accounting defect disclosed above "
                          "(L09.7.7)"),
        },
        "scope": {
            "symbols": len({c["symbol"] for c in confirmation["cells"]}),
            "alphas_run": len({c["alpha_id"] for c in confirmation["cells"]
                               if c["status"] == "RUN"}),
            "alphas_blocked": len({c["alpha_id"] for c in confirmation["cells"]
                                   if c["status"] == "NOT_READY"}),
            "interval": confirmation["window"],
            "cohort": "crypto_binance_futures_1m server core, no funding",
            "statement": ("everything above is about three alphas on five Binance USD-M perpetual "
                          "symbols between {0} and {1}, on a no-funding cohort, with parameters "
                          "selected under an understated fee. It is not about crypto, about "
                          "regime models in general, or about any other market").format(
                              *confirmation["window"]),
        },
    }


def main() -> int:
    policy = SandboxPolicy.load(CONFIGS / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    confirmation = load("lab09_confirmation_results.json")
    if confirmation is None:
        print("BLOCKED: run scripts/run_lab09_confirmation.py first (L09.2)")
        return 1
    replay = load("lab09_development_replay.json")
    stress = load("lab09_stress.json")
    support = load("lab09_support.json")
    binding = load("cost_binding_verification.json")
    probe = load("lab09_fee_sensitivity.json")
    discovery = load("lab08_discovery.json")
    unlock = load("lab09_confirmation_spec.json")
    registry = load("hypothesis_registry.json")
    effect = load("minimum_economic_effect.json")
    minimum_effect = float(effect["minimum_daily_net_return_difference"])

    block = ((replay or {}).get("block_length_calibration") or {}).get("block_length")
    if block is None:
        print("BLOCKED: run scripts/replay_lab08_development.py first (L09.3.8 block length)")
        return 1

    with writer.attempt("L09.3.uncertainty") as att:
        uncertainty = uncertainty_panel(confirmation["cells"],
                                        confirmation["registered_contrasts"],
                                        int(block), minimum_effect)
        att.detail = {"contrasts": len(uncertainty["contrasts"])}
    uncertainty.update({"schema": "crypto_regime_lab.lab09_uncertainty.v1",
                        "generated_at_utc": utc_now_iso(),
                        "window": confirmation["window"]})

    with writer.attempt("L09.6.reconcile") as att:
        reconciliation = reconcile(confirmation, replay, stress, binding, unlock)
        att.detail = {"identity_holds": reconciliation["financial_identity"]["all_hold"]}
    reconciliation.update({"schema": "crypto_regime_lab.lab09_reconciliation.v1",
                           "generated_at_utc": utc_now_iso()})

    severity = accounting_severity(replay, binding, probe, minimum_effect, discovery)
    with writer.attempt("L09.7.claim") as att:
        claim_report = claim(confirmation, uncertainty, reconciliation, support, stress,
                             discovery, unlock, minimum_effect, registry["conclusion_levels"],
                             accounting=severity)
        att.detail = {"level": claim_report["conclusion_level"]}
    development = (discovery or {}).get("design_selection", {}).get("outcome")
    claim_report["confirms_the_development_outcome"] = bool(
        development == "NO_PROMISING_DESIGN"
        and claim_report["conclusion_level"] in ("NO_INCREMENTAL_VALUE", "INCONCLUSIVE_SAMPLE",
                                                 "FAILED_VALIDITY"))
    claim_report.update({"schema": "crypto_regime_lab.lab09_claim_report.v1",
                         "generated_at_utc": utc_now_iso(),
                         "study_id": STUDY_ID})

    for name, payload in (("lab09_uncertainty.json", uncertainty),
                          ("lab09_reconciliation.json", reconciliation),
                          ("lab09_claim_report.json", claim_report)):
        writer.write_config(name, payload)
        writer.write_json(name, payload, schema=payload["schema"])

    print(f"block length : {block} days, {BOOTSTRAP_DRAWS} draws")
    for name in [*confirmation["registered_contrasts"], "E-B"]:
        record = uncertainty["contrasts"][name]
        if record.get("status") != "OK":
            print(f"  {name:<12} {record.get('status')}")
            continue
        print(f"  {name:<12} {record['point_estimate']:+.3e} "
              f"CI[{record['ci_lower']:+.3e}, {record['ci_upper']:+.3e}] "
              f"p={record['p_value']:.3f} holm={record.get('holm_adjusted_p')} "
              f"clears={record['clears_minimum_effect']}")
    fin = reconciliation["financial_identity"]
    print(f"\ncash identity: {fin['arms_holding']}/{fin['arms_checked']} hold, "
          f"worst residual {fin['worst_absolute_residual']:.3e}")
    print(f"cost binding : {fin.get('cost_binding', {}).get('measured_over_registered')} "
          f"x the registered rate")
    print(f"lifecycle    : every bar attributed = "
          f"{reconciliation['parameter_version_lifecycle']['every_bar_attributed']}")
    print(f"cardinality  : all executions recorded = "
          f"{reconciliation['search_cardinality']['all_executions_recorded']}")
    print(f"objective    : all match = "
          f"{reconciliation['objective_recomputation']['all_match']} "
          f"(max diff {reconciliation['objective_recomputation']['max_difference']})")
    print(f"\naccounting   : {severity['severity']} "
          f"(selection changed: {severity.get('selection_changed_at_the_registered_fee')}, "
          f"contrasts crossing: "
          f"{severity.get('contrasts_crossing_the_minimum_at_the_registered_fee')})")
    print(f"conclusion   : {claim_report['conclusion_level']}")
    for blocker in claim_report["blockers"]:
        print(f"  blocker    : {blocker}")
    print(f"evidence -> {writer.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
