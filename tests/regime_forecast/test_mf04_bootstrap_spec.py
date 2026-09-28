from pathlib import Path
from crypto_regime_lab.regime_forecast import bootstrap

LAB_ROOT = Path("/root/bobby/pool_alpha/lab_regime_model_quantbt")

def test_bootstrap_block_size_formula():
    """FIX-04 Acceptance test 1:
    Verify that bootstrap block size function computes ceil(H/7) for primary,
    and ceil(1.5*H/7), ceil(2*H/7) for sensitivities.
    """
    assert hasattr(bootstrap, "get_bootstrap_block_spec"), "bootstrap module must have get_bootstrap_block_spec"
    
    spec_56 = bootstrap.get_bootstrap_block_spec(56)
    assert spec_56["primary"] == 8, f"Expected 8 for H56 primary, got {spec_56['primary']}"
    assert spec_56["sensitivity_1_5x"] == 12, f"Expected 12 for H56 sens 1.5x, got {spec_56['sensitivity_1_5x']}"
    assert spec_56["sensitivity_2_0x"] == 16, f"Expected 16 for H56 sens 2.0x, got {spec_56['sensitivity_2_0x']}"
    
    spec_90 = bootstrap.get_bootstrap_block_spec(90)
    assert spec_90["primary"] == 13, f"Expected 13 for H90 primary, got {spec_90['primary']}"
    assert spec_90["sensitivity_1_5x"] == 20, f"Expected 20 for H90 sens 1.5x, got {spec_90['sensitivity_1_5x']}"
    assert spec_90["sensitivity_2_0x"] == 26, f"Expected 26 for H90 sens 2.0x, got {spec_90['sensitivity_2_0x']}"


def test_overlap_summary_structure():
    """FIX-04 Acceptance test 2:
    Verify computation of origin overlap summary with calendar span, overlap pairs,
    effective independent episodes, and explicit approximation caveat.
    """
    assert hasattr(bootstrap, "compute_origin_overlap_summary"), "Must have compute_origin_overlap_summary"
    origins = [f"2025-06-{i:02d}" for i in range(1, 49)] # 48 weekly origins
    summary = bootstrap.compute_origin_overlap_summary(origins, horizons=[56, 90])
    
    assert "H56" in summary
    assert "H90" in summary
    assert summary["H90"]["primary_block_size"] == 13
    assert summary["H90"]["estimated_effective_independent_episodes"] < 5
    assert "approximation_caveat" in summary["H90"]
