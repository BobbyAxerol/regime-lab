"""Guide FP01.2 findings: the 9-row map proved against current source.

Dispositions use the guide's own vocabulary (PRESENT / FIXED_WITH_PROOF /
SUPERSEDED_PATH_QUARANTINED / NOT_REPRODUCED_WITH_SCOPE / NEEDS_RUNTIME). A
repair row points at the FP-01 test that forces it plus the evidence artifact
that proves the current state; a PRESENT row names the future phase that must
go through the new guard. Nothing here edits history: published runs keep
their outputs and are cited via invalidated_by / recomputed_from refs.
"""
from __future__ import annotations

FINDING_IDS = tuple(f"FP-F{i:02d}" for i in range(1, 10))

ALLOWED_DISPOSITIONS = (
    "PRESENT",
    "FIXED_WITH_PROOF",
    "SUPERSEDED_PATH_QUARANTINED",
    "NOT_REPRODUCED_WITH_SCOPE",
    "NEEDS_RUNTIME",
)


def finding_rows(lab_run_id: str) -> list[dict]:  # noqa: ARG001
    """The 9 FP-01.2 rows, dispositions assessed against current source."""
    return [
        {
            "finding_id": "FP-F01",
            "audit_finding": ("Development ngoài window nhưng nằm ở tương lai: "
                              "calibration inputs outside the evaluation window but in "
                              "the future can steer the calibration."),
            "required": "Enforce before-evaluation và availability",
            "current_disposition": "FIXED_WITH_PROOF",
            "evidence_refs": [
                "src/crypto_regime_lab/fp/availability.py::development_prefix/"
                "assert_available/window_dwell_profile",
                "tests/fp_corrective/test_fp01_validity.py::"
                "test_fp01_t01_future_only_emissions_do_not_change_calibration",
            ],
            "affected_paths": [
                "src/crypto_regime_lab/fp/availability.py",
            ],
            "verification": ("FP01-T01: future-only mutations leave the pre-evaluation "
                             "profile identical; one prefix move shifts it; missing "
                             "boundary and unavailable-at-decision both refuse."),
            "planned_phase": "FP-03 (calibration origins) / FP-05 (labels) must pass "
                             "through this guard",
            "claim_limit": ("No calibration input at/after the declared evaluation "
                            "boundary may feed a profile; the tail rides along."),
        },
        {
            "finding_id": "FP-F02",
            "audit_finding": ("Admission tính sau deployment: ra05_discovery.run_one_arm "
                              "ran the full account first, then recorded admission as a "
                              "descriptive funnel; the deep-dive ran no admission at all."),
            "required": "Wire admission trước account consumes params",
            "current_disposition": "FIXED_WITH_PROOF",
            "evidence_refs": [
                "src/crypto_regime_lab/experiments/dynamic_fold_provider.py::"
                "run_cutoff_walk_forward(admission_policy=...) + admission_wiring lineage",
                "src/crypto_regime_lab/fp/admission_wiring.py",
                "tests/fp_corrective/test_fp01_engine_path.py::"
                "test_fp01_t02_forced_rejection_keeps_rejected_params_out_of_the_account",
            ],
            "affected_paths": [
                "src/crypto_regime_lab/experiments/dynamic_fold_provider.py",
                "src/crypto_regime_lab/fp/admission_wiring.py",
            ],
            "verification": ("FP01-T02 on the real engine path: forced rejection of "
                             "every fold yields NO_ADMITTED_DEPLOYMENT with empty "
                             "equity/fills (never PnL=0); the admission-OFF control "
                             "consumes the rejected params; forced admission deploys "
                             "exactly the raw stock record."),
            "planned_phase": "FP-07 locked study passes an admission_policy; FP-02 "
                             "re-qualifies the route with the wiring on",
            "claim_limit": ("Runs published before this repair used the unwired path; "
                            "they keep outputs, cited as invalidated_by FP-F02-wiring "
                            "for any future admission claim, never edited."),
            "upgrade_type": "CORRECTNESS_REPAIR",
            "invalidated_runs": [
                "evidence/regime_time_edge_ra_v1/ra05-20260918T201236Z-de11db62",
                "evidence/regime_time_edge_ra_v1/ra07decaydive-20260920T050551Z-97948f72",
                "evidence/regime_time_edge_ra_v1/fup05placebo-20260921T125029Z-32fc0c83",
            ],
        },
        {
            "finding_id": "FP-F03",
            "audit_finding": ("Warmup lẫn statistical window: warmup bars counted "
                              "inside the statistical sample."),
            "required": "Compute returns với prior equity rồi clip đúng",
            "current_disposition": "NOT_REPRODUCED_WITH_SCOPE",
            "evidence_refs": [
                "src/crypto_regime_lab/experiments/time_edge_contracts.py::daily_returns",
                "src/crypto_regime_lab/time_edge/execution.py::TrainingScorer._score",
                "tests/fp_corrective/test_fp01_validity.py::"
                "test_fp01_t04_warmup_outside_evaluation_does_not_grow_sample_count",
            ],
            "affected_paths": [
                "src/crypto_regime_lab/experiments/time_edge_contracts.py",
                "src/crypto_regime_lab/time_edge/execution.py",
            ],
            "verification": ("FP01-T04: 31 more warmup marks before the window leave "
                             "sample count AND every reported return unchanged."),
            "planned_phase": "FP-02 re-measures on the qualified route",
            "claim_limit": "Warmup handling is a measured property of the boundary "
                           "functions, never prose.",
        },
        {
            "finding_id": "FP-F04",
            "audit_finding": ("D1 mất first return: ra07_decay._deployment_slice measured "
                              "the first in-window return from the first IN-WINDOW mark, "
                              "dropping one observation versus the IS side."),
            "required": "Boundary/partition reconciliation",
            "current_disposition": "FIXED_WITH_PROOF",
            "evidence_refs": [
                "src/crypto_regime_lab/fp/decay_bounds.py::windowed_returns + reconcile",
                "src/crypto_regime_lab/ra/ra07_decay.py::_deployment_slice (untouched, "
                "RA-07 published)",
                "tests/fp_corrective/test_fp01_validity.py::"
                "test_fp01_t03_boundary_keeps_exactly_two_returns_on_100_120_108",
                "evidence/forward_persistence_fp_v1/<run_id>/decay_reconciliation.json",
            ],
            "affected_paths": [
                "src/crypto_regime_lab/fp/decay_bounds.py",
            ],
            "verification": ("FP01-T03: 100->120->108 yields exactly [0.2, -0.1]; legacy "
                             "reproduces exactly one; no prior mark -> explicit "
                             "PRIOR_EQUITY_UNAVAILABLE, never an invented 1.0."),
            "planned_phase": "FP-07 D1 uses fp/decay_bounds.windowed_returns; RA-07 rows "
                             "are recomputed_from, never overwritten",
            "claim_limit": ("Published D1 rows keep values; any FP headline quoting "
                            "them states the legacy dropped-first-return convention."),
            "upgrade_type": "REPORT_OR_METRIC_FIX",
        },
        {
            "finding_id": "FP-F05",
            "audit_finding": ("IS/OOS sizing khác nhau: IS scoring vs forward deployment "
                              "could run different economics."),
            "required": "Shared economic contract",
            "current_disposition": "NOT_REPRODUCED_WITH_SCOPE",
            "evidence_refs": [
                "src/crypto_regime_lab/experiments/dynamic_fold_provider.py::"
                "ACCOUNT_CAPITAL/ONE_WAY_TAKER_FEE/SLIPPAGE_BPS (single constants)",
                "tests/fp_corrective/test_fp01_engine_path.py::"
                "test_fp01_t05_same_params_data_economics_reach_parity",
            ],
            "affected_paths": [
                "src/crypto_regime_lab/experiments/dynamic_fold_provider.py",
                "src/crypto_regime_lab/integration/event_account.py",
            ],
            "verification": ("FP01-T05 on the real engine: IS scorer vs deployment "
                             "account reach rtol=1e-9 equity parity; capitals equal "
                             "at 20000."),
            "planned_phase": "FP-02 route qualification re-proves parity",
            "claim_limit": "Parity is measured per route pair/version, not a standing "
                           "certificate.",
        },
        {
            "finding_id": "FP-F06",
            "audit_finding": ("Verdict không trực tiếp so treatment: FUP-05's "
                              "CADENCE_ARTIFACT came from a placebo-vs-BAND comparison, "
                              "never a direct REGIME_TIMING-minus-comparator contrast."),
            "required": "New claim logic dựa contrast đúng",
            "current_disposition": "FIXED_WITH_PROOF",
            "evidence_refs": [
                "src/crypto_regime_lab/fp/claim_logic.py::timing_verdict",
                "tests/fp_corrective/test_fp01_validity.py::"
                "test_fp01_claim_logic_band_alone_cannot_form_a_verdict",
            ],
            "affected_paths": [
                "src/crypto_regime_lab/fp/claim_logic.py",
            ],
            "verification": ("Band-only refuses with the missing contrast named; direct "
                             "below/above decide artifact/survived; unsigned delta is "
                             "not inferred."),
            "planned_phase": "FP-09 verdicts must call fp/claim_logic with the paired "
                             "direct contrast",
            "claim_limit": ("FUP-05 CADENCE_ARTIFACT may not be cited as a causal "
                            "verdict; only as the DESCRIPTIVE band observation."),
            "upgrade_type": "CORRECTNESS_REPAIR",
            "invalidated_runs": [
                "evidence/corrective_mode4_v3/FUP-05/placebo_result.json "
                "(verdict field only; descriptive numbers keep values)",
            ],
        },
        {
            "finding_id": "FP-F07",
            "audit_finding": ("LOO sử dụng future origins: time-sorted leave-one-out can "
                              "train on future labels; RA-06's ladder never fit "
                              "(support 5 < 8), so no guard existed anywhere."),
            "required": "Chronological matured-label split",
            "current_disposition": "FIXED_WITH_PROOF",
            "evidence_refs": [
                "src/crypto_regime_lab/fp/chronology.py::chronological_split + "
                "naive_time_sorted_loo_train (hazard control)",
                "tests/fp_corrective/test_fp01_validity.py::"
                "test_fp01_t07_chronology_guard_refuses_future_labels",
            ],
            "affected_paths": [
                "src/crypto_regime_lab/fp/chronology.py",
            ],
            "verification": ("FP01-T07: naive LOO rows over the same fixture both fail "
                             "the guard at the held origin's decision time; a row with "
                             "no availability field refuses."),
            "planned_phase": "FP-05 fits go through fp/chronology; the registered "
                             "MIN_SUPPORT gate stays",
            "claim_limit": "No in-sample residual may be presented as generalization "
                           "uncertainty (guide 8.5).",
        },
        {
            "finding_id": "FP-F08",
            "audit_finding": ("Raw artifacts thiếu trong package: untracked run dirs and "
                              "gitignored binaries referenced but not in git."),
            "required": "Export existing outputs, không thay run khác",
            "current_disposition": "PRESENT",
            "evidence_refs": [
                "evidence/forward_persistence_fp_v1/<run_id>/artifact_inventory.json",
            ],
            "affected_paths": [],
            "verification": ("Inventory lists every missing/untracked artifact with a "
                             "planned export action; no run is re-generated to fill a "
                             "gap."),
            "planned_phase": "FP-02 (export small JSON), FP-10 (freeze package with "
                             "detached digests)",
            "claim_limit": ("A missing raw artifact caps every claim that needs it; "
                            "never zero-filled, never replaced by another run."),
        },
        {
            "finding_id": "FP-F09",
            "audit_finding": ("Gate kiểm token/field thay hành vi: a verifier reading its "
                              "own prior success record instead of the behavior."),
            "required": "Behavioral verifier",
            "current_disposition": "FIXED_WITH_PROOF",
            "evidence_refs": [
                "src/crypto_regime_lab/fp/verifier_fp01.py (hash re-check of every "
                "artifact, pytest XML re-parse with FP01-T01..T07 presence, gate "
                "re-evaluation from artifacts)",
                "tests/fp_corrective/test_fp01_verifier.py "
                "(empty/tampered/zero-tests/blocked-PASS all fail)",
            ],
            "affected_paths": [
                "src/crypto_regime_lab/fp/verifier_fp01.py",
            ],
            "verification": ("Four failure shapes each proved to fail; the PASS bundle "
                             "is independently re-verified."),
            "planned_phase": "FP-02..FP-10 verifiers inherit this behavioral shape",
            "claim_limit": ("Neither the process exit code nor this verifier's PASS is "
                            "evidence without the artifacts it inspected."),
        },
    ]
