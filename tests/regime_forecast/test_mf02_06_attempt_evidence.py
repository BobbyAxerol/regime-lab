import pytest
from pathlib import Path

LAB_ROOT = Path("/root/bobby/pool_alpha/lab_regime_model_quantbt")
RUNS_DIR = LAB_ROOT / "evidence/btc_regime_forecast_v1/runs"

def test_all_run_directories_have_request_attempt_and_report_or_postmortem():
    """FIX-06 Acceptance test:
    Every run directory under evidence/btc_regime_forecast_v1/runs/ must contain:
    1. request.json
    2. attempts.jsonl
    3. Either report.md or postmortem.md
    No empty directories are permitted per Section 23.1.
    """
    assert RUNS_DIR.is_dir(), f"Runs directory {RUNS_DIR} must exist"
    run_dirs = [d for d in sorted(RUNS_DIR.iterdir()) if d.is_dir()]
    assert len(run_dirs) > 0, "Must have at least one run directory"
    
    violations = []
    for d in run_dirs:
        has_req = (d / "request.json").is_file()
        has_att = (d / "attempts.jsonl").is_file()
        has_rep = (d / "report.md").is_file() or (d / "postmortem.md").is_file()
        
        missing = []
        if not has_req:
            missing.append("request.json")
        if not has_att:
            missing.append("attempts.jsonl")
        if not has_rep:
            missing.append("report.md or postmortem.md")
            
        if missing:
            violations.append(f"{d.name} missing: {', '.join(missing)}")
            
    if violations:
        pytest.fail(f"Found {len(violations)} non-compliant run directories:\n" + "\n".join(violations))
