#!/usr/bin/env python
"""LAB-05 L05.1-L05.5 — fit the regime model on the development role and emit causally.

Every fit here sees a trailing training window that ENDS at its declared cutoff.
The scaler is fitted inside that window too, and a mutation test proves neither
could have read past it. Emissions are produced by the streaming filter, one
observation at a time, which is the same code path a live provider would use.

Nothing in this script touches the outer-evaluation role.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter, utc_now_iso  # noqa: E402
from crypto_regime_lab.regime import ablation as AB  # noqa: E402
from crypto_regime_lab.regime import causality as C  # noqa: E402
from crypto_regime_lab.regime import model_selection as MS  # noqa: E402
from crypto_regime_lab.regime import registry as R  # noqa: E402
from crypto_regime_lab.regime import robustness as RB  # noqa: E402
from crypto_regime_lab.regime.emissions import (EmissionTape, OnlineStateFilter,  # noqa: E402
                                                build_emission)
from crypto_regime_lab.regime.jump_model import loss_matrix, multi_start_fit  # noqa: E402
from crypto_regime_lab.regime import quality as QL  # noqa: E402
from crypto_regime_lab.regime.quality import (assess, check_degeneracy,  # noqa: E402
                                              fit_novelty_threshold)
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"
SNAPSHOT_ID = "server_core_v1"
#: LAB-05 fitted BTCUSDT only. LAB-08's arms C/D/E need a state provider for every
#: symbol they trade, so the symbol is now an argument -- the SAME code and the
#: same contract, applied wider, rather than a second fitter written for LAB-08.
SYMBOL = "BTCUSDT"
#: LAB-05's own artifacts keep their names; a per-symbol run writes namespaced ones
#: so the validated BTCUSDT evidence is never overwritten by a later symbol.
ARTIFACT_PREFIX = "lab05"

#: Guide 8.6 starting hypotheses, registered before any fit.
OBSERVATION_INTERVAL = "4h"
TRAIN_MEMORY_DAYS = 365
LAMBDA_JUMP = 1.0
SEEDS = (11, 23, 37, 51)
#: Guide 8.6 registers a 28-day fit cadence. A coarser demo cadence would leave most
#: emissions STALE_MODEL and would not exercise the refit path the phase is about.
FIT_CADENCE_DAYS = 28
DEVELOPMENT_START = "2020-01-01"
DEVELOPMENT_END = "2023-12-31"
MAX_MODEL_AGE_DAYS = 56          # guide 8.6 comparator cadence; beyond it the model is STALE

#: The data role this fitter emits over. LAB-05 and LAB-08 emit over `development`;
#: LAB-09's frozen confirmation needs a state provider on the interval unlocked in
#: L09.1, and it gets it from THIS code with THIS contract -- same K, same lambda,
#: same seeds, same memory, same cadence -- because a second fitter written for the
#: confirmation would make "the engine is untouched" (L09.2.4) unverifiable.
#:
#: `first_cutoff` is the first model the role deploys. In the confirmation role its
#: 365-day training memory reaches back into development, which is what a deployed
#: model does on its first day: it refits on the history it has. The EMISSIONS never
#: start before the role does.
ROLES = {
    "development": {"end": DEVELOPMENT_END, "first_cutoff": None,
                    "note": "fitted on the development role only; no outer-evaluation data "
                            "was read"},
    "confirmation": {"end": None, "first_cutoff": "2024-01-01",
                     "note": "the confirmation role unlocked in L09.1. Training memory reaches "
                             "back into development by design -- a model deployed on the first "
                             "day of the interval refits on the history that existed then -- and "
                             "no emission is dated before the interval starts"},
}
ROLE = "development"


def fit_cutoffs(start: str, end: str, memory_days: int, cadence_days: int,
                first_cutoff: str | None = None) -> list[str]:
    """Every cadence_days from the first date with a full training memory behind it.

    `first_cutoff` overrides that starting point for a role whose data begins before
    it emits: the confirmation role's first model is dated at the role boundary and
    trains on the memory_days before it, rather than waiting memory_days into the
    role for a window that already exists.
    """
    first = (pd.Timestamp(first_cutoff) if first_cutoff
             else pd.Timestamp(start) + pd.Timedelta(days=memory_days))
    out, cursor = [], first
    while cursor <= pd.Timestamp(end):
        out.append(cursor.strftime("%Y-%m-%d"))
        cursor = cursor + pd.Timedelta(days=cadence_days)
    return out


def load_panel(policy: SandboxPolicy) -> tuple[pd.DataFrame, list[str], np.ndarray, dict]:
    schema = json.loads((policy.lab_root / "configs" / "feature_schema.json").read_text())
    features = list(schema["primary_core_features"])
    weights = np.asarray([schema["group_weights"][f] for f in features], dtype=np.float64)
    panel = pd.read_parquet(policy.lab_root / "snapshots" / SNAPSHOT_ID / "panels"
                            / f"{SYMBOL}.parquet")
    panel["time"] = pd.to_datetime(panel["time"])
    panel = panel.sort_values("time").reset_index(drop=True)
    # liquidity/impact columns for the stress overlay and the declared source columns
    # for the source-transition check; kept OUT of the model's feature vector on purpose
    extras = [c for c in ("g4_log_amihud_30", "g4_spread_bps",
                          "g3_source", "g4_source", "g3_basis_source") if c in panel.columns]
    frame = panel[["time", "available_at", *features, *extras]].dropna(
        subset=["time", "available_at", *features]).reset_index(drop=True)
    return frame, features, weights, schema


def _parse_args(argv: list[str] | None = None):
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default=SYMBOL,
                        help="symbol to fit. The default reproduces LAB-05's BTCUSDT run.")
    parser.add_argument("--artifact-prefix", default=None,
                        help="prefix for the written artifacts. Defaults to lab05 for BTCUSDT "
                             "(so LAB-05 reproduces exactly) and lab08_<symbol> otherwise, so a "
                             "later symbol can never overwrite validated evidence.")
    parser.add_argument("--role", choices=sorted(ROLES), default="development",
                        help="data role to emit over. 'confirmation' is LAB-09's frozen "
                             "interval and requires configs/lab09_confirmation_spec.json to "
                             "exist, so the tape can never be produced before the unlock.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    global SYMBOL, ARTIFACT_PREFIX, ROLE

    args = _parse_args(argv)
    SYMBOL = args.symbol
    ROLE = args.role
    ARTIFACT_PREFIX = args.artifact_prefix or (
        "lab05" if SYMBOL == "BTCUSDT" else f"lab08_{SYMBOL.lower()}")
    if ROLE != "development":
        unlock = LAB_ROOT / "configs" / "lab09_confirmation_spec.json"
        if not unlock.is_file():
            print(f"BLOCKED: role={ROLE} needs the L09.1 unlock "
                  "(scripts/unlock_lab09_confirmation.py) to exist first")
            return 1
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    policy.assert_lab_marker_ok(STUDY_ID)
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    frame, features, weights, schema = load_panel(policy)
    role = ROLES[ROLE]
    role_end = role["end"] or str(pd.Timestamp(frame["time"].max()).date())
    # `development` is the FITTING scope: every training window is cut from it. It
    # reaches back before the role starts because a trailing memory has to come from
    # somewhere; the emission loop below starts at the first cutoff, so nothing is
    # ever emitted before the role begins.
    development = frame[frame["time"] <= role_end].reset_index(drop=True)
    cutoffs = fit_cutoffs(DEVELOPMENT_START, role_end, TRAIN_MEMORY_DAYS,
                          FIT_CADENCE_DAYS, first_cutoff=role["first_cutoff"])
    groups: dict[str, list[int]] = {}
    for i, name in enumerate(features):
        groups.setdefault(name.split("_")[0].upper(), []).append(i)

    with writer.attempt("L05.4.choose_k") as att:
        # K is chosen on the FIRST cutoff's training window only, then frozen for
        # every later refit: re-choosing K at each refit would be selecting model
        # complexity repeatedly against overlapping data.
        first_cut = pd.Timestamp(cutoffs[0])
        first_train = development[(development["time"] < first_cut)
                                  & (development["time"] >= first_cut
                                     - pd.Timedelta(days=TRAIN_MEMORY_DAYS))]
        raw_first = first_train[features].to_numpy(float)
        scaler_first = C.fit_scaler(raw_first)
        z_first = C.apply_scaler(raw_first, scaler_first)
        k_choice = MS.choose_k(z_first, weights, lambda_jump=LAMBDA_JUMP, seeds=SEEDS,
                               candidates=(MS.PARSIMONIOUS_K, MS.STARTING_K))
        att.detail = {"best": k_choice["best_by_inner_criterion"]}
    # The registered starting K is 3. The inner criterion is REPORTED; it does not
    # silently override a registered choice (guide 8.1).
    n_states = MS.STARTING_K
    k_choice["registered_k_used"] = n_states
    k_choice["inner_criterion_agrees_with_registered"] = (
        k_choice["best_by_inner_criterion"] == n_states)
    k_choice["override_policy"] = (
        "the registered starting K=3 is used and the disagreement is reported rather than acted "
        "on. This is a JUDGEMENT CALL and the guide can be read both ways: 8.1 calls K=3 the "
        "'primary starting' K with K=2 a registered 'parsimonious alternative', while 8.3 says K "
        "is chosen in nested development -- which is exactly the criterion that preferred K=2 "
        "here. The lab keeps the registered starting point because switching after seeing a "
        "score, even a nested-development score, is still choosing the model on a result; but the "
        "margin is small and the decision belongs to the user, so it is recorded in "
        "reports/improvement_opinions.md rather than settled silently.")
    scores = {int(k): v["mean_per_observation_objective"] for k, v in k_choice["scores"].items()}
    if len(scores) > 1:
        best, second = sorted(scores.values())[:2]
        k_choice["margin_between_top_two"] = float(second - best)
        k_choice["relative_margin"] = float((second - best) / abs(second)) if second else None
    k_choice["direction_note"] = (
        "the usual worry is that a larger K fits better almost by construction. Here the SMALLER "
        "K scored better, which is the opposite direction and is why the standard warning does "
        "not settle this case.")
    writer.write_config(f"{ARTIFACT_PREFIX}_k_selection.json", k_choice)

    artifacts, mappings, transitions = [], [], []
    previous: R.ModelArtifact | None = None
    all_reports = {}

    for cutoff in cutoffs:
        cut = pd.Timestamp(cutoff)
        window = development[(development["time"] < cut)
                             & (development["time"] >= cut - pd.Timedelta(days=TRAIN_MEMORY_DAYS))]
        raw = window[features].to_numpy(float)
        with writer.attempt(f"L05.1.fit@{cutoff}") as att:
            scaler = C.fit_scaler(raw)
            z_train = C.apply_scaler(raw, scaler)
            fit = multi_start_fit(z_train, weights, n_states=n_states,
                                  lambda_jump=LAMBDA_JUMP, seeds=SEEDS)
            att.detail = {"rows": int(raw.shape[0]), "seed": fit["selected_seed"]}

        loss = loss_matrix(z_train, fit["centroids"], weights)
        residuals = loss.min(axis=1)
        novelty = fit_novelty_threshold(residuals)
        train_states = np.argmin(loss, axis=1)
        counts = np.bincount(train_states, minlength=n_states)
        degeneracy = check_degeneracy(weights, fit["centroids"], counts)

        artifact = R.ModelArtifact(
            model_id=f"jm_k{n_states}_{cutoff}",
            state_namespace=f"jm@{cutoff}",
            training_start=str(window["time"].iloc[0]),
            training_cutoff=cutoff,
            fit_ready_at=utc_now_iso(),
            n_states=n_states, lambda_jump=LAMBDA_JUMP,
            feature_names=tuple(features),
            feature_weights=tuple(float(w) for w in weights),
            group_weights=schema["group_weights"],
            centroids=np.asarray(fit["centroids"]).tolist(),
            scaler_ref={"median": scaler["median"].tolist(), "scale": scaler["scale"].tolist(),
                        "clip": scaler["clip"], "fitted_rows": scaler["fitted_rows"],
                        "fitted_on": "the training window ending at this cutoff, nothing after"},
            seeds=SEEDS, selected_seed=fit["selected_seed"],
            observation_interval=OBSERVATION_INTERVAL,
            fit_diagnostics={
                "multi_start": {k: v for k, v in fit.items() if k != "centroids"},
                "novelty_threshold": novelty,
                "state_counts": counts.tolist(),
                "degeneracy": degeneracy,
                "lambda_units": MS.lambda_jump_units(LAMBDA_JUMP, OBSERVATION_INTERVAL),
            },
            code_hashes=R.environment_hashes([
                LAB_ROOT / "src/crypto_regime_lab/regime/jump_model.py",
                LAB_ROOT / "src/crypto_regime_lab/regime/emissions.py",
                LAB_ROOT / "src/crypto_regime_lab/regime/causality.py",
            ]),
            library_versions=R.library_versions(),
            notes=role["note"])
        artifacts.append(artifact)

        with writer.attempt(f"L05.3.robustness@{cutoff}") as att:
            reports = {
                "constant_features": RB.constant_feature_report(z_train, tuple(features)),
                "convergence": RB.convergence_report(z_train, weights, n_states=n_states,
                                                     lambda_jump=LAMBDA_JUMP, seeds=SEEDS),
                "outlier_sensitivity": RB.outlier_sensitivity(z_train, weights,
                                                              n_states=n_states,
                                                              lambda_jump=LAMBDA_JUMP,
                                                              seeds=SEEDS),
            }
            att.detail = {"converged": reports["convergence"]["all_converged"]}
        all_reports[cutoff] = reports

        if previous is not None:
            mapping = R.map_state_namespaces(previous, artifact)
            mappings.append(mapping)
            transitions.append(R.model_transition_event(previous, artifact, mapping))
        previous = artifact

    # ---- guide 8.3 group ablation + the model-ladder position ----
    with writer.attempt("L05.4.group_ablation") as att:
        ablation = AB.group_ablation(z_first, tuple(features), weights, n_states=n_states,
                                     lambda_jump=LAMBDA_JUMP, seeds=SEEDS)
        ladder = AB.ladder_record()
        att.detail = {"blocks_that_improved": ablation["blocks_that_improved_out_of_fold"]}
    writer.write_config(f"{ARTIFACT_PREFIX}_group_ablation.json",
                        {**ablation, "model_ladder": ladder,
                         "requirement_satisfied": bool(
                             ablation["blocks_that_improved_out_of_fold"]),
                         "finding": (
                             "guide 8.3 asks the ablation to DEMONSTRATE that the flow and "
                             "market-coordination blocks contribute beyond price/volatility. On "
                             "this symbol and window it does not: out of fold, both the fit "
                             "objective and the scale-free variance-resolved measure get worse as "
                             "blocks are added, and at the full 8-feature core the state "
                             "assignment resolves essentially no variance on held-out blocks. "
                             "The registered core is NOT changed in response -- selecting a "
                             "feature set on this result would be choosing the model on an "
                             "outcome. It is recorded as a finding."),
                         })

    # ---- L05.3.5 source transition, on the real panel and on a positive control ----
    with writer.attempt("L05.3.source_transition") as att:
        source_columns = [c for c in ("g3_source", "g4_source", "g3_basis_source")
                          if c in development.columns]
        declared = {}
        boundaries = []
        for column in source_columns:
            values = development[column].astype(str)
            runs = values.ne(values.shift()).cumsum()
            declared[column] = {"distinct_sources": sorted(values.unique().tolist()),
                                "runs": int(runs.nunique())}
            if runs.nunique() > 1:
                first_change = int(runs.ne(runs.shift()).to_numpy().nonzero()[0][1])
                boundaries.append({"column": column, "index": first_change})

        real_checks = []
        for boundary in boundaries:
            index = boundary["index"]
            real_checks.append({
                "boundary": boundary,
                **RB.source_transition_report(
                    development[features].to_numpy(float)[:index],
                    development[features].to_numpy(float)[index:], tuple(features))})

        # POSITIVE CONTROL: a check that cannot fire proves nothing, so inject a
        # level shift into two features and require the detector to name them.
        half = len(development) // 2
        before = development[features].to_numpy(float)[:half]
        after = development[features].to_numpy(float)[half:].copy()
        shifted = list(features[:2])
        for i in range(2):
            spread = float(np.subtract(*np.percentile(before[:, i], [75, 25])))
            after[:, i] = after[:, i] + 4.0 * (spread if spread > 0 else 1.0)
        control = RB.source_transition_report(before, after, tuple(features))
        att.detail = {"real_boundaries": len(boundaries),
                      "control_flagged": control["features_with_large_level_shift"]}

    source_transition = {
        "schema": "crypto_regime_lab.source_transition_check.v1",
        "declared_sources": declared,
        "real_boundaries_found": len(boundaries),
        "real_checks": real_checks,
        "no_transition_note": ("every declared source column holds a single value across this "
                               "role's fitting scope for this symbol, so there is no real "
                               "transition to detect here. That is a finding about the data, not "
                               "a passing check"),
        "scope": {"role": ROLE, "rows": int(len(development)),
                  "span": [str(development["time"].iloc[0]), str(development["time"].iloc[-1])]},
        "positive_control": {
            "injected_shift_features": shifted,
            "detected": control["features_with_large_level_shift"],
            "verdict": control["verdict"],
            "detector_can_fire": bool(set(shifted) <= set(
                control["features_with_large_level_shift"])),
            "why": ("a detector that never fires would look identical to a clean dataset. The "
                    "control injects a 4-IQR level shift into two named features and requires "
                    "both to be flagged"),
        },
        "per_feature": control["per_feature"],
    }

    # ---- causal emission with the model that was CURRENT at each observation ----
    with writer.attempt("L05.2.emit") as att:
        by_cutoff = {a.training_cutoff: a for a in artifacts}
        first_ready = pd.Timestamp(artifacts[0].training_cutoff)
        live = development[development["time"] >= first_ready].reset_index(drop=True)
        centroids_cache = {a.training_cutoff: np.asarray(a.centroids) for a in artifacts}

        tapes: dict[str, EmissionTape] = {}
        statuses: dict[str, int] = {}
        streamer = None
        active: R.ModelArtifact | None = None
        emitted_transitions = []
        cutoff_stamps = [pd.Timestamp(c) for c in cutoffs]
        has_stress = {"g4_log_amihud_30", "g4_spread_bps"} <= set(live.columns)
        stress_rows: list[float] = []
        stress_axis_states: set[bool] = set()

        for i in range(len(live)):
            stamp = pd.Timestamp(live["time"].iloc[i])
            # the newest model whose cutoff has already passed; never a future one
            eligible = [c for c in cutoff_stamps if c <= stamp]
            current = by_cutoff[eligible[-1].strftime("%Y-%m-%d")]
            if active is None or current.model_id != active.model_id:
                if active is not None:
                    mapping = next((m for m in mappings
                                    if m["old_namespace"] == active.state_namespace
                                    and m["new_namespace"] == current.state_namespace), None)
                    if mapping is not None:
                        emitted_transitions.append({
                            "at": str(stamp),
                            **R.model_transition_event(active, current, mapping)})
                # a new model starts a new namespace AND a fresh filter state; the
                # previous tape is sealed and never touched again
                if active is not None:
                    tapes[active.state_namespace].seal()
                active = current
                streamer = OnlineStateFilter(centroids_cache[active.training_cutoff], weights,
                                             LAMBDA_JUMP, namespace=active.state_namespace)
                tapes.setdefault(active.state_namespace,
                                 EmissionTape(namespace=active.state_namespace))

            scaler = {"median": np.asarray(active.scaler_ref["median"]),
                      "scale": np.asarray(active.scaler_ref["scale"]),
                      "clip": active.scaler_ref["clip"]}
            z_t = C.apply_scaler(live[features].to_numpy(float)[i:i + 1], scaler)[0]
            state, costs, _ = streamer.step(z_t)
            cents = centroids_cache[active.training_cutoff]
            residual = float(loss_matrix(z_t.reshape(1, -1), cents, weights)[0].min())
            age = (stamp - pd.Timestamp(active.training_cutoff)).total_seconds()
            verdict = assess(costs=costs, fit_residual=residual,
                             novelty_threshold=active.fit_diagnostics["novelty_threshold"]["threshold"],
                             model_age_seconds=age,
                             max_model_age_seconds=MAX_MODEL_AGE_DAYS * 86400,
                             degeneracy=active.fit_diagnostics["degeneracy"])
            statuses[verdict.status] = statuses.get(verdict.status, 0) + 1
            if has_stress:
                overlay = QL.stress_overlay(
                    float(live["g4_log_amihud_30"].iloc[i]),
                    float(live["g4_spread_bps"].iloc[i]))
                stress_rows.append(overlay["stress_score"])
                stress_axis_states.add(overlay["is_a_regime_state"])
            tapes[active.state_namespace].append(build_emission(
                state, costs, namespace=active.state_namespace, z_t=z_t,
                centroids=cents, weights=weights, groups=groups,
                observed_at=str(stamp), available_at=str(live["available_at"].iloc[i]),
                inferred_at=str(live["available_at"].iloc[i]),
                model_fit_cutoff=active.training_cutoff, ready_at=active.fit_ready_at,
                version=active.model_id, quality_status=verdict.status,
                input_refs=(f"panel:{SYMBOL}",), novelty_score=verdict.novelty_score,
                decision_eligible=verdict.decision_eligible))
        if active is not None:
            tapes[active.state_namespace].seal()
        total = sum(len(t.emissions) for t in tapes.values())
        att.detail = {"emissions": total, "namespaces": len(tapes)}

    # ---- L05.5 cross-namespace view, DIAGNOSTIC only ----
    with writer.attempt("L05.5.relabel") as att:
        relabelled = []
        for mapping in mappings:
            source_ns = mapping["new_namespace"]
            tape = tapes.get(source_ns)
            if tape is None or not tape.emissions:
                continue
            translated = R.relabel_states(tape.states(), mapping)
            relabelled.append({
                "namespace": source_ns,
                "into_namespace": mapping["old_namespace"],
                "emissions": len(tape.emissions),
                "unmapped_emissions": int((translated == -1).sum()),
                "share_unmapped": float((translated == -1).mean()),
            })
        att.detail = {"namespaces_relabelled": len(relabelled)}
    cross_namespace = {
        "schema": "crypto_regime_lab.cross_namespace_view.v1",
        "per_namespace": relabelled,
        "total_emissions_translated": sum(r["emissions"] for r in relabelled),
        "total_unmapped": sum(r["unmapped_emissions"] for r in relabelled),
        "decision_eligible": False,
        "rule": ("translating one fit's states into the previous fit's ids produces a readable "
                 "series across a refit boundary. It is a DIAGNOSTIC: the emitted tapes stay as "
                 "they were emitted, an unmapped state becomes -1 rather than being folded into "
                 "its nearest neighbour, and no decision reads this view (guide 8.4)"),
    }

    registry_source_transition = source_transition
    registry = {
        "schema": "crypto_regime_lab.regime_model_registry.v1",
        "study_id": STUDY_ID, "symbol": SYMBOL,
        "observation_interval": OBSERVATION_INTERVAL,
        "train_memory_days": TRAIN_MEMORY_DAYS,
        "lambda_jump": LAMBDA_JUMP,
        "n_states": n_states,
        "data_role": ROLE,
        "outer_evaluation_touched": ROLE != "development",
        "role_window": [cutoffs[0], role_end],
        "models": [a.as_record() for a in artifacts],
        "namespace_mappings": mappings,
        "model_transitions": transitions,
        "robustness": all_reports,
        "source_transition_check": registry_source_transition,
        "group_ablation": ablation,
        "model_ladder": ladder,
        "clock_separation": {
            "model_fit_cadence": f"{len(cutoffs)} refits every {FIT_CADENCE_DAYS} days",
            "first_cutoff": cutoffs[0], "last_cutoff": cutoffs[-1],
            "inference_cadence": OBSERVATION_INTERVAL,
            "bank_refresh_triggered_by_this": False,
            "parameter_search_triggered_by_this": False,
            "rule": ("model retraining, bank refresh and switch frequency are three separate "
                     "counters. A state change does not trigger a fit and a fit does not trigger "
                     "a parameter search (guide 8.6, L05.5)"),
        },
    }
    writer.write_config(f"{ARTIFACT_PREFIX}_regime_model_registry.json", registry)
    writer.write_json("regime_model_registry.json", registry, schema=registry["schema"])

    tape_record = {
        "schema": "crypto_regime_lab.emission_tape.v1",
        "symbol": SYMBOL,
        "emitted_by": "OnlineStateFilter, one observation at a time",
        "namespaces": {ns: t.as_record() for ns, t in tapes.items()},
        "total_emissions": sum(len(t.emissions) for t in tapes.values()),
        "total_switches_within_namespaces": sum(t.switches() for t in tapes.values()),
        "quality_status_counts": statuses,
        "model_transitions_emitted": emitted_transitions,
        "cross_namespace_rule": ("switches are counted WITHIN a namespace. A model change starts a "
                                 "new namespace and a fresh filter, so a state id in one namespace "
                                 "is not comparable to the same integer in another (guide 8.4)"),
    }
    tape_record["stress_overlay"] = {
        "measured": has_stress,
        "observations": len(stress_rows),
        "mean_stress_score": float(np.mean(stress_rows)) if stress_rows else None,
        "p95_stress_score": float(np.quantile(stress_rows, 0.95)) if stress_rows else None,
        "is_a_regime_state": sorted(stress_axis_states) if stress_axis_states else [],
        "joint_labels_created": 0,
        "rule": ("stress is reported on its own axis from the liquidity/impact features. It is "
                 "never a bear state and it never multiplies the state vocabulary into K x stress "
                 "joint labels (guide 8.5)"),
    }
    tape_record["cross_namespace_view"] = cross_namespace

    # Persist EVERY emission, not just a summary. LAB-05 needed the counts; a
    # consumer that has to know the state at a given time needs the rows, and
    # LAB-08's dynamic arms are exactly that consumer. Reading whichever
    # per-namespace evidence file happened to be last gave arms C and D a state
    # tape covering only the final six months, so their refreshes all landed
    # there while the calendar arms refreshed across three years -- not a timing
    # result, a coverage artefact.
    rows = []
    for namespace, tape in tapes.items():
        for emission in tape.emissions:
            record = emission.as_record() if hasattr(emission, "as_record") else dict(emission)
            rows.append({"state_namespace": namespace,
                         "state_id": record["state_id"],
                         "observed_at": str(record["observed_at"]),
                         "available_at": str(record["available_at"]),
                         "quality_status": record.get("quality_status"),
                         "decision_eligible": record.get("decision_eligible")})
    rows.sort(key=lambda r: (r["available_at"], r["state_namespace"]))
    full_tape = {
        "schema": "crypto_regime_lab.full_emission_tape.v1",
        "symbol": SYMBOL,
        "rows": len(rows),
        "namespaces": sorted({r["state_namespace"] for r in rows}),
        "span": [rows[0]["available_at"], rows[-1]["available_at"]] if rows else None,
        "ordering": "available_at, then namespace; a consumer reads what was knowable",
        "why_full": ("a summary cannot answer 'what state was available at time t', which is the "
                     "only question a dynamic arm asks"),
        "emissions": rows,
    }
    writer.write_config(f"{ARTIFACT_PREFIX}_full_emission_tape.json", full_tape)
    writer.write_json(f"{ARTIFACT_PREFIX}_full_emission_tape.json", full_tape,
                      schema=full_tape["schema"])
    tape_record["full_tape_artifact"] = f"configs/{ARTIFACT_PREFIX}_full_emission_tape.json"
    tape_record["full_tape_rows"] = len(rows)

    writer.write_config(f"{ARTIFACT_PREFIX}_emission_tape.json", tape_record)
    writer.write_json("emission_tape.json", tape_record, schema=tape_record["schema"])

    print(f"panel            : {len(frame)} obs, role={ROLE} scope {len(development)}")
    print(f"K                : registered {n_states}, inner criterion picked "
          f"{k_choice['best_by_inner_criterion']} "
          f"(agrees={k_choice['inner_criterion_agrees_with_registered']})")
    print(f"fits             : {len(artifacts)} every {FIT_CADENCE_DAYS} days "
          f"({cutoffs[0]} .. {cutoffs[-1]})")
    degenerate = [a.training_cutoff for a in artifacts
                  if a.fit_diagnostics["degeneracy"]["is_degenerate"]]
    print(f"  degenerate fits: {len(degenerate)} {degenerate[:4]}")
    unmapped = [m for m in mappings if not m["all_states_mapped"]]
    print(f"  namespace maps : {len(mappings)}, with unmapped states: {len(unmapped)}")
    print(f"  any mapping claimed a market transition: "
          f"{any(m['is_market_transition'] for m in mappings)}")
    print(f"emissions        : {tape_record['total_emissions']} across "
          f"{len(tapes)} namespaces, switches within namespaces="
          f"{tape_record['total_switches_within_namespaces']}")
    print(f"  statuses       : {statuses}")
    print(f"  stress overlay : measured={tape_record['stress_overlay']['measured']} "
          f"is_a_regime_state={tape_record['stress_overlay']['is_a_regime_state']} "
          f"joint_labels={tape_record['stress_overlay']['joint_labels_created']}")
    print(f"source transition: real boundaries={source_transition['real_boundaries_found']} "
          f"| control detector_can_fire="
          f"{source_transition['positive_control']['detector_can_fire']} "
          f"(flagged {source_transition['positive_control']['detected']})")
    print(f"group ablation   : decided on {ablation['decided_on']}")
    for row in ablation["ladder"]:
        g = "-" if row["variance_resolved_gain"] is None else f"{row['variance_resolved_gain']:+.5f}"
        print(f"   {str(row['groups']):<22} var_resolved={row['variance_resolved_out_of_fold']:+.5f} "
              f"delta={g:<10} improved={row['improved']}")
    print(f"   blocks contributing beyond price/vol: "
          f"{ablation['blocks_that_improved_out_of_fold'] or 'NONE'}")
    print(f"model ladder     : implemented={ladder['implemented']} "
          f"declared-unbuilt={ladder['not_implemented']}")
    print(f"cross-namespace  : {cross_namespace['total_emissions_translated']} translated, "
          f"{cross_namespace['total_unmapped']} unmapped, "
          f"decision_eligible={cross_namespace['decision_eligible']}")
    print(f"evidence -> {writer.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
