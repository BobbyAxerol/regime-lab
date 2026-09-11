#!/usr/bin/env python
"""LAB-06 — join LAB-04 candidate utilities to LAB-05 states, then decide.

The join is the phase. Everything upstream produced one half of it: LAB-04 knows
what each parameter set was worth, LAB-05 knows what the market looked like, and
neither knows whether the second predicts the first.

Causality is enforced by construction at three points, so it cannot depend on
remembering a rule:

* the bank at a cutoff is assembled ONLY from discoveries at or before it, and a
  later discovery is rejected with a recorded reason rather than filtered away;
* an episode is usable at decision T only when its outcome finished AND published
  by T. The check lives on the episode, not in the caller;
* the context attached to a decision comes from the emission whose ``available_at``
  is at or before T, so a state inferred later can never reach an earlier decision.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.data import panel as P  # noqa: E402
from crypto_regime_lab.evidence.manifest import EvidenceWriter  # noqa: E402
from crypto_regime_lab.experiments.calendar_baseline import DECISION_INTERVAL  # noqa: E402
from crypto_regime_lab.experiments.evaluator import (ACCOUNT, run_candidate,  # noqa: E402
                                                     window_metrics)
from crypto_regime_lab.policy import bank as BK  # noqa: E402
from crypto_regime_lab.policy import campaign as CP  # noqa: E402
from crypto_regime_lab.policy import clocks as CL  # noqa: E402
from crypto_regime_lab.policy import decision as DC  # noqa: E402
from crypto_regime_lab.policy import episodes as EP  # noqa: E402
from crypto_regime_lab.policy import limitations as LM  # noqa: E402
from crypto_regime_lab.policy import response as RS  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402
from crypto_regime_lab.selector.alpha_schemas import SCHEMAS, SEED_POINTS  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"
SNAPSHOT_ID = "server_core_v1"
ALPHA, SYMBOL = "A-SC", "BTCUSDT"
HORIZON_DAYS = EP.PILOT_HORIZON_DAYS
BANK_WARMUP_BARS = 120
DEVELOPMENT_END = "2023-12-31"

#: The policy is the same policy in both roles. LAB-06 ran it on development;
#: L09.5 runs it on the confirmation interval to see how it behaves where the
#: design was not built -- new episodes, ambiguous states, a bank that goes stale.
#: The thresholds, the horizon, the warmup and the cost model are NOT touched
#: between the two: a policy retuned for the confirmation is not a confirmation.
ROLES = {
    "development": {
        "cells_dir": LAB_ROOT / ".cache" / "lab04_cells",
        "tape": "lab05_emission_tape.json",
        "window": (None, DEVELOPMENT_END),
        "prefix": "lab06",
        "panel": "response_panel.parquet",
    },
    "confirmation": {
        "cells_dir": LAB_ROOT / ".cache" / "lab09_cells",
        "tape": "lab09_btcusdt_emission_tape.json",
        "window": ("2024-01-01", "2026-08-31"),
        "prefix": "lab09_policy",
        "panel": "lab09_policy_response_panel.parquet",
    },
}
ROLE = "development"
CELLS_DIR = ROLES["development"]["cells_dir"]


def load_contexts(tape_name: str) -> dict:
    """Emissions keyed by the time they became AVAILABLE, not observed."""
    tape = json.loads((LAB_ROOT / "configs" / tape_name).read_text())
    def _utc(value):
        """The panel stores naive UTC; the bar index is tz-aware. Normalise once here
        rather than comparing them and hoping."""
        stamp = pd.Timestamp(value)
        return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")

    rows = []
    for namespace, record in tape["namespaces"].items():
        for emission in record["emissions"]:
            rows.append({
                "available_at": _utc(emission["available_at"]),
                "observed_at": _utc(emission["observed_at"]),
                "namespace": namespace, "state_id": emission["state_id"],
                "features": emission["feature_contributions"],
                "quality_status": emission["quality_status"],
                "decision_eligible": emission["decision_eligible"],
                "second_best_gap": emission["second_best_gap"],
            })
    rows.sort(key=lambda r: r["available_at"])
    return {"rows": rows, "namespaces": sorted(tape["namespaces"])}


def context_at(rows: list, when: pd.Timestamp) -> dict | None:
    """The most recent emission ALREADY AVAILABLE at ``when``. Never a later one."""
    best = None
    for row in rows:
        if row["available_at"] <= when:
            best = row
        else:
            break
    return best


def cutoff_records(cell: dict) -> list[dict]:
    """The (cutoff, evidence) pairs this cell produced, in either runner's shape.

    LAB-04 wrote them as `folds`; the LAB-09 confirmation runner writes them under
    `notes.calendar_cutoff_evidence` because it also carries a regime schedule.
    Same records, two containers -- read both rather than duplicating the policy.
    """
    if cell.get("folds"):
        return cell["folds"]
    return (cell.get("notes") or {}).get("calendar_cutoff_evidence") or []


def load_discoveries() -> list:
    """Candidates from the selector's search, each tagged with its discovery cutoff."""
    cell = json.loads((CELLS_DIR / f"{ALPHA}_{SYMBOL}.json").read_text())
    out = []
    for fold in cutoff_records(cell):
        evidence = fold.get("cutoff_evidence")
        if not evidence:
            continue
        cutoff = pd.Timestamp(fold["cutoff"])
        if cutoff.tzinfo is None:
            cutoff = cutoff.tz_localize("UTC")
        for point_id, score in evidence["robust_scores"].items():
            out.append({
                "candidate_id": f"{point_id}",
                "params": score["params"],
                "discovered_at": cutoff,
                "score": score.get("r") if score.get("r") is not None else -1e9,
                "validation_panel": {k: score.get(k) for k in
                                     ("g", "f", "r", "p_survive", "episodes_used",
                                      "neighbours_used", "status")},
                "reason": f"discovered by the LAB-04 search at cutoff {fold['cutoff'][:10]}",
            })
    stamps = []
    for fold in cutoff_records(cell):
        if not fold.get("cutoff_evidence"):
            continue
        stamp = pd.Timestamp(fold["cutoff"])
        stamps.append(stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp)
    return out, stamps


