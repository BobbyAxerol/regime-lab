import pytest
import json
from pathlib import Path

LAB_ROOT = Path("/root/bobby/pool_alpha/lab_regime_model_quantbt")

def test_bridge_rationale_cites_correct_sections_and_no_all_primary_heads():
    """FIX-05 Acceptance test:
    Verify WFO_BRIDGE_DECISION.json:
    - Verdict must remain CLOSED.
    - Must NOT contain the false rule 'all primary heads'.
    - Must explicitly cite §18.1, §9.4, §18.3, §18.5.
    - Must list the unmet WFO conditions (128 trials/cutoff, 12 paired folds, timeline evidence, financial domain gates).
    """
    bridge_path = LAB_ROOT / "configs/btc_regime_forecast_v1/WFO_BRIDGE_DECISION.json"
    assert bridge_path.is_file(), "WFO_BRIDGE_DECISION.json must exist"
    
    with open(bridge_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    assert data.get("wfo_bridge_decision") == "CLOSED"
    
    rationale = data.get("rationale", "")
    citations = data.get("guide_citations", [])
    unmet_conditions = data.get("unmet_wfo_conditions", [])
    
    # 1. Must not claim 'all primary heads'
    if "all primary heads" in rationale.lower():
        pytest.fail("Rationale contains incorrect 'all primary heads' rule; Guide §18 does not require all heads to pass.")
        
    # 2. Must cite §18.1, §9.4, §18.3, §18.5
    for section in ["18.1", "9.4", "18.3", "18.5"]:
        assert any(section in c for c in citations) or section in rationale, f"Missing citation for Section {section}"
        
    # 3. Must list unmet conditions
    assert len(unmet_conditions) >= 4, "Must list at least 4 unmet conditions per §18.3 and §18.5"
