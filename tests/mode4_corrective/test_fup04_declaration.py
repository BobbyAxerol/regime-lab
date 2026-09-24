"""FUP-04 acceptance — the declaration this repair rests on, guarded.

FUP-04 is the registered follow-up that made the full-length native-event
deployment account fit the memory budget. Its declaration is consumed by the
RF-05 freeze guard, so the declaration must itself be checkable:

* it exists, is registered, and its ``registration_ref`` resolves to FUP-04 in
  the follow-up registration file (a declaration that cannot point at its own
  registration is not evidence of registration);
* the declared ceilings are consistent with what is actually declared, so a
  ceiling can never be set below the repairs a manifest needs;
* the opt-in contract holds as a property of the CODE, not of prose: every
  entry point defaults to the engine default, so no registered phase can start
  silently running on a reduced output profile;
* the recorded measurements still say what the declaration claims they say
  (artifact hashes recomputed, parity invariants re-asserted).
"""

from __future__ import annotations

import inspect
import json

from crypto_regime_lab.experiments import dynamic_fold_provider as DFP
from crypto_regime_lab.integration import event_account as EA
from crypto_regime_lab.ra import ra05_discovery as RA05
from crypto_regime_lab.safety.paths import sha256_file

FUP04 = ("evidence", "corrective_mode4_v3", "FUP-04")
DECLARATION = "report_level_memory_repair.json"
STUDY_ID = "FUP-04"


def _declaration(lab_root) -> dict:
    return json.loads(lab_root.joinpath(*FUP04).joinpath(DECLARATION).read_text(encoding="utf-8"))


def test_fup04_declaration_is_registered_and_self_locating(lab_root):
    declaration = _declaration(lab_root)
    assert declaration["phase"] == STUDY_ID
    assert declaration["rf05_results_recomputed"] is False, (
        "this repair may not recompute or restate a frozen RF-05 number")
    path_part, _, pointer = declaration["registration_ref"].partition("#")
    assert pointer.startswith("/studies/"), declaration["registration_ref"]
    registration = json.loads(lab_root.joinpath(path_part).read_text(encoding="utf-8"))
    registered = registration["studies"][int(pointer.split("/")[-1])]["id"]
    assert registered == STUDY_ID, (
        f"registration_ref points at {registered!r}, not {STUDY_ID!r}")
    assert declaration["measurements"], "a declaration without measurements is not evidence"
    assert declaration["protocol_migration"], (
        "the guard rules this repair changes must be recorded old -> new -> reason -> test")
    for row in declaration["protocol_migration"]:
        assert row["required_test"].strip() and row["reason"].strip(), row


def _rf05_prior_hashes(lab_root, manifest_name: str) -> dict:
    """The RF-05 manifest's OWN prior-hash mapping, keyed by path -- the same
    inputs test_rf05_claims.py's own two guards build, reused here (not
    re-derived from a single declared row) so a chain lookup for one path
    does not spuriously reject an unrelated path's perfectly valid row."""
    from test_rf05_claims import RF05, _load

    if manifest_name == "freeze_manifest.json":
        manifest = _load(lab_root, RF05, manifest_name)
        return {row["path"]: row["sha256"]
                for rows in manifest["components"].values() for row in rows}
    if manifest_name == "reproducibility_manifest.json":
        repro = _load(lab_root, RF05, manifest_name)
        return {row["path"]: row["sha256"] for row in repro["canonical_runners"]}
    raise AssertionError(f"unknown RF-05 manifest {manifest_name!r}")


