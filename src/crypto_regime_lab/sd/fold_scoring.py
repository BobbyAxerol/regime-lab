"""SD-02: score one origin's candidate panel through a fitted selector and
apply the minY decision rule (guide SS3.4/SS5.5, SD02.4).

Panel-only selection scope (owner decision dec-c94ea602aeac0f1a,
``protocol_migration.json``'s F03b ``scope_revision_sd02_20260925``): the
candidate pool scored here is the SAME <=16-candidate representative panel +
anchor SD-01/SD-02's own archive already forward-evaluates at each origin,
not the full raw unique-candidate pool -- a disclosed, owner-approved scope
narrowing to avoid ~10h of undisclosed new engine compute.

Arm names, guide SS0.3's own vocabulary:
"""
from __future__ import annotations

from .selection import SelectionError, eligible_candidates, q_hat_identity, select_min_y

ARM_A = "A_M4"
ARM_B = "B_SD_GLOBAL"
ARM_R_RULE = "R_RULE"


def jm_arm_name(c: float) -> str:
    return f"JM_C{c}"


class FoldScoringError(ValueError):
    """A fold-scoring step was internally inconsistent."""


def score_pool(predict_fn, panel_rows: list, *, anchor_id: str, schema=None) -> dict:
    """``predict_fn(row, anchor_row) -> float`` (a candidate's Y_hat, given
    its own row and the origin's anchor row). ``panel_rows``: each
    ``{"candidate_id", "params", "features", "sr_is", "is_anchor", ...}`` --
    extra fields (e.g. ``"state"``) a specific ``predict_fn`` needs are the
    caller's own concern, this function is selector-agnostic. The anchor's
    own Y_hat is NEVER special-cased to 0 -- it is verified structurally by
    calling ``predict_fn`` on the anchor against itself like any other row
    (``contrast_vector`` gives v=0 there, so beta^T v=0 by construction)."""
    anchor_rows = [r for r in panel_rows if r["is_anchor"]]
    if not anchor_rows:
        raise FoldScoringError("panel_rows has no anchor row")
    anchor_row = anchor_rows[0]
    scored = []
    for row in panel_rows:
        y_hat = predict_fn(row, anchor_row)
        q_hat = q_hat_identity(row["sr_is"], anchor_row["sr_is"], y_hat)
        scored.append({"candidate_id": row["candidate_id"], "y_hat": y_hat, "q_hat": q_hat,
                       "params": row["params"], "anchor_params": anchor_row["params"]})
    eligible = eligible_candidates(scored)
    try:
        selection = select_min_y(eligible, anchor_id=anchor_id, schema=schema)
    except SelectionError as exc:
        raise FoldScoringError(f"minY selection failed: {exc}") from exc
    return {"selection": selection, "scored": eligible}


def score_pool_arm_a(panel_rows: list, *, anchor_id: str) -> dict:
    """Arm A (guide SS0.3: 'A_M4, stock Mode 4, unchanged'): the installed
    selector's own pick IS the search's own anchor at this origin -- no
    model, no prediction, trivially eligible (Q_hat=0)."""
    anchor_rows = [r for r in panel_rows if r["is_anchor"]]
    if not anchor_rows:
        raise FoldScoringError("panel_rows has no anchor row")
    return {"selection": {"decision": "CANDIDATE_SELECTED", "winner_id": anchor_id,
                          "y_hat": 0.0, "is_anchor": True, "tie_broken": False, "n_eligible": 1},
           "scored": [{"candidate_id": anchor_id, "y_hat": 0.0, "q_hat": 0.0,
                      "params": anchor_rows[0]["params"], "anchor_params": anchor_rows[0]["params"],
                      "eligible": True}]}
