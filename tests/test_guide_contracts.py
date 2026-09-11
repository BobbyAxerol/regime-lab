"""Contracts the guide states OUTSIDE the phase task lists.

Guide 13.1 (research-record identities), 13.5 (the CLI) and 10.5 (compute
budgets) are requirements no L0N.M task owns, which is exactly why all three
drifted: the phase audits each passed while the cross-phase contract did not.
These tests hold the contracts themselves.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pandas as pd

import pytest

from crypto_regime_lab.cli import STAGE_DELIVERY, build_parser
from crypto_regime_lab.evidence.identities import (
    DERIVABLE,
    TAXONOMY,
    execution_id,
    observation_id,
    probe_design_id,
)

GUIDE_CLI_STAGES = {
    "preflight", "certify-alphas", "snapshot-data", "verify-causality",
    "run", "freeze", "report", "verify-source-integrity",
}


# --- guide 13.5: the CLI contract ----------------------------------------


def test_the_cli_exposes_every_stage_the_guide_names():
    parser = build_parser()
    actions = [a for a in parser._actions if a.choices and "preflight" in (a.choices or {})]
    assert actions, "the CLI has no stage subparsers"
    assert set(actions[0].choices) == GUIDE_CLI_STAGES


def test_stage_availability_is_read_from_the_phase_audit_not_hard_coded(lab_root):
    """A stage's availability must track reality.

    The first version of cli.py froze an IMPLEMENTED set at LAB-01. When LAB-02
    and LAB-03 landed, `certify-alphas` and `snapshot-data` went on answering
    "the phase has not landed" about phases that had. A refusal that silently
    goes stale reads like a checked fact and is worse than no refusal.
    """
    for stage, delivery in STAGE_DELIVERY.items():
        audit = delivery["audit"]
        if audit is None:
            continue
        landed = (lab_root / "configs" / audit).is_file()
        if delivery["runner"] is not None:
            assert landed, (
                f"{stage} has a runner wired but {audit} does not exist: the CLI would run a "
                "stage whose phase never landed")
            assert (lab_root / delivery["runner"]).is_file(), (
                f"{stage} points at a missing runner {delivery['runner']}")


@pytest.mark.parametrize("stage", ["report"])
def test_a_stage_whose_phase_has_not_landed_refuses_and_says_so(lab_root, stage):
    """`run` and `freeze` left this list when LAB-08 landed and wired their runners.

    Parametrising over stages that have since shipped is the expiring-assertion
    shape again; `report` is owned by LAB-10 and is the one still genuinely
    unlanded.
    """
    argv = [sys.executable, "-m", "crypto_regime_lab.cli", stage]
    if stage == "run":
        argv += ["--stage", "discovery"]
    proc = subprocess.run(argv, cwd=str(lab_root), capture_output=True, text=True,
                          env={"PYTHONPATH": str(lab_root / "src"),
                               "PYTHONDONTWRITEBYTECODE": "1", "PATH": "/usr/bin:/bin"})
    assert proc.returncode == 2, "an unavailable stage must fail, never exit 0"
    payload = json.loads(proc.stderr)
    assert payload["status"] == "PHASE_NOT_LANDED"
    assert payload["phase_has_landed"] is False


def test_snapshot_data_refuses_to_repin_a_pinned_snapshot(lab_root):
    """Re-reading the source while the collector appends re-registers the read-lock.

    The snapshot is the study's read-lock. Silently taking a fresh one changes
    what every past result claims to have read, so the destructive path needs a
    flag rather than a default.
    """
    proc = subprocess.run(
        [sys.executable, str(lab_root / "scripts" / "snapshot_data.py")],
        cwd=str(lab_root), capture_output=True, text=True,
        env={"PYTHONPATH": str(lab_root / "src"), "PYTHONDONTWRITEBYTECODE": "1",
             "PATH": "/usr/bin:/bin"})
    assert proc.returncode == 0
    assert "REFUSED to re-pin" in proc.stdout
    assert "--repin" in proc.stdout
    manifest = json.loads((lab_root / "snapshots" / "server_core_v1" / "manifest.json").read_text())
    assert manifest["ingest_finished_utc"].startswith("2026-09-09"), (
        "the pinned manifest was rewritten by a read-only invocation")


def test_verify_causality_covers_every_layer_the_exit_gate_names(lab_root):
    """LAB-03's exit: the mutation test passes through loader, resampler and scaler.

    LAB-05 adds the model and the streaming filter. Each was tested on its own;
    nothing ran them as one gate, so nothing could be pointed at.
    """
    path = lab_root / "configs" / "causality_verification.json"
    if not path.is_file():
        pytest.skip("run scripts/verify_causality.py")
    report = json.loads(path.read_text())
    assert set(report["verdicts"]) >= {"resampler", "scaler", "model", "online_filter"}
    assert all(report["verdicts"].values()), report["verdicts"]
    assert report["leaky_control_is_detected"] is True, (
        "a causality suite that never fails proves nothing; the leaky control must be caught")
    assert report["status"] == "CAUSAL"
    for layer in report["layers"]:
        assert layer.get("suffix_actually_changed", True), (
            f"{layer['layer']}: the mutation did not change the suffix, so 'the past did not "
            "move' is trivially true")


# --- guide 13.1: research-record identities -------------------------------


def test_the_taxonomy_lists_all_twelve_identities():
    assert len(TAXONOMY) == 12
    assert {"study_id", "experiment_id", "trial_id", "candidate_id", "execution_id",
            "probe_design_id", "model_id", "observation_id", "response_id",
            "selection_id", "activation_id", "attempt_id"} == set(TAXONOMY)


def test_each_identity_is_deterministic_and_distinct():
    a = probe_design_id(alpha_id="A-SC", symbol="BTCUSDT", cutoff="2021-01-01", seed=1,
                        anchors=2, probes_per_anchor=8, radius=0.12)
    assert a == probe_design_id(alpha_id="A-SC", symbol="BTCUSDT", cutoff="2021-01-01", seed=1,
                                anchors=2, probes_per_anchor=8, radius=0.12)
    b = probe_design_id(alpha_id="A-SC", symbol="BTCUSDT", cutoff="2021-01-01", seed=2,
                        anchors=2, probes_per_anchor=8, radius=0.12)
    assert a != b, "the seed is part of a frozen design"


def test_a_different_fee_is_a_different_execution():
    """Guide 13.1 puts economics inside execution_id, and it has to stay there.

    The same candidate over the same bars at a different fee is a different
    measurement. One shared ID is how a cost-stress run gets compared against a
    headline run as if they were the same thing.
    """
    common = dict(candidate_id="c1", symbol="BTCUSDT", interval="15m",
                  start="2021-01-01", end="2021-06-30", initial_state="flat", seed=7)
    cheap = execution_id(economics={"taker_fee_rate": 0.0004}, **common)
    dear = execution_id(economics={"taker_fee_rate": 0.0008}, **common)
    assert cheap != dear


def test_an_observation_is_named_by_both_of_its_timestamps():
    common = dict(model_id="jm_k3_2021-01-01", state_namespace="jm@2021-01-01")
    early = observation_id(observed_at="2021-02-01T00:00", available_at="2021-02-01T04:00", **common)
    late = observation_id(observed_at="2021-02-01T00:00", available_at="2021-02-01T08:00", **common)
    assert early != late, (
        "available_at is what a policy may act on; dropping it would make a backdated re-read "
        "indistinguishable from a legitimate one")


def test_identity_ids_do_not_depend_on_dict_ordering():
    common = dict(candidate_id="c1", symbol="BTCUSDT", interval="15m",
                  start="2021-01-01", end="2021-06-30", initial_state="flat", seed=7)
    one = execution_id(economics={"fee": 0.0004, "slippage_bps": 1.0}, **common)
    two = execution_id(economics={"slippage_bps": 1.0, "fee": 0.0004}, **common)
    assert one == two, "an identity must describe what a record says, not how it was built"


def test_the_identity_audit_does_not_pass_on_its_own_output(lab_root):
    """The audit reported 12/12 on its first run, purely by grepping the file it had written."""
    path = lab_root / "configs" / "id_taxonomy.json"
    if not path.is_file():
        pytest.skip("run scripts/audit_identities.py")
    document = json.loads(path.read_text())
    assert document["present_count"] < document["total"], (
        "every identity reported PRESENT: the scan is almost certainly matching its own artifact")
    for name in DERIVABLE:
        assert document["identities"][name]["status"] == "DERIVABLE"
        assert name in document["derivations_demonstrated"], (
            f"{name} is called derivable but no derivation was demonstrated on a real record")
    # Derive the expectation from which phases have LANDED. Hardcoding the owed
    # set makes the test expire: it said {experiment_id, activation_id} until
    # LAB-07 shipped and minted activation_id.
    landed = {f"LAB-0{n}" for n in range(1, 10)
              if (lab_root / "configs" / f"lab0{n}_task_audit.json").is_file()}
    for name, record in document["identities"].items():
        if record["status"] == "OWED":
            assert record["owner"] not in landed, (
                f"{name} is owed by {record['owner']}, which has already landed")


# --- guide 10.5: compute budgets ------------------------------------------


@pytest.fixture(scope="module")
def compute_budget(lab_root):
    path = lab_root / "configs" / "compute_budget_registration.json"
    if not path.is_file():
        pytest.skip("run scripts/register_compute_budget.py")
    return json.loads(path.read_text())


def test_both_compute_reports_are_registered(compute_budget):
    assert set(compute_budget["reports"]) == {"MATCHED_TOTAL_COMPUTE", "OPERATIONAL_POLICY"}
    for report in compute_budget["reports"].values():
        assert report["counted_units"], "a budget report with no counted unit cannot be matched"
        assert report["reported_per"]


def test_search_accounting_is_not_limited_to_optimizer_trials(compute_budget):
    """Guide 10.5: 'Không chỉ log Optuna alpha trials.'

    A method whose tuning happens outside the optimizer is not cheaper; it is
    accounted for somewhere else. If that somewhere is nowhere, the comparison
    is wrong in the new method's favour.
    """
    kinds = set(compute_budget["what_counts_as_search"])
    assert {"state-count (K) choices", "jump penalties",
            "response bandwidth and shrinkage", "switching thresholds"} <= kinds


def test_the_ledger_opens_with_what_the_completed_phases_actually_spent(compute_budget):
    entries = compute_budget["ledger_opened_with"]["entries"]
    phases = {e["phase"] for e in entries}
    assert {"LAB-04", "LAB-05", "LAB-06"} <= phases
    lab04 = next(e for e in entries if e["phase"] == "LAB-04")
    assert lab04["unique_executions"] and lab04["unique_executions"] > 0
    assert lab04["candidate_episode_visits"] > lab04["unique_executions"]
    lab05 = next(e for e in entries if e["kind"] == "state_count_choice")
    assert lab05["candidates_considered"], "the K search must be counted, not assumed free"


def test_the_budget_was_registered_before_the_arms_that_could_game_it(compute_budget, lab_root):
    """The budget must PRE-DATE LAB-07, and stay provably so after LAB-07 lands.

    The first version of this test asserted `lab07_task_audit.json` did not
    exist, which was true when it was written and false the moment LAB-07
    shipped. An assertion that expires quietly is the same defect as the CLI's
    frozen IMPLEMENTED set, so the property is now checked against timestamps
    instead of against a phase not having happened yet.
    """
    assert compute_budget["status"] == "REGISTERED_BEFORE_LAB07"
    assert "never reduced" in compute_budget["baseline_protection_rule"]

    audit_path = lab_root / "configs" / "lab07_task_audit.json"
    if not audit_path.is_file():
        return                                  # LAB-07 has not landed; nothing to compare
    registered = pd.Timestamp(compute_budget["registered_at_utc"])
    landed = pd.Timestamp(audit_path.stat().st_mtime, unit="s", tz="UTC")
    assert registered < landed, (
        f"the compute budget was registered {registered}, after LAB-07 landed {landed}: it "
        "could have been chosen knowing what the refit scheduler costs")


def test_the_ledger_carries_each_landed_phase_and_the_registration_stays_immutable(
        compute_budget, lab_root):
    """A registered contract that a phase then ignores is worse than none.

    LAB-07 owed the ledger its measured per-refit cost and its activation
    delays. Re-registering to add them would have re-stamped
    ``registered_at_utc``, destroying the only evidence that the contract
    pre-dated the arm whose cost it governs — so the registration is preserved
    and the ledger appends.
    """
    entries = compute_budget["ledger_opened_with"]["entries"]
    phases = {e["phase"] for e in entries}
    for phase in ("LAB-04", "LAB-05", "LAB-06"):
        assert phase in phases

    if (lab_root / "configs" / "lab07_task_audit.json").is_file():
        assert "LAB-07" in phases, (
            "LAB-07 has landed but owes the ledger the operational cost it registered for")
        operational = next(e for e in entries
                           if e["phase"] == "LAB-07" and e["kind"] == "operational_latency")
        assert operational["latency_source"] == "measured_benchmark"
        assert operational["min_refit_delay_seconds"] > 0
        assert operational["network_calls"] == 0
        assert operational["activation_delay_bars"], (
            "activation delay is the half of the operational cost no latency model captures")

    assert "registration_is_immutable" in compute_budget
    assert "ledger_last_appended_utc" in compute_budget


def test_guide_10_1_captures_all_six_fields_from_the_installed_selector(lab_root):
    """Guide 10.1 names six things to capture, so "identical to the current WFO" is checkable.

    Three of them — search_scope, selected_params_freeze, data_used_for_selection —
    existed only under the engine's own field names, where a reader looking for
    the guide's name would not find them. Found while re-reading §10 against the
    artifacts rather than against the phase audits.
    """
    path = lab_root / "configs" / "lab04_installed_wfo_trace.json"
    if not path.is_file():
        pytest.skip("run scripts/trace_installed_selector.py")
    capture = json.loads(path.read_text()).get("guide_10_1_capture")
    assert capture, "the trace carries no guide 10.1 capture block"
    for field in ("route", "mode", "search_scope", "candidate_freeze",
                  "selected_params_freeze", "data_used_for_selection"):
        entry = capture[field]
        assert entry["value"] is not None, f"{field} is captured as null"
        assert entry["from"], f"{field} does not say where it came from"
    assert capture["all_six_present"] is True

    # the capture has to reach the label it justifies: a route that declares OOS
    # selection is what makes arm A `A_legacy_selection_adjusted`
    declared = capture["data_used_for_selection"]["value"]["modes_declaring_oos_selection"]
    discovery = lab_root / "configs" / "lab08_discovery.json"
    if declared and discovery.is_file():
        label = json.loads(discovery.read_text())["legacy_arm_label"]
        assert "legacy" in json.dumps(label).lower(), (
            "a route declaring OOS selection must not be reported as an untouched baseline")


def test_the_declared_execution_resolution_is_compared_against_the_actual_one(lab_root):
    """Guide 4.3 — the protocol declares 1-minute execution; the account uses the decision bar.

    Found by asking which numbered guide subsection nothing in the lab
    references. §4.3 was one of five, and it is the one with a measurable
    consequence: a stop and a take-profit inside the same 15-minute bar are
    resolved by the engine's ordering rule rather than by the minute path.

    The test does not demand that they MATCH — building the 1-minute cohort is an
    implementation and is proposed, not improvised (OP-19). It demands that the
    comparison exists, is measured from the source rather than asserted, and that
    the exposure is quantified per alpha.
    """
    path = lab_root / "configs" / "protective_order_fidelity.json"
    if not path.is_file():
        pytest.skip("run scripts/verify_execution_resolution.py")
    document = json.loads(path.read_text())

    assert document["actual"]["source_check_passes"] is True, (
        "the finding is derived from a source string that no longer matches; re-check whether "
        "the account still builds engine_frame from the decision-bar frame")
    assert set(document["declared"]["execution_bars"].values()) == {"1m"}
    assert document["declared_matches_actual"] is False

    exposure = document["exposure"]
    assert exposure["alphas_measured"] >= 2
    for alpha_id, record in exposure["per_alpha"].items():
        if record["status"] != "MEASURED":
            continue
        assert record["fills"] > 0, f"{alpha_id} traded nothing, so its exposure is unmeasured"
        assert record["exposed_to_the_resolution"] == (record["protective_fills"] > 0)
    # an alpha that rests no protection cannot be affected, and one is
    assert exposure["alphas_not_exposed"], (
        "no alpha was measured as unexposed, which would make the probe indistinguishable from "
        "one that never looked")

    assert document["two_cohort_requirement"]["status"] == "NOT_BUILT"
    assert document["two_cohort_requirement"]["why_not_built"]
    assert "cancels" in document["direction"], (
        "the direction has to say whether a CONTRAST is at risk, not only a level")


def test_every_numbered_guide_subsection_is_claimed_by_something(lab_root):
    """The blind spot the phase audits cannot see.

    A phase audit asks *did every L0N.M task get done*. It cannot ask whether a
    guide requirement belongs to no task at all — and five findings have come out
    of that gap: the compute-budget contract (§10.5), the CLI stage contract
    (§13.5), the identity taxonomy (§13.1), the six captures §10.1 asks for, and
    the protective-order resolution (§4.3).
    """
    path = lab_root / "configs" / "guide_section_coverage.json"
    if not path.is_file():
        pytest.skip("run scripts/audit_guide_section_coverage.py")
    coverage = json.loads(path.read_text())
    assert coverage["sections_total"] > 40
    assert coverage["unclaimed"] == [], (
        "these guide subsections are referenced by nothing in the lab: "
        f"{coverage['unclaimed']}. Either claim them or list them in PROSE_ONLY by name")

    # a prose-only decision has to be recorded with a reason, not implied
    for section in coverage["prose_only"]:
        row = next(r for r in coverage["sections"] if r["section"] == section)
        assert row["prose_reason"], f"§{section} is called prose-only with no reason"


def test_all_twelve_approved_conditions_resolve_to_an_enforcing_artifact(lab_root):
    """Guide 0.1 is the user's own approved list, and it is nobody's phase task."""
    path = lab_root / "configs" / "guide_section_coverage.json"
    if not path.is_file():
        pytest.skip("run scripts/audit_guide_section_coverage.py")
    conditions = json.loads(path.read_text())["approved_conditions"]
    assert conditions["total"] == 12
    assert conditions["broken"] == [], (
        f"approved conditions with a dead pointer: {conditions['broken']}")
    assert conditions["enforced"] == 12
    for entry in conditions["conditions"]:
        assert entry["condition"], f"{entry['id']} has no text"
        assert entry["pointer"], f"{entry['id']} has no pointer"


def test_a_budget_revision_is_appended_and_never_restamped(lab_root):
    """Guide 10.5 — `registered_at_utc` is the evidence the contract pre-dated the arm.

    A revision that re-stamped it would destroy exactly that. So a change to the
    budget appends, with its reason and with what it does and does not affect.
    """
    path = lab_root / "configs" / "compute_budget_registration.json"
    if not path.is_file():
        pytest.skip("run scripts/register_compute_budget.py")
    document = json.loads(path.read_text())
    revisions = document.get("os_resource_budget_revisions") or []
    if not revisions:
        pytest.skip("no budget revision has been recorded")

    assert document["registered_at_utc"] < revisions[0]["revised_at_utc"], (
        "the registration stamp is not older than its own revision, so it was re-stamped")
    for revision in revisions:
        assert revision["from"] != revision["to"], "a revision that changes nothing"
        assert revision["what_it_changes"] and revision["what_it_does_not_change"]
        assert revision["what_it_costs"], "a revision with no stated cost"
        assert revision["measured_reason"], "a revision with no measurement behind it"
        # The guard here used to be `cpu_limit must not change`. That was a PROXY,
        # and the wrong one: it would block a recorded, justified revision while
        # permitting an unrecorded change that actually breaks the rule. What
        # guide L08.6 forbids is raising CPU *so that one arm finishes before
        # another*, and what 10.5 protects is the baseline's own conditions. The
        # invariant is therefore about ARMS, not about a number.
        assert revision.get("per_arm_compute_is_unchanged") is True, (
            "a budget revision must state that no arm receives more compute than another; "
            "guide L08.6 forbids raising CPU to let one policy finish ahead of the baseline")
        assert revision.get("how_arms_stay_equal"), (
            "and must say HOW they stay equal, not merely that they do")
        if revision["to"]["cpu_limit"] != revision["from"]["cpu_limit"]:
            assert revision.get("cpu_limit_change_justification"), (
                "a change to the CPU limit needs its own justification on the record")
    assert document["os_resource_budget"] == revisions[-1]["to"], (
        "the live budget does not match the latest revision")
