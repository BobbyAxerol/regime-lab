import json
import pytest
from pathlib import Path

LAB_ROOT = Path("/root/bobby/pool_alpha/lab_regime_model_quantbt")

def test_chronos_not_labeled_as_active_candidate_without_backend():
    """FIX-02 Acceptance test:
    Fail if model_grid.json or active candidate models contains Chronos without torch/chronos installed.
    """
    grid_path = LAB_ROOT / "configs/btc_regime_forecast_v1/model_grid.json"
    assert grid_path.exists(), "model_grid.json must exist"
    
    with open(grid_path, "r", encoding="utf-8") as f:
        grid = json.load(f)
        
    candidates = grid.get("candidate_models", [])
    for cand in candidates:
        model_id = cand.get("model_id", "")
        model_type = cand.get("model_type", "")
        arch = cand.get("architecture", "")
        
        is_chronos = "chronos" in model_id.lower() or "chronos" in model_type.lower() or "chronos" in arch.lower()
        if is_chronos:
            import importlib.util
            torch_spec = importlib.util.find_spec("torch")
            chronos_spec = importlib.util.find_spec("chronos")
            if torch_spec is None or chronos_spec is None:
                pytest.fail(
                    f"Model candidate '{model_id}' is labeled as Chronos ({arch}), "
                    "but torch/chronos backend is not importable. "
                    "Per FIX-02, unbacked foundation models must not be in active candidates "
                    "and must be registered as BLOCKED_CAPABILITY with metrics null."
                )

def test_blocked_capability_structure():
    """Verify that if blocked capabilities are declared, they have null metrics and valid reason."""
    grid_path = LAB_ROOT / "configs/btc_regime_forecast_v1/model_grid.json"
    with open(grid_path, "r", encoding="utf-8") as f:
        grid = json.load(f)
    blocked = grid.get("blocked_capabilities", [])
    assert len(blocked) > 0, "Blocked capability for unbacked Chronos must be declared in model_grid.json"
    for b in blocked:
        assert b.get("status") == "BLOCKED_CAPABILITY"
        assert b.get("metrics") is None
        assert len(b.get("reason", "")) > 0