def test_fup04_ceilings_are_consistent_with_what_is_declared(lab_root):
    """A ceiling below the declared repairs would be a contradiction; a ceiling
    above them would silently pre-authorise drift nobody registered."""
    from test_rf05_claims import _SUPERSESSION_SOURCES, _declared_supersessions

    declaration = _declaration(lab_root)
    declared_per_manifest: dict = {}
    # A later registered study (e.g. FP-01) may have further superseded a row
    # FUP-04 declared here -- a legitimate second hop on the SAME chain
    # test_rf05_claims.py's own freeze guard checks. FUP-04's row is then an
    # accurate HISTORICAL declaration, not a claim about the live file; the
    # live file is that later study's responsibility. Detect this with the
    # SAME chain loader and the SAME full RF-05 prior-hash mapping the freeze
    # guard uses, rather than asserting FUP-04's row against a file only a
    # LATER declared study is accountable for.
    manifests_seen: set = set()
    for row in declaration["frozen_component_supersessions"]:
        manifest = row["frozen_by"].rsplit("/", 1)[-1]
        declared_per_manifest[manifest] = declared_per_manifest.get(manifest, 0) + 1
        manifests_seen.add(manifest)
        assert row["registered_study"] == STUDY_ID, row
    for manifest in manifests_seen:
        chain = _declared_supersessions(lab_root, manifest, _rf05_prior_hashes(lab_root, manifest))
        for row in declaration["frozen_component_supersessions"]:
            if row["frozen_by"].rsplit("/", 1)[-1] != manifest:
                continue
            head = chain.get(row["path"], row)
            assert head["current_sha256"] == sha256_file(lab_root / row["path"]), (
                f"{row['path']}: neither the FUP-04 declaration nor any later registered "
                f"supersession ({_SUPERSESSION_SOURCES}) matches the committed file")
    assert declared_per_manifest, "no supersession declared"
    ceilings = declaration["frozen_supersession_ceilings"]
    assert set(ceilings) == set(declared_per_manifest), (
        f"ceilings {sorted(ceilings)} do not cover {sorted(declared_per_manifest)}")
    for manifest, count in declared_per_manifest.items():
        assert ceilings[manifest] == count, (
            f"{manifest}: ceiling {ceilings[manifest]} but {count} repairs are declared")


def test_fup04_reduced_profile_is_opt_in_at_every_entry_point():
    """The contract is a property of the code, not of the declaration's prose:
    every entry point the event route passes through defaults to the engine
    default, so no existing caller can be running on a reduced profile."""
    entry_points = {
        "EventAccountScorer.__init__": (DFP.EventAccountScorer.__init__, "engine_report_level"),
        "run_cutoff_walk_forward": (DFP.run_cutoff_walk_forward, "engine_report_level"),
        "run_one_arm": (RA05.run_one_arm, "engine_report_level"),
        "run_event_account": (EA.run_event_account, "report_level"),
    }
    for name, (function, parameter) in entry_points.items():
        signature = inspect.signature(function)
        assert parameter in signature.parameters, f"{name} lost its {parameter!r} parameter"
        assert signature.parameters[parameter].default is None, (
            f"{name}.{parameter} must default to None (engine default); a non-None default "
            "would silently put every registered caller on a reduced output profile")


def test_fup04_measurement_artifacts_support_the_declaration(lab_root):
    """Re-assert the load-bearing parity from the recorded artifacts, so the
    declaration cannot outlive the measurement that justified it."""
    declaration = _declaration(lab_root)
    for name, measurement in declaration["measurements"].items():
        artifact = lab_root.joinpath(*FUP04).joinpath(measurement["artifact"])
        assert artifact.is_file(), f"{name}: measurement artifact missing"
        assert sha256_file(artifact) == measurement["sha256"], (
            f"{name}: the measurement artifact changed after the declaration was written")
        payload = json.loads(artifact.read_text(encoding="utf-8"))
        assert payload["headline"] == {k: v for k, v in measurement.items()
                                       if k not in ("artifact", "sha256")}, name

    parity = declaration["measurements"]["s7_parity_engine_default_vs_score"]
    assert parity["exact_equal"] is True and parity["max_abs_equity_diff"] == 0.0
    assert parity["equity_len"] > 0
    assert parity["strategy_fills_default"] == parity["strategy_fills_score"] > 0
    assert parity["engine_fill_count_default"] == parity["strategy_fills_default"], (
        "the two counters must agree on the engine default or switching the scorer to the "
        "strategy-level count was not behaviour-preserving")
    assert parity["engine_fill_count_score"] == 0, (
        "a reduced profile must drop the native audit trail, which is why the scorer reads "
        "the strategy-level count")
    assert parity["score_peak_mib"] < parity["default_peak_mib"]

    score = declaration["measurements"]["s3_deployment_full_frame_score_profile"]
    assert score["outcome"] == "COMPLETED"
    assert score["status"] == "EVALUATED"
    assert score["equity_len"] == score["frame_rows"] > 0, (
        "the deployment account must cover the whole frame")
    default = declaration["measurements"]["s3_deployment_full_frame_engine_default"]
    assert default["outcome"] == "FAILED", (
        "the control must reproduce the budget failure or the comparison has no control")
    assert default["frame_rows"] == score["frame_rows"], (
        "both profiles must be measured on the same frame or the comparison is not paired")
