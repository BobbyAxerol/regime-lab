"""SD-02: assemble model_bc-ready training rows from committed archive
records, real activity descriptors, and a JM vintage tape (guide SD02.2/2.3).

The ONLY chronology guard this module (or anything downstream) uses is
``fp.chronology.chronological_split`` / ``fp.forward_ledger.training_view``,
reused VERBATIM (guide migration finding F02's remedy) -- this module's own
job is only to shape SD's real archive+descriptor+tape data into the exact
record schema those two functions already expect
(``record_id``/``origin_cutoff``/``label``/``label_available_at``), never a
second, parallel chronology check.
"""
from __future__ import annotations

import pandas as pd

from .candidate_descriptors import build_descriptor_row
from .metrics import FORWARD_WINDOW_DAYS


class TrainingRowsError(ValueError):
    """A training-row assembly step was internally inconsistent."""


def label_available_at(origin_cutoff: str) -> str:
    """The FWD window's own end -- when a candidate's relative_decay_Y label
    genuinely becomes knowable (guide SS2.2/SS4: forward maturity)."""
    return (pd.Timestamp(origin_cutoff, tz="UTC")
           + pd.Timedelta(days=FORWARD_WINDOW_DAYS)).isoformat()


def chronology_records(archive_by_origin: dict, descriptors_by_origin: dict, schema) -> list:
    """One flat record per (origin, non-degenerate-label candidate), in the
    exact schema ``fp.chronology.chronological_split`` expects PLUS SD's own
    ``candidate_features``/``anchor_features``/``is_anchor``. A candidate
    whose relative_decay_Y status != OK is skipped entirely -- never a
    fabricated numeric label."""
    records = []
    for origin, arch_rec in archive_by_origin.items():
        anchor_rows = [r for r in arch_rec["label_rows"] if r["is_anchor"]]
        if not anchor_rows:
            raise TrainingRowsError(f"{origin}: archive record has no anchor row")
        anchor_row = anchor_rows[0]
        desc_by_id = {d["candidate_id"]: d["activity_entries"] for d in descriptors_by_origin[origin]}
        anchor_features = build_descriptor_row(schema, anchor_row,
                                               activity_entries=desc_by_id[anchor_row["candidate_id"]])
        available_at = label_available_at(origin)
        for row in arch_rec["label_rows"]:
            y = row["relative_decay_Y"]
            if y["status"] != "OK":
                continue
            candidate_features = build_descriptor_row(schema, row,
                                                       activity_entries=desc_by_id[row["candidate_id"]])
            records.append({
                "record_id": f"{origin}|{row['candidate_id']}", "origin_cutoff": origin,
                "label": y["value"], "label_available_at": available_at,
                "candidate_features": candidate_features, "anchor_features": anchor_features,
                "is_anchor": row["is_anchor"],
            })
    return records


def retag_states(records: list, state_by_origin: dict) -> list:
    """Generic state tagging: ``state_by_origin`` maps origin_cutoff -> int
    state or None. Reused by both JM (state_by_origin derived from a
    ``jm_vintage`` tape) and R_RULE (state_by_origin derived from a
    per-fold causal median-ratio threshold, ``r_rule.assign_state``) --
    the SAME downstream ``model_c_rows``/``model_bc`` machinery consumes
    either uniformly, since C has no concept of WHERE a state came from."""
    out = []
    for r in records:
        if r["origin_cutoff"] not in state_by_origin:
            raise TrainingRowsError(f"no state mapping for origin {r['origin_cutoff']!r}")
        out.append({**r, "state": state_by_origin[r["origin_cutoff"]]})
    return out


def attach_states(records: list, tape_by_origin: dict) -> list:
    """Tag each record with its OWN origin's JM-filtered state (a property
    of the origin, shared by every candidate row from it -- state assignment
    is decision-time-independent, already causal by construction in
    ``jm_vintage``, so this can run BEFORE chronological filtering). An
    origin whose tape status != OK gets ``state=None`` -- excluded from C's
    per-state pool downstream (``model_c_rows``), never a fabricated ID."""
    state_by_origin = {}
    for r in records:
        origin = r["origin_cutoff"]
        if origin in state_by_origin:
            continue
        tape_rec = tape_by_origin.get(origin)
        if tape_rec is None:
            raise TrainingRowsError(f"no tape record for origin {origin!r}")
        state_by_origin[origin] = tape_rec.state if tape_rec.status == "OK" else None
    return retag_states(records, state_by_origin)


def model_b_rows(usable_records: list) -> list:
    """Adapt chronology-guarded records to model_bc's field names. Every
    record contributes to B's global pool regardless of state."""
    return [{"origin_id": r["origin_cutoff"], "candidate_features": r["candidate_features"],
            "anchor_features": r["anchor_features"], "y": r["label"]} for r in usable_records]


def model_c_rows(usable_records: list) -> list:
    """Same adapter, but ONLY records with a real (non-None) state --
    guide SD02.3: an unknown-state origin never gets a fabricated state ID,
    so it is excluded from C's state-conditioned training pool (it still
    contributes to B's pool via ``model_b_rows``)."""
    return [{"origin_id": r["origin_cutoff"], "candidate_features": r["candidate_features"],
            "anchor_features": r["anchor_features"], "y": r["label"], "state": r["state"]}
           for r in usable_records if r["state"] is not None]
