"""fp.fp08_decision -- guide FP08.5's registered disposition table, one
test per row, plus a check that every returned label is in the vocabulary."""
from __future__ import annotations

import pytest

from crypto_regime_lab.fp import fp08_decision as dec


def test_registered_vocabulary_has_exactly_six_labels():
    assert len(dec.REGISTERED_VOCABULARY) == 6


def test_technical_invalid_beats_everything_else():
    out = dec.classify_disposition(claim="x", claim_type="economic_outperformance",
                                   technical_valid=False, degenerate=True,
                                   contrast={"status": "ESTIMATED", "ci95_basic": [1.0, 2.0]},
                                   delta_threshold=0.5)
    assert out["disposition"] == dec.NOT_EVALUABLE


def test_degenerate_contrast_is_context_not_exercised_even_with_a_clearing_ci():
    out = dec.classify_disposition(claim="C-B", claim_type="economic_outperformance",
                                   technical_valid=True, degenerate=True,
                                   contrast={"status": "ESTIMATED", "estimate": 0.0,
                                            "ci95_basic": [0.0, 0.0]},
                                   delta_threshold=6.4e-05)
    assert out["disposition"] == dec.CONTEXT_NOT_EXERCISED


def test_non_estimated_contrast_is_inconclusive():
    out = dec.classify_disposition(claim="x", claim_type="economic_outperformance",
                                   technical_valid=True,
                                   contrast={"status": "NOT_EVALUABLE"}, delta_threshold=6.4e-05)
    assert out["disposition"] == dec.INCONCLUSIVE


def test_no_registered_threshold_is_inconclusive_never_invents_one():
    out = dec.classify_disposition(claim="x", claim_type="decay_reduction", technical_valid=True,
                                   contrast={"status": "ESTIMATED", "ci95_basic": [0.1, 0.2]},
                                   delta_threshold=None)
    assert out["disposition"] == dec.INCONCLUSIVE
    assert "descriptive" in out["reason"]


def test_economic_outperformance_when_ci_lower_clears_the_threshold():
    out = dec.classify_disposition(claim="B-A", claim_type="economic_outperformance",
                                   technical_valid=True,
                                   contrast={"status": "ESTIMATED", "ci95_basic": [0.0001, 0.0003]},
                                   delta_threshold=6.4e-05)
    assert out["disposition"] == dec.ECONOMIC_OUTPERFORMANCE


def test_retention_contribution_needs_both_ci_and_the_risk_safeguard():
    contrast = {"status": "ESTIMATED", "ci95_basic": [0.0001, 0.0003]}
    without_safeguard = dec.classify_disposition(claim="C-B decay", claim_type="decay_reduction",
                                                 technical_valid=True, contrast=contrast,
                                                 delta_threshold=6.4e-05, risk_safeguard_met=False)
    assert without_safeguard["disposition"] == dec.INCONCLUSIVE
    with_safeguard = dec.classify_disposition(claim="C-B decay", claim_type="decay_reduction",
                                              technical_valid=True, contrast=contrast,
                                              delta_threshold=6.4e-05, risk_safeguard_met=True)
    assert with_safeguard["disposition"] == dec.RETENTION_CONTRIBUTION


def test_no_meaningful_improvement_when_ci_upper_excludes_the_threshold():
    out = dec.classify_disposition(claim="x", claim_type="economic_outperformance",
                                   technical_valid=True,
                                   contrast={"status": "ESTIMATED", "ci95_basic": [-0.0001, 0.00001]},
                                   delta_threshold=6.4e-05)
    assert out["disposition"] == dec.NO_MEANINGFUL_IMPROVEMENT


def test_inconclusive_when_ci_straddles_the_threshold():
    out = dec.classify_disposition(claim="x", claim_type="economic_outperformance",
                                   technical_valid=True,
                                   contrast={"status": "ESTIMATED", "ci95_basic": [-0.0001, 0.0003]},
                                   delta_threshold=6.4e-05)
    assert out["disposition"] == dec.INCONCLUSIVE


def test_unknown_claim_type_raises():
    with pytest.raises(ValueError):
        dec.classify_disposition(claim="x", claim_type="bogus", technical_valid=True)


def test_real_cell1_secondary_contrast_classifies_as_no_meaningful_improvement():
    """Sanity check against FP-07's own real B-A contrast: estimate
    -0.000189/day, ci95 [-0.0003208, -0.0000387] -- entirely below the
    registered 6.4e-05 threshold, so 'no meaningful improvement', not
    inconclusive and not a fabricated positive."""
    contrast = {"status": "ESTIMATED", "estimate": -0.0001889748502425521,
               "ci95_basic": [-0.0003208041703683213, -3.872726972319523e-05]}
    out = dec.classify_disposition(claim="B-A cell1", claim_type="economic_outperformance",
                                   technical_valid=True, contrast=contrast, delta_threshold=6.4e-05)
    assert out["disposition"] == dec.NO_MEANINGFUL_IMPROVEMENT
