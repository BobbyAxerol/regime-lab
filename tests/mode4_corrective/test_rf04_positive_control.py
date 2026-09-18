"""RF-04 acceptance: G11 positive control is a real treatment, not a rename."""

from __future__ import annotations

import json


def test_g11_positive_control_changes_parameters_and_reaches_execution(lab_root):
    payload = json.loads(
        (lab_root / "evidence" / "corrective_mode4_v3" / "RF-04" / "positive_control.json")
        .read_text(encoding="utf-8"))
    assert payload["params_changed_by_treatment"] is True
    assert payload["treatment_reached_execution"] is True
    assert payload["regime"]["status"] == "EVALUATED"
    assert payload["calendar"]["status"] == "EVALUATED"
    assert payload["regime"]["engine_fills"] != payload["calendar"]["engine_fills"]
    assert "policy reads emissions" in payload["ground_truth_use"]


def test_rf04_protocol_is_registered_before_the_discovery_runs(lab_root):
    payload = json.loads(
        (lab_root / "evidence" / "corrective_mode4_v3" / "RF-04" / "discovery_protocol.json")
        .read_text(encoding="utf-8"))
    assert payload["status"] == "REGISTERED_BEFORE_DISCOVERY_RUNS"
    assert payload["primary_arms"] == ["M4_CAL", "M4_REGIME"]
    assert payload["cells_planned"] == 20
    assert "G10 model repairs (A14)" in payload["gates"]["must_close_before_results"]
