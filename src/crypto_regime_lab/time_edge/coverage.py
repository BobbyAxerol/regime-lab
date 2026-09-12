"""Append-only TE-03 coverage revisions and cross-run collection bridges.

The registered TE-03 target/model window is fixed in
``configs/time_edge_validation_v4/te03_coverage_registration.json``. Extending
it to reach the registered support floor is never silent: a spec whose series
crosses the registered boundary is refused unless a measured coverage revision
is attached with ``te.sh plan --coverage``. The revision restates the prior
coverage, the revised coverage, why the extension is needed, and which
properties (grid, horizon, cell, bank, economics) are unchanged.

Bridging prior and extension collections is explicit too: the merged artifact
records both source identities and the revision hash, and refuses duplicate
targets or non-increasing origins. Nothing is moved or re-dated.
"""
import pandas as pd

from ..experiments.time_edge_contracts import ContractError
from .runtime import local, verify_ref
from .storage import file_digest, read, save

COVERAGE_REVISION_SCHEMA = "regime_lab.te_coverage_revision.v1"
COVERAGE_REGISTRATION_SCHEMA = "regime_lab.te03_coverage_registration.v1"
COVERAGE_COLLECTION_SCHEMA = "regime_lab.te_coverage_collection.v1"
GRID_DAYS = 28


def _require_series(container, name):
    series = container.get(name)
    if not isinstance(series, dict) or not series:
        raise ContractError("coverage revision missing "+name)
    return series


def require_registered_coverage(registered, spec):
    """Refuse a spec that extends the registered series without a revision."""
    if registered.get("schema") != COVERAGE_REGISTRATION_SCHEMA:
        raise ContractError("TE-03 coverage registration missing or unsupported")
    for name in ("target_series", "model_series"):
        if name not in spec:
            continue
        requested = spec[name]
        boundary = pd.Timestamp(registered[name]["end_exclusive"])
        if pd.Timestamp(requested["end"]) > boundary:
            raise ContractError(
                f"{name} extends beyond the registered TE-03 coverage ({boundary.isoformat()}); "
                "register a coverage revision and pass --coverage")
        if pd.Timestamp(requested.get("start", registered[name]["start"])) < pd.Timestamp(registered[name]["start"]):
            raise ContractError(f"{name} starts before the registered TE-03 coverage")
    return registered


def check_coverage_revision(revision, *, spec, registered):
    """Validate an attached revision against the registration and the spec."""
    if not isinstance(revision, dict) or revision.get("schema") != COVERAGE_REVISION_SCHEMA:
        raise ContractError("unsupported or missing coverage revision schema")
    if registered.get("schema") != COVERAGE_REGISTRATION_SCHEMA:
        raise ContractError("TE-03 coverage registration missing or unsupported")
    for key in ("study_id", "registration_id", "revision_id", "stage_scope", "prior_coverage",
                "revised_coverage", "support_floor", "why", "what_it_changes",
                "what_it_does_not_change", "unchanged", "evidence_refs"):
        if not revision.get(key):
            raise ContractError("coverage revision missing "+key)
    prior = revision["prior_coverage"]
    revised = revision["revised_coverage"]
    for name in ("target_series", "model_series"):
        stated = _require_series(prior, name)
        boundary = registered[name]
        for key in ("start", "end_exclusive", "step_days"):
            if stated.get(key) != boundary.get(key):
                raise ContractError(f"coverage revision prior {name}.{key} does not match the registration")
        if name == "target_series":
            if int(stated.get("horizon_days", -1)) != GRID_DAYS:
                raise ContractError("coverage revision prior target horizon moved")
        target = _require_series(revised, name)
        if int(target.get("step_days", -1)) != GRID_DAYS:
            raise ContractError(f"coverage revision must keep the {GRID_DAYS}-day grid for {name}")
        if name == "target_series" and int(target.get("horizon_days", -1)) != GRID_DAYS:
            raise ContractError(f"coverage revision must keep the {GRID_DAYS}-day target horizon")
        if pd.Timestamp(target["start"]) != pd.Timestamp(boundary["start"]):
            raise ContractError(f"coverage revision may not move the {name} start")
        if pd.Timestamp(target["end_exclusive"]) <= pd.Timestamp(boundary["end_exclusive"]):
            raise ContractError(f"coverage revision does not extend {name}")
        if pd.Timestamp(target["end_exclusive"]) < pd.Timestamp(prior[name]["end_exclusive"]):
            raise ContractError(f"coverage revision moves {name} backwards")
    unchanged = revision["unchanged"]
    if unchanged.get("grid_days", GRID_DAYS) != GRID_DAYS:
        raise ContractError("coverage revision may not change the target grid")
    if unchanged.get("target_horizon_days", GRID_DAYS) != GRID_DAYS:
        raise ContractError("coverage revision may not change the target horizon")
    if "target_series" in spec:
        requested = spec["target_series"]
        revised_target = revised["target_series"]
        if pd.Timestamp(requested["end"]) > pd.Timestamp(revised_target["end_exclusive"]):
            raise ContractError("requested target series exceeds the revised coverage")
        extension_start = revised_target.get("extension_start")
        if extension_start is None:
            raise ContractError("revised target coverage needs an explicit extension_start")
        expected = pd.Timestamp(prior["target_series"]["last_origin"])+pd.Timedelta(days=GRID_DAYS)
        if pd.Timestamp(extension_start) != expected:
            raise ContractError("revised target coverage must extend contiguously from the prior last origin")
        if pd.Timestamp(requested["start"]) != expected:
            raise ContractError("target spec must begin at the prior coverage boundary; origins may not move")
        if requested.get("alpha_id") != unchanged.get("alpha_id") or requested.get("cell_id") != unchanged.get("cell_id"):
            raise ContractError("coverage revision belongs to a different alpha/cell")
    if "model_series" in spec:
        requested = spec["model_series"]
        if pd.Timestamp(requested["start"]) != pd.Timestamp(prior["model_series"]["start"]):
            raise ContractError("extended model series must be recomputed from the registered model start")
        if pd.Timestamp(requested["end"]) > pd.Timestamp(revised["model_series"]["end_exclusive"]):
            raise ContractError("requested model series exceeds the revised coverage")
    return revision


