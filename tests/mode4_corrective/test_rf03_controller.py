"""RF-03 controller acceptance — A10 semantics and the online trigger policy."""

from __future__ import annotations

from crypto_regime_lab.experiments.regime_schedule import online_trigger_schedule


def _at(iso: str, state_id: int, namespace: str = "v1", **kwargs) -> dict:
    return {"state_id": state_id, "state_namespace": namespace,
            "state_common": kwargs.get("common"), "decision_eligible": kwargs.get("eligible", True),
            "quality_status": kwargs.get("quality", "OK"), "available_at": iso}


def test_a10_a_namespace_change_alone_does_not_trigger():
    emissions = [_at("2024-01-01T00:00:00+00:00", 0, "v1"),
                 _at("2024-02-01T00:00:00+00:00", 0, "v2")]
    schedule = online_trigger_schedule(emissions, earliest="2024-01-01", latest="2024-06-01")
    assert schedule.cutoffs == (), schedule.source


def test_a10_an_ineligible_or_unknown_emission_does_not_trigger():
    emissions = [_at("2024-01-01T00:00:00+00:00", 0),
                 _at("2024-02-01T00:00:00+00:00", 1, eligible=False),
                 _at("2024-03-01T00:00:00+00:00", 2, quality="UNKNOWN_STATE")]
    schedule = online_trigger_schedule(emissions, earliest="2024-01-01", latest="2024-06-01")
    assert schedule.cutoffs == (), schedule.source


def test_a10_a_semantic_change_in_one_namespace_triggers():
    emissions = [_at("2024-01-01T00:00:00+00:00", 0),
                 _at("2024-02-01T00:00:00+00:00", 1)]
    schedule = online_trigger_schedule(emissions, earliest="2024-01-01", latest="2024-06-01")
    assert len(schedule.cutoffs) == 1
    assert schedule.cutoffs[0].startswith("2024-02-01")


def test_max_age_is_reported_as_max_age_not_as_a_regime():
    emissions = [_at("2024-01-01T00:00:00+00:00", 0),
                 _at("2024-02-01T00:00:00+00:00", 1),
                 _at("2024-09-01T00:00:00+00:00", 1)]
    schedule = online_trigger_schedule(emissions, earliest="2024-01-01", latest="2024-12-01",
                                       max_age_days=90.0)
    assert "MAX_AGE" in schedule.source
    assert len(schedule.cutoffs) == 2, schedule.cutoffs


def test_the_budget_caps_the_number_of_search_requests():
    emissions = [_at(f"2024-{month:02d}-01T00:00:00+00:00", month % 3)
                 for month in range(1, 10)]
    schedule = online_trigger_schedule(emissions, earliest="2024-01-01", latest="2024-12-01",
                                       min_gap_days=0.0, budget=2)
    assert len(schedule.cutoffs) <= 2, schedule.cutoffs


def test_a11_opposite_economic_contexts_are_not_collapsed():
    import numpy as np

    from crypto_regime_lab.policy.response import context_distance, context_distance_economic
    from crypto_regime_lab.regime.emissions import build_emission

    mu = np.array([[-2.0], [2.0]])
    emissions = []
    for k in (0, 1):
        costs = 0.5 * (mu[:, 0] - mu[k, 0]) ** 2
        emissions.append(build_emission(
            k, costs, namespace="v", z_t=mu[k], centroids=mu, weights=np.ones(1),
            groups={"G": [0]}, observed_at="2024-01-01", available_at="2024-01-01",
            inferred_at="2024-01-01", model_fit_cutoff="2023-12-31",
            ready_at="2023-12-31", version="v"))
    residual = context_distance(np.array(emissions[0].feature_contributions),
                                np.array(emissions[1].feature_contributions), np.ones(1))
    assert residual == 0.0, "the documented defect: residual-only context collapses"
    assert context_distance_economic(emissions[0], emissions[1], np.ones(1)) > 0, (
        "the repaired path compares raw economic coordinates")


def test_g4_the_legacy_oracle_is_quarantined_from_the_corrective_path():
    from pathlib import Path

    from crypto_regime_lab.experiments import evaluator as ev
    from crypto_regime_lab.integration import event_account as ea
    from crypto_regime_lab.quantbt_bridge import routes
    from crypto_regime_lab.selector import mode4_baseline as mb

    assert ev.LEGACY_FIXED_POINT_EVALUATOR == "QUARANTINED_UNSUPPORTED_PATH"
    corrective_source = "".join(Path(module.__file__).read_text(encoding="utf-8")
                                for module in (ea, routes, mb))
    assert "_exit_oracle" not in corrective_source
    assert "run_candidate_fixed_point_reference" not in corrective_source


def test_g5_engine_order_events_are_classified_as_rejections():
    from types import SimpleNamespace

    from crypto_regime_lab.integration.event_account import _rejection_reason

    assert _rejection_reason(SimpleNamespace(event_name="order_rejected")) == "order_rejected"
    assert _rejection_reason(SimpleNamespace(event_name="unsupported_command")) == "unsupported_command"
    assert _rejection_reason(SimpleNamespace(event_name="fill")) is None
    assert _rejection_reason(SimpleNamespace(status=2)) is None
