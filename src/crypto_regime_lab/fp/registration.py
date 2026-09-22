"""FP registration (guide §13 FP01.3, §26.1): the frozen primary, secondary,
arms, and study-level contracts every later phase inherits.

The migration rows are a deliberate methodology revision under the lab's
`protocol_migration` discipline, never a certificate that old gates passed and
never an edit of an old run's acceptance.
"""
from __future__ import annotations

from . import GUIDE_VERSION, STUDY_ID

REQUIRED_GATES = ("FP01-G-VALIDITY", "FP01-G-IDENTITY", "FP01-G-MIGRATION", "FP01-G-BUDGET")


def registration(*, registered_at_utc: str, registered_by_phase: str = "FP-01") -> dict:
    """The FP registration artifact content (configs + run-dir copy)."""
    return {
        "schema": "regime_lab.fp_registration.v1",
        "study_id": STUDY_ID,
        "guide_version": GUIDE_VERSION,
        "guide_source": "REGIME_LAB_FORWARD_PERSISTENT_PLATEAU_GUIDE_VI.md",
        "registered_at_utc": registered_at_utc,
        "registered_by_phase": registered_by_phase,
        "primary": {
            "contrast": "C_FP_CONTEXT minus B_FP_PERSISTENCE on a common fixed calendar",
            "decision_rule": ("retention within scope only when valid, decays better, "
                              "and meets the OOS utility/risk safeguard (guide 20.5)"),
            "fixed_timing": True,
        },
        "secondary": {
            "timing": ("conditional FP-09 only: SELECTOR_FIXED_CAL / SELECTOR_CAL_MATCHED "
                       "/ SELECTOR_REGIME_TIMING under the same frozen selector; needs "
                       "a mechanism hypothesis + owner approval, never automatic"),
        },
        "arms": {
            "A_STOCK_CAL": "stock comparator: installed Mode 4 selection, calendar",
            "B_FP_PERSISTENCE": "forward-persistence selector, NO signed regime/context",
            "C_FP_CONTEXT": "B pipeline + one frozen context family, same pool/target/base",
        },
        "trial_episode_rule": ("a trial is one evaluated candidate; an episode is a "
                               "matured train->deploy->forward-outcome run; trials do "
                               "not substitute episodes"),
        "decay_primary_rule": ("decay is the primary selector objective but never "
                               "optimized alone: always beside the OOS utility/risk "
                               "safeguard"),
        "historical_invariance": ("RA/RF/FUP registrations, runs, verdicts are "
                                  "append-only; FP cites them via invalidated_by / "
                                  "superseded_by / recomputed_from / verified_reuse_of"),
        "phases": ["FP-01", "FP-02", "FP-03", "FP-04", "FP-05", "FP-06",
                   "FP-07", "FP-08", "FP-09", "FP-10"],
        "owner_approval": ("each phase starts only on the owner's explicit approval "
                           "recorded in evidence/regime_time_edge_ra_v1/"
                           "owner_decisions.jsonl (R-18)"),
    }


def migration_rows() -> list[dict]:
    """Old rule -> new rule -> reason -> affected claims/tests."""
    return [
        {"old_rule": "Regime edge = timing: M4_REGIME schedule vs calendar WFO",
         "new_rule": "Primary = C_FP_CONTEXT vs B_FP_PERSISTENCE on a common fixed "
                     "calendar; timing moves to conditional FP-09",
         "reason": ("two independent falsifications (RA-07 90d placebo; FUP-05 12m "
                    "placebo) reproduced the apparent timing advantage with "
                    "market-free tapes; the open question is conditional SELECTION"),
         "affected_claims_or_tests": "FUP-05 verdict (invalidated for causal citation); "
                                     "FP-07/FP-09 registration"},
        {"old_rule": "Admission funnel recorded descriptively after the account ran",
         "new_rule": "admission_policy before the deployment account is built; only "
                     "admitted params are consumed (FP-F02 repair)",
         "reason": "KEEP_INCUMBENT never stopped the account from switching",
         "affected_claims_or_tests": "FP01-T02; FP-07 must pass a policy"},
        {"old_rule": "D1/OOS first return dropped (in-window base)",
         "new_rule": "fp/decay_bounds.windowed_returns: preceding-mark base (FP-F04)",
         "reason": "IS side kept the first return via prior equity; OOS did not",
         "affected_claims_or_tests": "FP01-T03; FP-07 D1 recomputed_from"},
        {"old_rule": "Verdict from a control-vs-band comparison (FUP-05)",
         "new_rule": "fp/claim_logic.timing_verdict: band-alone is "
                     "NOT_EVALUABLE_DIRECT_CONTRAST_MISSING (FP-F06)",
         "reason": "guide 21 forbids CADENCE verdicts without the direct paired contrast",
         "affected_claims_or_tests": "FUP-05 verdict (invalidated); FP-09 verdicts"},
        {"old_rule": "LOO/model-fit chronology by convention only",
         "new_rule": "fp/chronology.chronological_split before any FP-05 fit (FP-F07)",
         "reason": "time-sorted LOO can train on future labels; no guard existed",
         "affected_claims_or_tests": "FP01-T07; FP-05 model protocol"},
    ]