def verify_coverage_evidence(root, revision):
    for name, reference in revision.get("evidence_refs", {}).items():
        verify_ref(root, reference)
    for name, reference in revision.get("unchanged", {}).items():
        if isinstance(reference, dict) and set(reference) == {"path", "sha256"}:
            verify_ref(root, reference)
    return revision


def merge_coverage_collections(root, *, prior_refs, extension_ref, coverage_ref, kind, output, lab_run_id):
    """Hash-verified bridge of a prior committed collection and one extension run.

    The merged artifact names both source identities and the coverage revision;
    it never claims a single source identity and never overwrites a target.
    """
    if kind not in ("targets", "results"):
        raise ContractError("unsupported coverage collection kind")
    prior_paths = [verify_ref(root, reference) for reference in prior_refs]
    extension_path = verify_ref(root, extension_ref)
    coverage_path = verify_ref(root, coverage_ref)
    prior_payloads = [read(path) for path in prior_paths]
    extension_payload = read(extension_path)
    coverage = read(coverage_path)
    if coverage.get("schema") != COVERAGE_REVISION_SCHEMA:
        raise ContractError("coverage collection needs a coverage revision")
    sources = []
    for reference, payload, path in zip(prior_refs, prior_payloads, prior_paths):
        sources.append({"role": "prior", "path": reference["path"], "sha256": reference["sha256"],
                        "lab_run_id": payload["lab_run_id"], "source_identity": payload["source_identity"]})
    sources.append({"role": "extension", "path": extension_ref["path"], "sha256": extension_ref["sha256"],
                    "lab_run_id": extension_payload["lab_run_id"], "source_identity": extension_payload["source_identity"]})
    payload = {"schema": COVERAGE_COLLECTION_SCHEMA, "lab_run_id": lab_run_id, "kind": kind,
               "coverage_revision": {"revision_id": coverage["revision_id"], "path": coverage_ref["path"],
                                     "sha256": coverage_ref["sha256"]},
               "sources": sources}
    if kind == "targets":
        rows = [row for body in prior_payloads for row in body["targets"]]
        rows += list(extension_payload["targets"])
        keys = [(row["cell_id"], row["origin"]) for row in rows]
        if len(set(keys)) != len(keys):
            raise ContractError("coverage collection would duplicate a target origin")
        prior_last = max(pd.Timestamp(body["targets"][-1]["origin"]) for body in prior_payloads)
        extension_first = min(pd.Timestamp(row["origin"]) for row in extension_payload["targets"])
        if extension_first <= prior_last:
            raise ContractError("extension targets are not strictly after the prior coverage")
        payload["targets"] = sorted(rows, key=lambda row: (row["origin"], row["cell_id"]))
    else:
        payload["results"] = [row for body in prior_payloads for row in body["results"]] + list(extension_payload["results"])
    path = local(root, output)
    save(path, payload)
    return {"path": str(path.relative_to(root)), "sha256": file_digest(path),
            "targets": len(payload.get("targets", [])), "results": len(payload.get("results", [])),
            "sources": [row["source_identity"] for row in sources]}