def main(argv: list[str] | None = None) -> int:
    global ROLE, CELLS_DIR
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", choices=sorted(ROLES), default="development",
                        help="which data role to run the policy over. 'confirmation' is L09.5 "
                             "and needs the LAB-09 confirmation cell and state tape.")
    args = parser.parse_args(argv)
    ROLE = args.role
    role = ROLES[ROLE]
    CELLS_DIR = role["cells_dir"]
    if not (CELLS_DIR / f"{ALPHA}_{SYMBOL}.json").is_file():
        print(f"BLOCKED: role={ROLE} needs {CELLS_DIR / f'{ALPHA}_{SYMBOL}.json'}")
        return 1

    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    policy.assert_lab_marker_ok(STUDY_ID)
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    contexts = load_contexts(role["tape"])
    discoveries, cutoffs = load_discoveries()
    schema = SCHEMAS[ALPHA]

    snapshot_root = policy.lab_root / "snapshots" / SNAPSHOT_ID
    manifest = json.loads((snapshot_root / "manifest.json").read_text())
    bars = P.load_resampled(snapshot_root, "crypto_binance_futures_1m", SYMBOL,
                            DECISION_INTERVAL[ALPHA], manifest=manifest)
    bars["time"] = pd.to_datetime(bars["time"])
    if bars["time"].dt.tz is None:
        bars["time"] = bars["time"].dt.tz_localize("UTC")
    bars = bars.set_index("time").sort_index()
    window_start, window_end = role["window"]
    if window_start is not None:
        bars = bars[bars.index >= pd.Timestamp(window_start, tz="UTC")]
    bars = bars[bars.index <= pd.Timestamp(f"{window_end} 23:59:59", tz="UTC")]

    # ---- L06.1 horizon from holding diagnostics -----------------------
    probe = run_candidate(ALPHA, dict(SEED_POINTS[ALPHA]),
                          bars[(bars.index >= cutoffs[0]) & (bars.index < cutoffs[1])])
    holding = window_metrics(probe)
    bar_hours = pd.Timedelta(DECISION_INTERVAL[ALPHA]).total_seconds() / 3600.0
    horizon_note = EP.horizon_from_holding_diagnostics(
        holding["mean_holding_bars"] or 0.0, bar_hours)

    # ---- L06.2 bank at each cutoff, lineage enforced ------------------
    banks = {}
    with writer.attempt("L06.2.bank") as att:
        for cutoff in cutoffs:
            banks[cutoff] = BK.build_bank(
                cutoff, discoveries, adapter_hash=BK.parameter_digest({"alpha": ALPHA}),
                warmup_bars=BANK_WARMUP_BARS, schema=schema)
        att.detail = {"cutoffs": len(banks),
                      "sizes": [len(b.admissible()) for b in banks.values()]}

    # ---- L06.1 episodes for every bank candidate ----------------------
    windows = EP.build_grid(bars.index, horizon_days=HORIZON_DAYS)
    window_index = {start: i for i, (start, _end) in enumerate(windows)}
    all_candidates: dict[str, dict] = {}
    for bank_obj in banks.values():
        for entry in bank_obj.admissible():
            all_candidates.setdefault(entry.candidate_id, entry.params)
    incumbent_id = "incumbent_seed"
    all_candidates[incumbent_id] = dict(SEED_POINTS[ALPHA])

    def outcome_for(params):
        def _fn(start, end):
            window = bars[(bars.index >= start) & (bars.index < end)]
            if len(window) < 20:
                return None
            try:
                run = run_candidate(ALPHA, params, window)
            except Exception:
                return None
            metrics = window_metrics(run)
            return {"net_return": metrics["net_return"],
                    "max_drawdown": metrics["max_drawdown"],
                    "turnover": float(metrics["entries"]) * ACCOUNT["entry_notional_usdt"]
                    / ACCOUNT["initial_capital_usdt"],
                    "cost": float(metrics["fills"]) * ACCOUNT["taker_fee_rate"],
                    "trades": metrics["fills"], "exposure": metrics["exposure"],
                    "terminal_position": 0.0 if run.positions[-1] == 0 else float(
                        run.positions[-1])}
        return _fn

    context_lookup = {}
    for start, _end in windows:
        row = context_at(contexts["rows"], start)
        if row is not None and row["decision_eligible"]:
            context_lookup[start] = {"features": row["features"], "state_id": row["state_id"],
                                     "namespace": row["namespace"]}

    grids = {}
    with writer.attempt("L06.1.episodes") as att:
        for candidate_id, params in all_candidates.items():
            grids[candidate_id] = EP.build_episodes(
                decision_times=[s for s, _ in windows], contexts=context_lookup,
                candidate_id=candidate_id, parameter_version=BK.parameter_digest(params),
                outcome_fn=outcome_for(params), horizon_days=HORIZON_DAYS)
        att.detail = {"candidates": len(grids),
                      "episodes": sum(len(g.episodes) for g in grids.values())}

    # ---- L06.3 + L06.4 decisions at every episode boundary ------------
    scheduler = CL.Scheduler()
    book = CP.CampaignBook()
    for candidate_id in all_candidates:
        book.warmups[candidate_id] = CP.IndicatorWarmup(candidate_id, BANK_WARMUP_BARS,
                                                        bars_seen=BANK_WARMUP_BARS)
    ledger, responses = [], []
    response_status_counts: dict[str, int] = {}
    current_incumbent = incumbent_id
    last_switch_at = None

    # Guide 8.6: a switch is assessed at every eligible REGIME OBSERVATION, which is
    # the 4h inference boundary -- not at the 7-day episode boundary. Assessing only
    # when a new episode closes would tie the switch clock to the response clock, and
    # those are two of the four clocks guide 9.4 insists on keeping apart.
    assessment_times = [r["available_at"] for r in contexts["rows"]
                        if r["available_at"] >= cutoffs[0]]

    # Precompute each candidate's episode arrays ONCE. Episodes are laid out in time
    # order and outcome_available_at is monotonic in that order, so "usable at T" is a
    # prefix and bisect finds its length. Re-scanning every episode at every 4h
    # boundary would be about eight million iterations for no extra information.
    import bisect

    prepared: dict[str, dict] = {}
    for candidate_id, grid in grids.items():
        rows = sorted((e for e in grid.episodes if e.quality_eligible and e.net_return is not None
                       and e.outcome_status != EP.OUTCOME_UNFINISHED),
                      key=lambda e: e.outcome_available_at)
        prepared[candidate_id] = {
            "available": [e.outcome_available_at for e in rows],
            "decision_time": [e.decision_time for e in rows],
            "net_return": np.asarray([e.net_return for e in rows], dtype=float),
            "context": np.asarray([e.context_asof_decision for e in rows], dtype=float)
            if rows else np.zeros((0, 1)),
            "episode_id": [e.episode_id for e in rows],
            "order": np.asarray([window_index[e.decision_time] for e in rows], dtype=int),
        }

    def usable_prefix(candidate_id, when):
        data = prepared[candidate_id]
        return bisect.bisect_right(data["available"], when)

    with writer.attempt("L06.3-4.decide") as att:
        for i, decision_time in enumerate(assessment_times):
            scheduler.counters.inference += 1
            row = context_at(contexts["rows"], decision_time)
            if row is None:
                continue
            bank_cutoff = max([c for c in cutoffs if c <= decision_time], default=None)
            if bank_cutoff is None:
                continue
            scheduler.counters.switch_assessments += 1
            active = banks[bank_cutoff].admissible()

            inc_data = prepared[current_incumbent]
            inc_n = usable_prefix(current_incumbent, decision_time)
            inc_by_time = {inc_data["decision_time"][k]: inc_data["net_return"][k]
                           for k in range(inc_n)}
            estimates, costs = [], {}
            pooled = {}
            for entry in active:
                if entry.candidate_id == current_incumbent:
                    continue
                data = prepared.get(entry.candidate_id)
                if data is None:
                    continue
                n = usable_prefix(entry.candidate_id, decision_time)
                keep = [k for k in range(n) if data["decision_time"][k] in inc_by_time]
                if not keep:
                    continue
                cand_u = data["net_return"][keep]
                inc_u = np.asarray([inc_by_time[data["decision_time"][k]] for k in keep])
                ctx = data["context"][keep]
                ages = np.asarray([(decision_time - data["decision_time"][k]).total_seconds()
                                   / 86400.0 for k in keep])
                elig = np.ones(len(keep))
                ids = [data["episode_id"][k] for k in keep]
                order = data["order"][keep]
                # the pooled prior: an UNWEIGHTED mean over every eligible episode, so it
                # carries no information about the current context and is a genuine prior
                # rather than a second copy of the local estimate
                pooled.update(RS.pooled_delta_from({entry.candidate_id: cand_u - inc_u}))
                estimate = RS.estimate_response(
                    response_id=f"resp-{i}-{entry.candidate_id}",
                    candidate_id=entry.candidate_id, incumbent_id=current_incumbent,
                    x_t=np.asarray(row["features"], dtype=float),
                    contexts=ctx, ages_days=ages, eligibility=elig,
                    feature_weights=np.full(len(row["features"]),
                                            1.0 / len(row["features"])),
                    candidate_utility=cand_u, incumbent_utility=inc_u,
                    episode_ids=ids, order=order,
                    pooled_delta=pooled[entry.candidate_id])
                estimates.append(estimate)
                if len(responses) < 4000:
                    responses.append(estimate.as_record())
                response_status_counts[estimate.status] = response_status_counts.get(
                    estimate.status, 0) + 1
                costs[entry.candidate_id] = DC.transition_cost(
                    projected_turnover=1.0, fee_rate=ACCOUNT["taker_fee_rate"],
                    slippage_rate=ACCOUNT["slippage_bps"] / 1e4)

            outcome = DC.decide(
                selection_id=f"sel-{i}", decision_time=decision_time,
                incumbent_id=current_incumbent, estimates=estimates, costs=costs,
                quality_status=row["quality_status"],
                campaign_open=bool(book.open_campaigns()),
                last_switch_at=last_switch_at,
                bank_adequate=bool(active),
                warm_candidates={c for c, w in book.warmups.items()
                                 if w.status == CP.WARMUP_READY},
                data_cutoff=str(decision_time), bank_cutoff=str(bank_cutoff),
                model_version=row["namespace"],
                # guide 13.4: typed params on both sides, and the campaign version
                # the decision would replace
                incumbent_params=all_candidates.get(current_incumbent),
                candidate_params={entry.candidate_id: all_candidates.get(entry.candidate_id)
                                  for entry in active},
                campaign_version=BK.parameter_digest(
                    all_candidates.get(current_incumbent) or {}))
            ledger.append(outcome)
            if outcome.decision == DC.SWITCH_READY:
                book.request_activation(outcome.selection_id, outcome.challenger_id,
                                        decision_time, outcome.reason)
                current_incumbent = outcome.challenger_id
                last_switch_at = decision_time
                scheduler.counters.switches_executed += 1
        att.detail = {"decisions": len(ledger), "responses": len(responses)}

    # ---- L06.5 scheduling behaviour on the real cadence ---------------
    with writer.attempt("L06.5.clocks") as att:
        for k, cutoff in enumerate(cutoffs):
            job = scheduler.trigger(f"bank-{k}", CL.BANK_REFRESH, cutoff,
                                    "frozen baseline calendar")
            if job.status == CL.JOB_PENDING:
                scheduler.complete(job.job_id, cutoff + pd.Timedelta(hours=6))
                scheduler.activate(job.job_id, cutoff + pd.Timedelta(hours=6))
        att.detail = scheduler.counters.as_record()

    # ---- outputs ------------------------------------------------------
    panel = pd.concat([EP.to_frame(g) for g in grids.values()], ignore_index=True)
    panel_path = policy.resolve_write_target(
        LAB_ROOT / "evidence" / STUDY_ID / role["panel"])
    panel.to_parquet(panel_path, index=False)

    ledger_record = DC.summarize_ledger(ledger)
    informative = EP.informativeness(panel, incumbent_id)
    response_model = {
        "schema": "crypto_regime_lab.response_model.v1",
        "episode_informativeness": informative,
        "alpha_id": ALPHA, "symbol": SYMBOL,
        "horizon": horizon_note,
        "hyperparameters": RS.hyperparameters(),
        "responses": responses[:400],
        "response_count": int(sum(response_status_counts.values())),
        "status_counts": dict(sorted(response_status_counts.items())),
        "responses_sampled": len(responses),
        "supporting_neighbors_attached": all(
            r["supporting_episodes"] is not None for r in responses),
        "episode_panel_rows": int(len(panel)),
        "episode_panel_path": str(panel_path.relative_to(LAB_ROOT)),
    }
    bank_registry = {
        "schema": "crypto_regime_lab.bank_registry.v1",
        "alpha_id": ALPHA, "symbol": SYMBOL,
        "banks": {str(c): b.as_record() for c, b in banks.items()},
        "specialist_rule": BK.specialist_note(),
    }
    spec = DC.policy_spec()
    spec["clocks"] = scheduler.as_record()
    spec["campaigns"] = book.as_record(now=bars.index[-1])
    spec["counterfactual_limits"] = LM.counterfactual_limits()
    spec["initial_state_contract"] = LM.initial_state_contract()
    spec["expert_curve"] = LM.expert_curve_check(False)

    for payload in (response_model, bank_registry, spec, ledger_record):
        payload["data_role"] = ROLE
        payload["window"] = [str(bars.index[0]), str(bars.index[-1])]
    for stem, payload in (("response_model.json", response_model),
                          ("bank_registry.json", bank_registry),
                          ("policy_spec.json", spec),
                          ("decision_ledger.json", ledger_record)):
        writer.write_config(f"{role['prefix']}_{stem}", payload)
        writer.write_json(stem, payload, schema=payload.get("schema", stem))

    print(f"contexts         : {len(contexts['rows'])} emissions across "
          f"{len(contexts['namespaces'])} namespaces")
    print(f"role             : {ROLE}  bars {bars.index[0]} .. {bars.index[-1]}")
    print(f"discoveries      : {len(discoveries)} from {len(cutoffs)} selector cutoffs")
    print(f"banks            : sizes {[len(b.admissible()) for b in banks.values()]} "
          f"(proposed range {BK.BANK_MIN}-{BK.BANK_MAX})")
    rejected = sum(len(b.rejected) for b in banks.values())
    print(f"  rejected       : {rejected} (later discoveries + over-size), trial rows kept "
          f"{sum(b.trial_rows_retained for b in banks.values())}")
    print(f"horizon          : registered {horizon_note['registered_horizon_days']}d, measured "
          f"holding {horizon_note['measured_mean_holding_days']:.2f}d, covers="
          f"{horizon_note['horizon_covers_mean_holding']}")
    print(f"episodes         : {len(panel)} rows over {len(grids)} candidates")
    print(f"responses        : {len(responses)}  statuses={response_model['status_counts']}")
    print(f"informativeness  : {informative['pairs_with_zero_delta']}/{informative['pairs']} "
          f"cặp có delta đúng bằng 0 ({informative['share_uninformative']:.0%}) "
          f"-> episode không phân biệt được")
    print(f"decisions        : {ledger_record['decisions']} {ledger_record['counts']}")
    print("  nhịp đánh giá  : mọi biên 4h (guide 8.6), không phải biên episode 7 ngày")
    print(f"counters         : {scheduler.counters.as_record()}")
    print(f"evidence -> {writer.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
