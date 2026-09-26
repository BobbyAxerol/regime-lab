"""Coverage for sd/preflight_sd03.py (guide SD03.1) -- run against the REAL
committed SD-01/SD-02 artifacts, matching this lab's standing discipline.
"""
from __future__ import annotations

from pathlib import Path

from crypto_regime_lab.sd import preflight_sd03 as pf

LAB = Path(__file__).resolve().parents[2]


def test_verify_prior_receipts_real_sd01_sd02_both_pass():
    result = pf.verify_prior_receipts(LAB)
    assert result["pass"] is True
    assert result["sd01"]["technical_gate"] == "PASS"
    assert result["sd02"]["technical_gate"] == "PASS"


def test_verify_freeze_real_sd02_freeze_sealed():
    result = pf.verify_freeze(LAB)
    assert result["pass"] is True
    assert result["freeze"]["recipe_selection"]["selected_c"] == 2.0


def test_verify_timeline_real_final_role_has_12_origins():
    result = pf.verify_timeline(LAB)
    assert result["pass"] is True
    assert len(result["final_origins"]) == 12
    assert result["final_origins"][0] == "2024-03-23"


def test_verify_resource_budget_real_registered():
    result = pf.verify_resource_budget(LAB)
    assert result["pass"] is True
    assert result["budget"]["working_memory_gib"] == 4


def test_preflight_real_overall_ready():
    result = pf.preflight(LAB)
    assert result["overall"] == "READY"
    assert result["planned_work_manifest"] is not None
    assert result["planned_work_manifest"]["final_archive"]["n_origins"] == 12


def test_preflight_blocked_when_freeze_missing(tmp_path):
    import json
    import shutil

    fake_lab = tmp_path / "lab"
    for sub in ("evidence/sharpe_decay_sd_v1/init_archive", "evidence/sharpe_decay_sd_v1/validation_folds",
               "configs/sharpe_decay_sd_v1"):
        (fake_lab / sub).mkdir(parents=True)
    (fake_lab / "evidence/sharpe_decay_sd_v1/init_archive/gate_receipt.json").write_text(
        json.dumps({"technical_gate": "PASS"}))
    (fake_lab / "evidence/sharpe_decay_sd_v1/validation_folds/gate_receipt.json").write_text(
        json.dumps({"technical_gate": "PASS"}))
    shutil.copy(LAB / "configs" / "sharpe_decay_sd_v1" / "timeline.json",
               fake_lab / "configs" / "sharpe_decay_sd_v1" / "timeline.json")
    shutil.copy(LAB / "configs" / "sandbox_policy.json", fake_lab / "configs" / "sandbox_policy.json")
    if (LAB / ".lab_marker.json").exists():
        shutil.copy(LAB / ".lab_marker.json", fake_lab / ".lab_marker.json")
    # deliberately NO sd02_freeze.json written
    result = pf.preflight(fake_lab)
    assert result["overall"] == "BLOCKED"
    assert result["freeze"]["pass"] is False
